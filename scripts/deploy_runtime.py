#!/usr/bin/env python3
"""Plan (default) or create the dedicated Step 1 stack; never alter older services.

Requires AIVEN_API_TOKEN. A new stack also requires MODEL_API_KEY,
LANGFUSE_INIT_USER_EMAIL and S3_BUCKET/REGION/ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY.
Agent-only updates use existing state credentials. Keep --state outside the
repository: it contains stable passwords and is written with mode 0600.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit

import httpx

API = 'https://api.aiven.io/v1'
REPOSITORY = 'https://github.com/carabaestlein/aiven-prototype-agent.git'
PROJECT, CLOUD = 'cara-test', 'aws-eu-west-1'
DATA = {
    'prototype-agent-pg': ('pg', 'startup-4', {'pg_version': '16'}),
    'prototype-langfuse-pg': ('pg', 'startup-4', {'pg_version': '17'}),
    'prototype-langfuse-ch': ('clickhouse', 'startup-8', {'clickhouse_version': '26.3'}),
    'prototype-langfuse-valkey': ('valkey', 'startup-2', {
        'valkey_version': '8.1', 'valkey_maxmemory_policy': 'noeviction', 'valkey_persistence': 'rdb'}),
}
APPS = {'prototype-langfuse-web': ('startup-200-4096', 'Dockerfile.langfuse-web'),
        'prototype-langfuse-worker': ('startup-200-4096', 'Dockerfile.langfuse-worker'),
        'prototype-agent': ('startup-50-1024', 'Dockerfile')}
INPUTS = ('MODEL_API_KEY', 'LANGFUSE_INIT_USER_EMAIL', 'S3_BUCKET', 'S3_REGION',
          'S3_ENDPOINT', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY')


class DeploymentError(Exception):
    """Only sanitized, safe-to-print diagnostics belong here."""


def require(condition, message):
    if not condition:
        raise DeploymentError(message)


def origin(value):
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment
                 and parsed.path in ('', '/'))
    except (ValueError, TypeError):
        valid = False
    require(valid, 'Expected a trusted HTTPS origin without credentials or a path.')
    return value.rstrip('/')


def runtime_origin(service):
    """Use Runtime's public HTTPS edge, never its internal container port."""
    for component in service.get('components', []):
        if component.get('component') != 'http' or component.get('route') != 'public':
            continue
        host = component.get('host')
        if not host:
            continue
        require(isinstance(host, str) and len(host) <= 253 and all(
            re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
            for label in host.split('.')), 'Runtime returned an invalid public HTTP hostname.')
        return origin('https://' + host)
    # Runtime may return a legacy hostname ending in ':' as service_uri.
    # Only use this field when it is already a complete, valid HTTPS origin.
    try:
        return origin(service.get('service_uri'))
    except DeploymentError:
        return None


def env_entries(values):
    public = {'MODEL_MODE', 'MODEL_BASE_URL', 'MODEL_NAME', 'LANGFUSE_BASE_URL', 'TRACE_CONTENT',
              'APP_ENVIRONMENT', 'APP_RELEASE', 'NEXTAUTH_URL', 'CLICKHOUSE_URL', 'CLICKHOUSE_DB',
              'CLICKHOUSE_MIGRATION_URL', 'S3_REGION', 'S3_ENDPOINT', 'S3_FORCE_PATH_STYLE',
              'LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL', 'LANGSMITH_TRACING',
              'LANGCHAIN_TRACING_V2', 'LANGFUSE_INIT_ORG_ID', 'LANGFUSE_INIT_PROJECT_ID'}
    return [{'key': key, 'value': value, 'kind': 'variable' if key in public else 'secret'}
            for key, value in values.items()]


