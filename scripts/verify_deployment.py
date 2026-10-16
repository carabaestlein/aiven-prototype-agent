#!/usr/bin/env python3
"""Two-stage live acceptance check; the operator restarts Runtime between stages.

Uses Langfuse's current observations API, not deprecated trace reads:
https://langfuse.com/docs/api-and-data-platform/features/public-api
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx


class VerificationError(Exception):
    """A safe-to-display diagnostic that never includes a provider response."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    return value.isoformat().replace('+00:00', 'Z')


def draft_hash(draft):
    require(isinstance(draft, str) and bool(draft.strip()), 'Run has no draft.')
    return hashlib.sha256(draft.encode('utf-8')).hexdigest()


def base_url(value, variable):
    try:
        parsed = urlsplit(value)
        valid = (parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and (parsed.scheme == 'https' or
                      (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1'))))
    except ValueError:
        valid = False
    require(valid, f'{variable} must be an HTTPS base URL without credentials or query parameters (HTTP loopback is allowed locally).')
    return value.rstrip('/')


def request_json(client, method, path, **kwargs):
    try:
        response = client.request(method, path, **kwargs)
    except httpx.HTTPError:
        raise VerificationError('Connection failed; check service availability and trusted TLS certificates.') from None
    require(not response.is_redirect, 'Service returned a redirect; set the final base URL. Redirects are disabled.')
    require(response.is_success, f'Service returned HTTP {response.status_code}; response body withheld.')
    try:
        result = response.json()
    except ValueError:
        raise VerificationError('Service returned invalid JSON.') from None
    require(isinstance(result, dict), 'Service returned an unexpected JSON shape.')
    return result


def check_session(app, allow_mock=False, expected_model=None):
    require(request_json(app, 'GET', '/health/ready').get('status') == 'ready', 'App is not ready.')
    session = request_json(app, 'GET', '/api/session')
    require(session.get('mode') in ('mock', 'openai-compatible'), 'App returned an unknown model mode.')
    require(allow_mock or session['mode'] == 'openai-compatible', 'App is in mock mode; configure AI Gateway, or use --allow-mock for a local check.')
    if session['mode'] != 'mock':
        require(isinstance(session.get('model'), str) and bool(session['model']), 'Real model mode has no configured model.')
    if expected_model:
        require(session.get('model') == expected_model, 'Configured model differs from --expected-model.')
    return session


def check_run(run, status, revision, mode, run_id=None):
    require(not run.get('error'), 'Workflow paused with an error; inspect service configuration and saved run.')
    try:
        UUID(run.get('id', ''))
    except (ValueError, AttributeError, TypeError):
        raise VerificationError('Run returned an invalid ID.') from None
    if run_id:
        require(run.get('id') == run_id, 'Run ID changed unexpectedly.')
    require(run.get('status') == status, f'Expected run status {status}.')
    require(run.get('revision') == revision, f'Expected revision {revision}.')
    require(run.get('mode') == mode, 'Run model mode differs from the configured mode.')
    require(isinstance(run.get('checkpoint'), str) and bool(run['checkpoint']), 'Run has no persisted checkpoint.')
    draft_hash(run.get('draft'))


def trace_id(run):
    value = run.get('trace_id')
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value), 'Mutation returned no valid trace_id; enable Langfuse tracing.')
    return value


def observations(client, target_trace, since, until, deadline, monotonic):
    """Read all pages with both a time and a page bound; request no input/output."""
    params = {'traceId': target_trace, 'fromStartTime': since, 'toStartTime': until,
              'fields': 'core,basic,model,metadata', 'limit': 100}
    rows, cursors = [], set()
    for _ in range(10):
        remaining = deadline - monotonic()
        if remaining <= 0:
            return None
        try:
            response = client.get('/api/public/v2/observations', params=params,
                                  timeout=min(10, remaining))
        except httpx.HTTPError:
            return None
        require(not response.is_redirect, 'Langfuse redirected the read request; set its final base URL.')
        if response.status_code in (429, 502, 503, 504):
            return None
        require(response.is_success, f'Langfuse observations read returned HTTP {response.status_code}; check API keys, permissions and server v4 compatibility.')
        try:
            payload = response.json()
        except ValueError:
            raise VerificationError('Langfuse returned invalid JSON.') from None
        require(isinstance(payload, dict) and isinstance(payload.get('data'), list), 'Langfuse returned an unexpected observations shape.')
        require(all(isinstance(row, dict) for row in payload['data']), 'Langfuse returned an invalid observation.')
        rows.extend(payload['data'])
        meta = payload.get('meta') or {}
        require(isinstance(meta, dict), 'Langfuse returned invalid pagination metadata.')
        cursor = meta.get('cursor')
        if not cursor:
            return rows
        require(isinstance(cursor, str) and cursor not in cursors, 'Langfuse returned a repeated or invalid cursor.')
        cursors.add(cursor)
        params['cursor'] = cursor
    raise VerificationError('Trace exceeded the 1,000-observation safety bound.')


def verify_trace(client, target_trace, run_id, since, expect_generation, requested_model,
                 timeout=90, interval=2, monotonic=time.monotonic, sleep=time.sleep):
    """Poll worker lag. For no-generation assertions, observe the entire window."""
    deadline = monotonic() + timeout
    found_complete = False
    latest_read_complete = False
    has_polled = False
    until = timestamp(utc_now() + timedelta(minutes=5))
    while monotonic() < deadline:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        if has_polled and remaining < interval:
            # Do not start a last read with a deadline-shortened timeout. Its
            # failure could erase the last complete poll solely because the
            # observation window is ending. Keep waiting through the window,
            # preserving success/failure from the last properly timed read.
            sleep(remaining)
            continue
        has_polled = True
        rows = observations(client, target_trace, since, until, deadline, monotonic)
        latest_read_complete = rows is not None
        if rows is not None:
            for row in rows:
                require(row.get('traceId') == target_trace, 'Langfuse returned an observation from another trace.')
                require(not row.get('sessionId') or row['sessionId'] == run_id, 'Trace session does not match the saved run.')
                require(row.get('level') != 'ERROR', 'Trace contains an error observation.')
            roots = [row for row in rows if row.get('type') == 'SPAN' and row.get('name') == 'langgraph.run' and row.get('endTime')]
            generations = [row for row in rows if row.get('type') == 'GENERATION']
            if not expect_generation:
                require(not generations, 'Approval or mock invocation unexpectedly recorded a model generation.')
                found_complete = found_complete or bool(roots)
            else:
                matches = [row for row in generations if row.get('name') == 'gateway.chat'
                           and row.get('endTime') and isinstance(row.get('model'), str) and row['model']]
                for generation in matches:
                    metadata = generation.get('metadata')
                    if isinstance(metadata, dict) and metadata.get('requested_model'):
                        require(metadata['requested_model'] == requested_model, 'Generation requested a different model than the app configuration.')
                if roots and matches:
                    return
        remaining = deadline - monotonic()
        if remaining > 0:
            sleep(min(interval, remaining))
    if not expect_generation and found_complete and latest_read_complete:
        return
    raise VerificationError('Trace verification timed out; check Langfuse worker/storage health and SDK/server compatibility, then retry the check.')


def write_receipt(path, receipt, exclusive=False):
    # A receipt holds only hashes, identifiers and configuration labels, never keys or drafts.
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    try:
        with os.fdopen(os.open(path, flags, 0o600), 'w') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    except OSError:
        raise VerificationError('Cannot write receipt; choose a writable path and do not overwrite an existing start receipt.') from None


def read_receipt(path):
    try:
        receipt = json.loads(path.read_text())
        required = {'version', 'app_url', 'run_id', 'checkpoint', 'draft_sha256', 'revision',
                    'mode', 'model', 'trace_id', 'started_at', 'stage'}
        require(isinstance(receipt, dict) and required <= receipt.keys() and receipt['version'] == 1,
                'Receipt format is invalid.')
        UUID(receipt['run_id'])
        require(receipt['stage'] in ('awaiting_restart', 'revised', 'completed_trace_pending', 'complete'),
                'Receipt has an unknown stage.')
        return receipt
    except (OSError, ValueError, TypeError, AttributeError):
        raise VerificationError('Cannot read a valid receipt.') from None


def start(app, langfuse, app_url, receipt_path, args):
    require(not receipt_path.exists(), 'Receipt already exists; use resume or choose a new receipt path.')
    session = check_session(app, args.allow_mock, args.expected_model)
    since = timestamp(utc_now() - timedelta(minutes=5))
    run = request_json(app, 'POST', '/api/runs', json={
        'request': 'Deployment acceptance check: write one short welcome sentence for a test workspace.'})
    check_run(run, 'awaiting_review', 1, session['mode'])
    receipt = {'version': 1, 'app_url': app_url, 'run_id': run['id'], 'checkpoint': run['checkpoint'],
               'draft_sha256': draft_hash(run['draft']), 'revision': 1, 'mode': session['mode'],
               'model': session.get('model'), 'trace_id': trace_id(run), 'started_at': since,
               'stage': 'awaiting_restart'}
    write_receipt(receipt_path, receipt, exclusive=True)
    verify_trace(langfuse, receipt['trace_id'], run['id'], since, session['mode'] != 'mock',
                 session.get('model'), args.trace_timeout, args.poll_interval)
    print('PASS: ready, draft checkpoint saved, invocation trace verified. Receipt saved.')
    print('Now restart the app on Aiven Runtime, wait for readiness, then run resume with --restart-confirmed. This script does not restart Runtime.')


def resume(app, langfuse, app_url, receipt_path, args):
    require(args.restart_confirmed, 'Restart the app on Runtime first, then pass --restart-confirmed. The script cannot independently prove a restart occurred.')
    receipt = read_receipt(receipt_path)
    require(receipt['app_url'] == app_url, 'APP_URL differs from the receipt.')
    session = check_session(app, args.allow_mock, args.expected_model)
    require(session['mode'] == receipt['mode'] and session.get('model') == receipt['model'], 'Model configuration changed since start.')
    run_id = receipt['run_id']
    current = request_json(app, 'GET', f'/api/runs/{run_id}')
    expected_status = 'completed' if receipt['stage'] in ('complete', 'completed_trace_pending') else 'awaiting_review'
    check_run(current, expected_status, receipt['revision'], receipt['mode'], run_id)
    require(current['checkpoint'] == receipt['checkpoint'], 'Saved checkpoint changed across the reported restart.')
    require(draft_hash(current['draft']) == receipt['draft_sha256'], 'Saved draft changed across the reported restart.')
    # Recheck the original trace, including when start previously timed out on worker lag.
    verify_trace(langfuse, receipt['trace_id'], run_id, receipt['started_at'], receipt['mode'] != 'mock',
                 receipt['model'], args.trace_timeout, args.poll_interval)
    if receipt['stage'] == 'awaiting_restart':
        since = timestamp(utc_now() - timedelta(minutes=5))
        revised = request_json(app, 'POST', f'/api/runs/{run_id}/review', json={
            'action': 'revise', 'feedback': 'Use exactly five words.', 'checkpoint': current['checkpoint']})
        check_run(revised, 'awaiting_review', 2, receipt['mode'], run_id)
        require(revised['checkpoint'] != current['checkpoint'], 'Revision did not create a new checkpoint.')
        revision_trace = trace_id(revised)
        require(revision_trace != receipt['trace_id'], 'Revision reused the initial invocation trace.')
        # Save the new state before polling so a delayed trace does not hide the mutation.
        receipt.update(stage='revised', revision=2, checkpoint=revised['checkpoint'],
                       draft_sha256=draft_hash(revised['draft']), revision_trace_id=revision_trace,
                       revision_started_at=since, operator_confirmed_restart=True)
        write_receipt(receipt_path, receipt)
        current = revised
    require(receipt.get('revision_trace_id') and receipt.get('revision_started_at'), 'Receipt is missing revision trace details.')
    verify_trace(langfuse, receipt['revision_trace_id'], run_id, receipt['revision_started_at'], receipt['mode'] != 'mock',
                 receipt['model'], args.trace_timeout, args.poll_interval)
    if receipt['stage'] == 'revised':
        since = timestamp(utc_now() - timedelta(minutes=5))
        approved = request_json(app, 'POST', f'/api/runs/{run_id}/review', json={
            'action': 'approve', 'checkpoint': current['checkpoint']})
        check_run(approved, 'completed', 2, receipt['mode'], run_id)
        require(approved['checkpoint'] != current['checkpoint'], 'Approval did not create a new checkpoint.')
        require(draft_hash(approved['draft']) == receipt['draft_sha256'], 'Approval unexpectedly changed the draft.')
        approval_trace = trace_id(approved)
        require(approval_trace not in (receipt['trace_id'], receipt['revision_trace_id']), 'Approval reused an earlier invocation trace.')
        receipt.update(stage='completed_trace_pending', checkpoint=approved['checkpoint'],
                       approval_trace_id=approval_trace, approval_started_at=since)
        write_receipt(receipt_path, receipt)
    require(receipt.get('approval_trace_id') and receipt.get('approval_started_at'), 'Receipt is missing approval trace details.')
    verify_trace(langfuse, receipt['approval_trace_id'], run_id, receipt['approval_started_at'], False,
                 receipt['model'], args.trace_timeout, args.poll_interval)
    receipt.update(stage='complete', operator_confirmed_restart=True)
    write_receipt(receipt_path, receipt)
    print('PASS: saved state survived the operator-confirmed restart; revision 2 and approval completed with new checkpoints.')
    print('PASS: draft/revision traces contain model generations (unless --allow-mock); approval trace contains none during the observation window.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('start', 'resume'))
    parser.add_argument('--receipt', required=True, type=Path, help='Local receipt file; use the same path for both stages.')
    parser.add_argument('--restart-confirmed', action='store_true', help='Confirm you restarted Runtime after start; required for resume.')
    parser.add_argument('--expected-model', help='Require this configured AI Gateway model name; router-resolved names may differ in traces.')
    parser.add_argument('--allow-mock', action='store_true', help='Allow local deterministic mode; this does not validate AI Gateway.')
    parser.add_argument('--trace-timeout', type=float, default=90, help='Maximum seconds to poll each trace (default: 90). Approval observes the full window.')
    parser.add_argument('--poll-interval', type=float, default=2, help='Seconds between Langfuse reads (default: 2).')
    args = parser.parse_args(argv)
    try:
        require(0 < args.trace_timeout <= 900 and 0 < args.poll_interval <= args.trace_timeout, 'Trace timeout must be 0–900 seconds and polling interval must fit inside it.')
        needed = ('APP_URL', 'APP_API_KEY', 'LANGFUSE_BASE_URL', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY')
        require(all(os.environ.get(key) for key in needed), 'Set APP_URL, APP_API_KEY, LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in your environment; do not put keys in command arguments.')
        app_url = base_url(os.environ['APP_URL'], 'APP_URL')
        langfuse_url = base_url(os.environ['LANGFUSE_BASE_URL'], 'LANGFUSE_BASE_URL')
        options = dict(follow_redirects=False, verify=True, trust_env=False, timeout=httpx.Timeout(65, connect=10))
        with httpx.Client(base_url=app_url, headers={'Authorization': 'Bearer ' + os.environ['APP_API_KEY']}, **options) as app:
            with httpx.Client(base_url=langfuse_url, auth=(os.environ['LANGFUSE_PUBLIC_KEY'], os.environ['LANGFUSE_SECRET_KEY']), **options) as langfuse:
                (start if args.mode == 'start' else resume)(app, langfuse, app_url, args.receipt, args)
    except VerificationError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