def save_state(path, state):
    require(not path.is_symlink(), 'State path must not be a symlink.')
    temp = None
    try:
        descriptor, filename = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        temp = Path(filename)
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(state, handle, indent=2)
            handle.write('\n')
        os.replace(temp, path)
    except OSError:
        raise DeploymentError('Cannot save private deployment state; check its directory and permissions.') from None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def load_state(path):
    if path is None or not path.exists():
        return None
    require(not path.is_symlink() and path.stat().st_mode & 0o077 == 0,
            'Deployment state must be a private regular file with mode 0600.')
    try:
        state = json.loads(path.read_text())
        require(state.get('version') == 1 and state.get('project') == PROJECT,
                'Deployment state has an unsupported format or project.')
        return state
    except (OSError, ValueError, AttributeError):
        raise DeploymentError('Cannot read valid private deployment state.') from None


def new_state(args, environ):
    require(all(environ.get(key) for key in INPUTS), 'Apply requires the Gateway, Langfuse owner email and all five S3 environment settings.')
    origin(environ['S3_ENDPOINT'])
    values = {key: environ[key] for key in INPUTS}
    values.update({key: secrets.token_hex(32) for key in
                   ('APP_PASSWORD', 'APP_API_KEY', 'SESSION_SECRET', 'SALT', 'ENCRYPTION_KEY',
                    'NEXTAUTH_SECRET', 'LANGFUSE_INIT_USER_PASSWORD')})
    values['LANGFUSE_INIT_PROJECT_PUBLIC_KEY'] = 'pk-lf-' + secrets.token_hex(16)
    values['LANGFUSE_INIT_PROJECT_SECRET_KEY'] = 'sk-lf-' + secrets.token_hex(32)
    return {'version': 1, 'project': PROJECT, 'owner': secrets.token_hex(16),
            'branch': args.branch, 'release': args.release, 'values': values, 'stage': 'prepared'}


class Deployer:
    def __init__(self, api, public, timeout=1800, monotonic=time.monotonic, sleep=time.sleep):
        self.api, self.public = api, public
        self.monotonic, self.sleep = monotonic, sleep
        self.deadline = monotonic() + timeout

    def remaining(self):
        left = self.deadline - self.monotonic()
        require(left > 0, 'Deployment wait timed out; resources are preserved. Rerun with the same private state.')
        return min(30, left)

    def call(self, method, path, body=None, missing=False):
        try:
            response = self.api.request(method, API + path, json=body, timeout=self.remaining())
        except httpx.HTTPError:
            raise DeploymentError('Aiven connection failed; resources are preserved. Response details withheld.') from None
        if missing and response.status_code == 404:
            return None
        require(response.is_success, f'Aiven returned HTTP {response.status_code}; response body withheld.')
        if response.status_code == 204:
            return {}
        try:
            result = response.json()
        except ValueError:
            raise DeploymentError('Aiven returned invalid JSON.') from None
        require(isinstance(result, dict), 'Aiven returned an unexpected response shape.')
        return result

    def service(self, name, missing=False):
        result = self.call('GET', f'/project/{PROJECT}/service/{name}', missing=missing)
        return result.get('service') if result is not None else None

    def pause(self):
        self.sleep(min(10, self.remaining()))

    def wait_services(self, names):
        while True:
            services = {name: self.service(name) for name in names}
            if all(service and service.get('state') == 'RUNNING' for service in services.values()):
                return services
            self.pause()

    def wait_health(self, url):
        while True:
            try:
                response = self.public.get(url, timeout=min(10, self.remaining()))
                if response.is_success:
                    return
                require(not response.is_redirect, 'Health endpoint redirected; inspect its configured origin.')
            except httpx.HTTPError:
                pass
            self.pause()

    def wait_origin(self, name):
        while True:
            url = runtime_origin(self.service(name) or {})
            if url:
                return url
            self.pause()

    def wait_langfuse_initialized(self, url, public_key, secret_key, project_id='prototype-project'):
        """Wait for the corrected auth origin and initialized project credentials."""
        url = origin(url)
        expected = urlsplit(url)

        def read(path, auth=None):
            try:
                response = self.public.get(url + path, auth=auth, follow_redirects=False,
                                           timeout=min(10, self.remaining()))
            except httpx.HTTPError:
                return None
            require(not response.is_redirect, 'Langfuse initialization endpoint redirected; inspect its configured origin.')
            if response.status_code != 200:
                return None  # A new web process/project may still be initializing.
            try:
                payload = response.json()
            except ValueError:
                raise DeploymentError('Langfuse initialization endpoint returned invalid JSON; body withheld.') from None
            require(isinstance(payload, dict), 'Langfuse initialization endpoint returned an unexpected shape.')
            return payload

        def auth_matches(providers):
            if not providers:
                return False
            for provider in providers.values():
                if not isinstance(provider, dict):
                    return False
                for key in ('signinUrl', 'callbackUrl'):
                    value = provider.get(key)
                    if not isinstance(value, str):
                        return False
                    try:
                        parsed = urlsplit(value)
                        if (parsed.scheme != 'https' or parsed.hostname != expected.hostname
                                or (parsed.port or 443) != (expected.port or 443)
                                or parsed.username or parsed.password):
                            return False
                    except ValueError:
                        return False
            return True

        while True:
            if auth_matches(read('/api/auth/providers')):
                projects = read('/api/public/projects', auth=(public_key, secret_key))
                if projects and isinstance(projects.get('data'), list) and any(
                        isinstance(project, dict) and project.get('id') == project_id
                        for project in projects['data']):
                    return
            self.pause()

    def preflight(self, state):
        types = {kind for kind, _, _ in DATA.values()} | {'application'}
        schemas, plans = {}, {}
        for kind in sorted(types):
            schemas[kind] = self.call('GET', f'/project/{PROJECT}/service-types/{kind}')['user_config_schema']
            plans[kind] = self.call('GET', f'/project/{PROJECT}/service-types/{kind}/plans')['service_plans']
        versions = self.call('GET', '/service_versions')['service_versions']
        for name, (kind, plan, config) in DATA.items():
            for key, value in config.items():
                spec = schemas[kind].get('properties', {}).get(key)
                require(spec and ('enum' not in spec or value in spec['enum']), 'Requested database setting is unavailable in the current schema.')
                if key.endswith('_version'):
                    require(any(v.get('service_type') == kind and v.get('major_version') == value
                                and v.get('state') == 'available' for v in versions), 'Requested database version is not available.')
        for kind, plan in [(k, p) for k, p, _ in DATA.values()] + [('application', p) for p, _ in APPS.values()]:
            require(any(p.get('service_plan') == plan and CLOUD in p.get('regions', {}) for p in plans[kind]),
                    'Requested service plan is unavailable in the target region.')
        integrations = self.call('GET', f'/project/{PROJECT}/integration_types')['integration_types']
        credential = next((i for i in integrations if i.get('integration_type') == 'application_service_credential'), {})
        require({'pg', 'valkey'} <= set(credential.get('source_service_types', [])), 'PostgreSQL/Valkey Runtime credential integrations are unavailable.')
        for name in (*DATA, *APPS):
            current = self.service(name, missing=True)
            if current:
                require(state and current.get('tags', {}).get('prototype_step1') == state['owner'],
                        'A target name already exists without this deployment ownership tag; no changes made.')

    def ensure_service(self, name, kind, plan, config, state, integrations=None, existing_only=False):
        current = self.service(name, missing=True)
        if current:
            require(current.get('tags', {}).get('prototype_step1') == state['owner'], 'Existing service ownership does not match private state.')
            require(current.get('service_type') == kind and current.get('cloud_name') == CLOUD
                    and current.get('plan') == plan, 'Existing service configuration differs from this deployment.')
            if current.get('state') == 'POWEROFF':
                self.call('PUT', f'/project/{PROJECT}/service/{name}', {'powered': True})
            return current
        require(not existing_only, 'Agent-only deployment requires the existing owned agent; no service was created.')
        body = {'service_name': name, 'service_type': kind, 'plan': plan, 'cloud': CLOUD,
                'tags': {'prototype_step1': state['owner']}, 'user_config': config}
        if integrations:
            body['service_integrations'] = integrations
        return self.call('POST', f'/project/{PROJECT}/service', body)['service']

    def app(self, name, values, state, existing_only=False, force_redeploy=False):
        plan, dockerfile = APPS[name]
        release = state.get('agent_source', state) if name == 'prototype-agent' else state
        source = {'repository_url': REPOSITORY, 'branch': release['branch'],
                  'build_path': './', 'containerfile_path': './' + dockerfile}
        settings = {'source': source, 'ports': [] if name.endswith('worker') else
                    [{'name': 'http', 'port': 8080, 'protocol': 'HTTP'}],
                    'environment_variables': env_entries(values)}
        integrations = []
        mappings = [('prototype-agent-pg', 'pg', 'DATABASE_URL')] if name == 'prototype-agent' else [
            ('prototype-langfuse-pg', 'pg', 'DATABASE_URL'), ('prototype-langfuse-valkey', 'valkey', 'VALKEY_URL')]
        for service, kind, variable in mappings:
            integrations.append({'integration_type': 'application_service_credential', 'source_service': service,
                'user_config': {'service_type': kind, 'exposed_values': {'connection_string': {'environment_variable_key': variable}}}})
        current = self.ensure_service(name, 'application', plan, {'application': settings}, state,
                                      integrations, existing_only=existing_only)
        # Only owned fresh applications are reconciled; full env is deterministic
        # from the same private state, so stable credentials survive every retry.
        existing = current.get('user_config', {}).get('application', {})
        old_env = {entry.get('key'): entry.get('value') for entry in existing.get('environment_variables', [])}
        source_changed = any(existing.get('source', {}).get(key) != value for key, value in source.items())
        if source_changed or any(old_env.get(key) != value for key, value in values.items()) or existing.get('ports') != settings['ports']:
            self.call('PUT', f'/project/{PROJECT}/service/{name}', {'user_config': {'application': settings}})
        if source_changed or force_redeploy:
            self.call('POST', f'/project/{PROJECT}/service/{name}/application/redeploy')
        return current


def clickhouse_settings(service):
    components = service.get('components', [])
    def endpoint(names, scheme):
        row = next((c for c in components if c.get('component') in names and c.get('ssl') is not False
                    and c.get('route') in ('dynamic', 'public')), None)
        require(row and row.get('host') and row.get('port'), 'ClickHouse TLS endpoints are missing; inspect service connection information.')
        return f"{scheme}://{row['host']}:{row['port']}"
    params = service.get('service_uri_params') or {}
    parsed = urlsplit(service.get('service_uri') or '')
    user = params.get('user') or params.get('username') or (unquote(parsed.username) if parsed.username else None)
    password = params.get('password') or (unquote(parsed.password) if parsed.password else None)
    require(user and password and password not in ('***', '********', '<redacted>'), 'ClickHouse credentials are missing or redacted.')
    return {'CLICKHOUSE_URL': endpoint(('clickhouse_https',), 'https'),
            'CLICKHOUSE_MIGRATION_URL': endpoint(('clickhouse', 'clickhouse_native'), 'clickhouse'),
            'CLICKHOUSE_USER': user, 'CLICKHOUSE_PASSWORD': password, 'CLICKHOUSE_DB': 'langfuse'}


def agent_environment(state, ca):
    private = state['values']
    agent = {key: private[key] for key in ('APP_PASSWORD', 'APP_API_KEY', 'SESSION_SECRET', 'MODEL_API_KEY')}
    agent.update(PG_CA_CERT_BASE64=ca, MODEL_MODE='openai-compatible', MODEL_BASE_URL='https://ai.aiven.io/v1',
        MODEL_NAME='claude-sonnet-5', LANGFUSE_BASE_URL=state['langfuse_url'],
        LANGFUSE_PUBLIC_KEY=private['LANGFUSE_INIT_PROJECT_PUBLIC_KEY'],
        LANGFUSE_SECRET_KEY=private['LANGFUSE_INIT_PROJECT_SECRET_KEY'], TRACE_CONTENT='false',
        APP_ENVIRONMENT=PROJECT, APP_RELEASE=state.get('agent_source', state)['release'],
        LANGSMITH_TRACING='false', LANGCHAIN_TRACING_V2='false')
    return agent


def preflight_agent(deployer, state):
    require(state and state.get('langfuse_url'), 'Agent-only deployment requires an existing private deployment state with Langfuse configured.')
    origin(state['langfuse_url'])
    required = ('APP_PASSWORD', 'APP_API_KEY', 'SESSION_SECRET', 'MODEL_API_KEY',
                'LANGFUSE_INIT_PROJECT_PUBLIC_KEY', 'LANGFUSE_INIT_PROJECT_SECRET_KEY')
    require(all(state.get('values', {}).get(key) for key in required),
            'Private deployment state is missing required agent credentials.')
    current = deployer.service('prototype-agent', missing=True)
    require(current, 'Agent-only deployment requires the existing owned agent; no service was created.')
    require(current.get('tags', {}).get('prototype_step1') == state['owner'],
            'Existing service ownership does not match private state.')
    require(current.get('service_type') == 'application' and current.get('cloud_name') == CLOUD
            and current.get('plan') == APPS['prototype-agent'][0],
            'Existing agent configuration differs from this deployment.')


def apply_agent(deployer, state, path, branch, release):
    preflight_agent(deployer, state)
    certificate = deployer.call('GET', f'/project/{PROJECT}/kms/ca')['certificate']
    ca = base64.b64encode(certificate.encode()).decode()
    # Save the intended source before mutation so an interrupted deployment can
    # resume without rotating credentials or silently reverting on full apply.
    state['agent_source'] = {'branch': branch, 'release': release}
    state['agent_update'] = 'requested'
    save_state(path, state)
    deployer.app('prototype-agent', agent_environment(state, ca), state,
                 existing_only=True, force_redeploy=True)
    deployer.wait_services(['prototype-agent'])
    state['app_url'] = deployer.wait_origin('prototype-agent')
    deployer.wait_health(state['app_url'] + '/health/ready')
    state['agent_update'] = 'health_ready'
    save_state(path, state)
    return {'status': 'agent_health_ready', 'app_url': state['app_url'],
            'agent_source': state['agent_source'], 'build_commit_verification': 'pending'}


def apply(deployer, state, path, data_only=False):
    for name, (kind, plan, config) in DATA.items():
        deployer.ensure_service(name, kind, plan, config, state)
    data = deployer.wait_services(DATA)
    if data_only:
        state['stage'] = 'data_ready'
        save_state(path, state)
        return {'status': 'data_ready', 'services': list(DATA), 'applications': 'not_started'}
    db_path = f'/project/{PROJECT}/service/prototype-langfuse-ch/clickhouse/db'
    if not any(db.get('name') == 'langfuse' for db in deployer.call('GET', db_path)['databases']):
        deployer.call('POST', db_path, {'database': 'langfuse'})
    while not any(db.get('name') == 'langfuse' and db.get('state') == 'ok'
                  for db in deployer.call('GET', db_path)['databases']):
        deployer.pause()
    certificate = deployer.call('GET', f'/project/{PROJECT}/kms/ca')['certificate']
    ca = base64.b64encode(certificate.encode()).decode()
    private = state['values']
    shared = {key: private[key] for key in ('SALT', 'ENCRYPTION_KEY', 'S3_BUCKET', 'S3_REGION',
                                           'S3_ENDPOINT', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY')}
    shared.update(clickhouse_settings(data['prototype-langfuse-ch']))
    shared.update(AIVEN_CA_CERT_BASE64=ca, S3_FORCE_PATH_STYLE='false', NEXTAUTH_URL=state.get('langfuse_url', 'https://pending.invalid'))
    web = dict(shared, **{key: private[key] for key in ('NEXTAUTH_SECRET', 'LANGFUSE_INIT_USER_EMAIL',
        'LANGFUSE_INIT_USER_PASSWORD', 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY', 'LANGFUSE_INIT_PROJECT_SECRET_KEY')},
        LANGFUSE_INIT_ORG_ID='prototype-org', LANGFUSE_INIT_PROJECT_ID='prototype-project')
    deployer.app('prototype-langfuse-web', web, state)
    state['langfuse_url'] = deployer.wait_origin('prototype-langfuse-web')
    web['NEXTAUTH_URL'] = shared['NEXTAUTH_URL'] = state['langfuse_url']
    save_state(path, state)
    deployer.app('prototype-langfuse-web', web, state)
    deployer.wait_services(['prototype-langfuse-web'])
    deployer.wait_health(state['langfuse_url'] + '/api/public/health')
    deployer.wait_langfuse_initialized(state['langfuse_url'], private['LANGFUSE_INIT_PROJECT_PUBLIC_KEY'],
                                      private['LANGFUSE_INIT_PROJECT_SECRET_KEY'])
    deployer.app('prototype-langfuse-worker', dict(shared, LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL='false'), state)
    deployer.wait_services(['prototype-langfuse-worker'])
    deployer.app('prototype-agent', agent_environment(state, ca), state)
    deployer.wait_services(['prototype-agent'])
    state['app_url'] = deployer.wait_origin('prototype-agent')
    deployer.wait_health(state['app_url'] + '/health/ready')
    state['stage'] = 'ready'
    save_state(path, state)
    return {'status': 'ready', 'app_url': state['app_url'], 'langfuse_url': state['langfuse_url'],
            'trace_verification': 'pending', 'build_commit_verification': 'pending'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Create/reconcile only the dedicated tagged new stack.')
    parser.add_argument('--data-only', action='store_true', help='Create and wait for the four data services; do not build applications yet.')
    parser.add_argument('--agent-only', action='store_true', help='Update only the existing owned agent to --branch/--release; preserve all data and Langfuse services.')
    parser.add_argument('--state', type=Path, help='Private state file outside the repository; required for apply.')
    parser.add_argument('--branch', default='main')
    parser.add_argument('--release', required=True, help='Full Git commit SHA, recorded in app telemetry.')
    parser.add_argument('--timeout', type=float, default=1800, help='Total deadline in seconds, including polling every 10 seconds.')
    args = parser.parse_args(argv)
    try:
        require(re.fullmatch(r'[0-9a-f]{40}', args.release) and re.fullmatch(r'[a-zA-Z0-9_./-]+', args.branch), 'Supply a valid full release SHA and branch.')
        require(0 < args.timeout <= 7200, 'Timeout must be between 0 and 7200 seconds.')
        require(not (args.agent_only and args.data_only), '--agent-only cannot be combined with --data-only.')
        require(os.environ.get('AIVEN_API_TOKEN'), 'Set AIVEN_API_TOKEN in the environment.')
        if args.apply:
            require(args.state is not None, '--apply requires --state outside the repository.')
        if args.state:
            require(not args.state.resolve().is_relative_to(Path(__file__).resolve().parents[1]), 'Private deployment state must be outside the repository.')
        state = load_state(args.state)
        if state and not args.agent_only:
            require(state['branch'] == args.branch and state['release'] == args.release, 'Use the original branch/release when resuming this state.')
        options = dict(follow_redirects=False, trust_env=False, verify=True)
        with httpx.Client(headers={'Authorization': 'Bearer ' + os.environ['AIVEN_API_TOKEN']}, **options) as api:
            with httpx.Client(**options) as public:
                deployer = Deployer(api, public, args.timeout)
                if args.agent_only:
                    preflight_agent(deployer, state)
                    if args.apply:
                        result = apply_agent(deployer, state, args.state, args.branch, args.release)
                    else:
                        result = {'status': 'plan', 'services': ['prototype-agent'], 'creates_resources': False,
                                  'agent_source': {'branch': args.branch, 'release': args.release}}
                    print(json.dumps(result))
                    return 0
                deployer.preflight(state)
                if not args.apply:
                    print(json.dumps({'status': 'plan', 'project': PROJECT, 'cloud': CLOUD,
                        'services': list(DATA) + list(APPS), 'creates_resources': True,
                        'credentials_available': all(os.environ.get(k) for k in INPUTS)}))
                    return 0
                if state is None:
                    state = new_state(args, os.environ)
                    save_state(args.state, state)
                result = apply(deployer, state, args.state, args.data_only)
                print(json.dumps(result))
        return 0
    except DeploymentError as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
    except Exception:
        print('FAIL: Unexpected deployment error; details withheld to protect credentials. Resources were preserved.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
