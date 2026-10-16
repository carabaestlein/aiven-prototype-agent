from argparse import Namespace
import json
import os

import httpx
import pytest

from scripts import deploy_runtime as deploy


def state():
    return {'version': 1, 'project': deploy.PROJECT, 'owner': 'test-owner',
            'branch': 'main', 'release': 'a' * 40, 'values': {}}


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_data_only_creates_exact_new_services_and_resumes_without_duplicates(tmp_path):
    services, requests = {}, []

    def respond(request):
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.method == 'POST':
            name = body['service_name']
            services[name] = dict(body, state='RUNNING', cloud_name=body['cloud'])
            return httpx.Response(200, json={'service': services[name]})
        name = request.url.path.rsplit('/', 1)[-1]
        return httpx.Response(200, json={'service': services[name]}) if name in services else httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(respond)) as api:
        runner = deploy.Deployer(api, api)
        private = state()
        first = deploy.apply(runner, private, tmp_path / 'state.json', data_only=True)
        second = deploy.apply(runner, private, tmp_path / 'state.json', data_only=True)
    assert first == second and first['status'] == 'data_ready'
    creates = [body for method, _, body in requests if method == 'POST']
    assert {body['service_name'] for body in creates} == set(deploy.DATA)
    assert len(creates) == 4
    assert all(body['tags'] == {'prototype_step1': 'test-owner'} for body in creates)
    assert all('prototype-' in path for method, path, _ in requests if method != 'POST')
    assert (tmp_path / 'state.json').stat().st_mode & 0o077 == 0


def test_existing_service_with_wrong_owner_is_never_modified():
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json={'service': {'tags': {'prototype_step1': 'someone-else'}}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as api:
        with pytest.raises(deploy.DeploymentError, match='ownership'):
            deploy.Deployer(api, api).ensure_service('prototype-agent-pg', 'pg', 'startup-4', {}, state())
    assert calls == ['GET']


def test_errors_do_not_disclose_response_or_connection_details():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(403, text='secret-token-value'))) as api:
        with pytest.raises(deploy.DeploymentError) as caught:
            deploy.Deployer(api, api).call('POST', '/test', {'secret': 'request-secret'})
    assert str(caught.value) == 'Aiven returned HTTP 403; response body withheld.'

    def fail(request):
        raise httpx.ConnectError('secret-token-value')

    with httpx.Client(transport=httpx.MockTransport(fail)) as api:
        with pytest.raises(deploy.DeploymentError) as caught:
            deploy.Deployer(api, api).call('GET', '/test')
    assert 'secret-token-value' not in str(caught.value)


def test_wait_deadline_is_global_and_bounded():
    clock = Clock()
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'service': {'state': 'REBUILDING'}}))) as api:
        runner = deploy.Deployer(api, api, timeout=21, monotonic=clock.monotonic, sleep=clock.sleep)
        with pytest.raises(deploy.DeploymentError, match='timed out'):
            runner.wait_services(['prototype-agent-pg'])
    assert clock.now == 21


def test_stable_secrets_are_private_and_preserved_on_read(tmp_path):
    inputs = {key: 'test-only-value' for key in deploy.INPUTS}
    inputs['S3_ENDPOINT'] = 'https://storage.example.test'
    initial = deploy.new_state(Namespace(branch='main', release='a' * 40), inputs)
    path = tmp_path / 'private.json'
    deploy.save_state(path, initial)
    assert deploy.load_state(path) == initial
    assert len({initial['values'][key] for key in ('APP_PASSWORD', 'APP_API_KEY', 'SESSION_SECRET')}) == 3
    os.chmod(path, 0o644)
    with pytest.raises(deploy.DeploymentError, match='0600'):
        deploy.load_state(path)


def test_state_save_ignores_a_stale_fixed_temporary_file(tmp_path):
    path = tmp_path / 'private.json'
    stale = tmp_path / 'private.json.tmp'
    stale.write_text('previous interrupted write')
    deploy.save_state(path, state())
    assert deploy.load_state(path) == state()
    assert stale.read_text() == 'previous interrupted write'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['private.json', 'private.json.tmp']


def test_public_source_and_full_environment_keep_credentials_out_of_source():
    calls = []

    def respond(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, body))
        if request.method == 'GET':
            return httpx.Response(404)
        return httpx.Response(200, json={'service': {'service_uri': 'https://agent.example.test'}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as api:
        deploy.Deployer(api, api).app('prototype-agent', {'APP_API_KEY': 'stable-secret', 'MODEL_MODE': 'openai-compatible'}, state())
    body = next(body for method, body in calls if method == 'POST')
    app = body['user_config']['application']
    assert app['source'] == {'repository_url': deploy.REPOSITORY, 'branch': 'main', 'build_path': './', 'containerfile_path': './Dockerfile'}
    assert app['environment_variables'][0] == {'key': 'APP_API_KEY', 'value': 'stable-secret', 'kind': 'secret'}
    assert 'stable-secret' not in json.dumps(app['source'])
    assert body['service_integrations'][0]['source_service'] == 'prototype-agent-pg'


def test_clickhouse_absent_ssl_metadata_uses_tls_and_preserves_raw_password():
    service = {'components': [{'component': name, 'host': 'db.example.test', 'port': port, 'route': 'dynamic'}
                              for name, port in [('clickhouse_https', 12345), ('clickhouse', 12346)]],
               'service_uri_params': {'user': 'raw%40user', 'password': 'raw%2Fpassword'}}
    values = deploy.clickhouse_settings(service)
    assert values['CLICKHOUSE_URL'] == 'https://db.example.test:12345'
    assert values['CLICKHOUSE_MIGRATION_URL'] == 'clickhouse://db.example.test:12346'
    assert values['CLICKHOUSE_USER'] == 'raw%40user'
    assert values['CLICKHOUSE_PASSWORD'] == 'raw%2Fpassword'
    service['components'][0]['ssl'] = False
    with pytest.raises(deploy.DeploymentError, match='TLS endpoints'):
        deploy.clickhouse_settings(service)


def test_full_flow_waits_for_web_before_worker_and_shares_stable_configuration(tmp_path):
    events, apps = [], {}
    inputs = {key: 'private-test-value' for key in deploy.INPUTS}
    inputs['S3_ENDPOINT'] = 'https://storage.example.test'
    private = deploy.new_state(Namespace(branch='main', release='a' * 40), inputs)
    private['agent_source'] = {'branch': 'release/ui-refresh', 'release': 'b' * 40}

    class Stub:
        def ensure_service(self, name, *args):
            events.append(('data', name))

        def wait_services(self, names):
            events.append(('ready', tuple(names)))
            return {name: {'service_uri': 'https://agent.example.test', 'components': [
                {'component': 'clickhouse_https', 'host': 'db.example.test', 'port': 12001, 'route': 'dynamic'},
                {'component': 'clickhouse', 'host': 'db.example.test', 'port': 12002, 'route': 'dynamic'}],
                'service_uri_params': {'user': 'test-user', 'password': 'private-db-password'}} for name in names}

        def call(self, method, path, body=None):
            return {'certificate': 'test-ca'} if path.endswith('/ca') else {'databases': [{'name': 'langfuse', 'state': 'ok'}]}

        def app(self, name, values, state):
            events.append(('app', name))
            apps[name] = dict(values)

        def wait_origin(self, name):
            return 'https://langfuse.example.test' if name.endswith('web') else 'https://agent.example.test'

        def wait_health(self, url):
            events.append(('health', url))

        def wait_langfuse_initialized(self, url, public_key, secret_key):
            assert public_key == private['values']['LANGFUSE_INIT_PROJECT_PUBLIC_KEY']
            assert secret_key == private['values']['LANGFUSE_INIT_PROJECT_SECRET_KEY']
            events.append(('initialized', url))

    result = deploy.apply(Stub(), private, tmp_path / 'private.json')
    assert events.index(('ready', tuple(deploy.DATA))) < events.index(('app', 'prototype-langfuse-web'))
    assert events.index(('health', 'https://langfuse.example.test/api/public/health')) < events.index(('app', 'prototype-langfuse-worker'))
    assert events.index(('initialized', 'https://langfuse.example.test')) < events.index(('app', 'prototype-langfuse-worker'))
    assert events.index(('ready', ('prototype-langfuse-worker',))) < events.index(('app', 'prototype-agent'))
    for key in ('SALT', 'ENCRYPTION_KEY', 'S3_SECRET_ACCESS_KEY', 'NEXTAUTH_URL', 'CLICKHOUSE_PASSWORD'):
        assert apps['prototype-langfuse-web'][key] == apps['prototype-langfuse-worker'][key]
    assert apps['prototype-agent']['LANGFUSE_SECRET_KEY'] == private['values']['LANGFUSE_INIT_PROJECT_SECRET_KEY']
    assert apps['prototype-agent']['APP_API_KEY'] == private['values']['APP_API_KEY']
    assert apps['prototype-agent']['APP_RELEASE'] == 'b' * 40
    assert result['status'] == 'ready' and 'private' not in json.dumps(result)


def test_runtime_origin_uses_observed_edge_hostname_without_internal_port():
    service = {'service_uri': 'prototype-langfuse-web-cara-test.b.aivencloud.com:',
               'components': [{'component': 'http', 'host': '01a143e8-a09e-70b1-9170-21575e8e407f-8080.eur-1.aiven.app',
                               'port': 8080, 'route': 'public'}]}
    assert deploy.runtime_origin(service) == 'https://01a143e8-a09e-70b1-9170-21575e8e407f-8080.eur-1.aiven.app'
    assert ':8080' not in deploy.runtime_origin(service)


@pytest.mark.parametrize('uri', [None, '', 'legacy-host:', 'http://host.test',
                               'https://user:secret@host.test', 'https://host.test/path',
                               'https://host.test?secret=value'])
def test_runtime_origin_waits_when_no_valid_public_endpoint_is_allocated(uri):
    assert deploy.runtime_origin({'service_uri': uri}) is None


def test_runtime_origin_https_fallback_and_rejection_of_malformed_component():
    assert deploy.runtime_origin({'service_uri': 'https://valid.example.test/'}) == 'https://valid.example.test'
    service = {'service_uri': 'https://valid.example.test', 'components': [
        {'component': 'http', 'host': 'host.test:8080', 'route': 'public'}]}
    with pytest.raises(deploy.DeploymentError, match='hostname'):
        deploy.runtime_origin(service)


def test_runtime_endpoint_allocation_wait_is_bounded_and_reads_new_components():
    clock, requests = Clock(), []
    def respond(request):
        requests.append(request)
        service = {} if len(requests) == 1 else {'components': [
            {'component': 'http', 'host': 'edge.example.test', 'route': 'public', 'port': 8080}]}
        return httpx.Response(200, json={'service': service})
    with httpx.Client(transport=httpx.MockTransport(respond)) as api:
        runner = deploy.Deployer(api, api, timeout=20, monotonic=clock.monotonic, sleep=clock.sleep)
        assert runner.wait_origin('prototype-agent') == 'https://edge.example.test'
    assert len(requests) == 2 and clock.now == 10


def providers(origin='https://langfuse.example.test'):
    return {'credentials': {'signinUrl': origin + '/api/auth/signin/credentials',
                            'callbackUrl': origin + '/api/auth/callback/credentials'}}


def test_langfuse_initialization_waits_for_new_origin_and_uses_project_auth_only_there():
    clock, requests = Clock(), []
    def respond(request):
        requests.append(request)
        if request.url.path == '/api/auth/providers':
            assert 'authorization' not in request.headers
            return httpx.Response(200, json=providers('https://pending.invalid') if len(requests) == 1 else providers())
        assert request.url.path == '/api/public/projects'
        assert request.headers['Authorization'] == httpx.BasicAuth('public-test-key', 'secret-test-key')._auth_header
        return httpx.Response(200, json={'data': [{'id': 'prototype-project'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        runner = deploy.Deployer(client, client, timeout=30, monotonic=clock.monotonic, sleep=clock.sleep)
        runner.wait_langfuse_initialized('https://langfuse.example.test', 'public-test-key', 'secret-test-key')
    assert len(requests) == 3 and clock.now == 10


def test_langfuse_initialization_retries_project_key_readiness():
    clock, project_calls = Clock(), []
    def respond(request):
        if request.url.path.endswith('/providers'):
            return httpx.Response(200, json=providers())
        project_calls.append(request)
        return httpx.Response(401, text='private-error') if len(project_calls) == 1 else httpx.Response(
            200, json={'data': [{'id': 'prototype-project'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        runner = deploy.Deployer(client, client, timeout=30, monotonic=clock.monotonic, sleep=clock.sleep)
        runner.wait_langfuse_initialized('https://langfuse.example.test', 'public', 'secret')
    assert len(project_calls) == 2 and clock.now == 10


@pytest.mark.parametrize('provider_payload,project_payload', [
    ({}, {'data': [{'id': 'prototype-project'}]}),
    (providers('https://pending.invalid'), {'data': [{'id': 'prototype-project'}]}),
    (providers(), {'data': [{'id': 'wrong-project'}]}),
    ({'credentials': {'signinUrl': 'https://langfuse.example.test/api/auth/signin',
                      'callbackUrl': 'https://pending.invalid/api/auth/callback'}}, {'data': [{'id': 'prototype-project'}]}),
])
def test_langfuse_initialization_never_accepts_partial_or_mismatched_state(provider_payload, project_payload):
    clock = Clock()
    def respond(request):
        return httpx.Response(200, json=provider_payload if request.url.path.endswith('/providers') else project_payload)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        runner = deploy.Deployer(client, client, timeout=21, monotonic=clock.monotonic, sleep=clock.sleep)
        with pytest.raises(deploy.DeploymentError, match='timed out'):
            runner.wait_langfuse_initialized('https://langfuse.example.test', 'public', 'secret')
    assert clock.now == 21


def test_langfuse_initialization_rejects_redirect_without_forwarding_project_keys():
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.path.endswith('/providers'):
            return httpx.Response(200, json=providers())
        return httpx.Response(307, headers={'Location': 'https://elsewhere.example.test'}, text='secret-response')
    with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False) as client:
        with pytest.raises(deploy.DeploymentError, match='redirected') as caught:
            deploy.Deployer(client, client).wait_langfuse_initialized('https://langfuse.example.test', 'public', 'secret')
    assert len(requests) == 2 and all(r.url.host == 'langfuse.example.test' for r in requests)
    assert 'secret-response' not in str(caught.value)


def agent_state():
    inputs = {key: 'private-test-value' for key in deploy.INPUTS}
    inputs['S3_ENDPOINT'] = 'https://storage.example.test'
    private = deploy.new_state(Namespace(branch='release/step1', release='a' * 40), inputs)
    private['langfuse_url'] = 'https://langfuse.example.test'
    return private


def test_agent_only_rebuild_preserves_secrets_and_never_mutates_dependencies(tmp_path):
    private, requests = agent_state(), []
    initial_values = dict(private['values'])
    service = {'tags': {'prototype_step1': private['owner']}, 'service_type': 'application',
               'cloud_name': deploy.CLOUD, 'plan': deploy.APPS['prototype-agent'][0], 'state': 'RUNNING',
               'service_uri': 'https://agent.example.test', 'user_config': {'application': {
                   'source': {'branch': 'release/step1'},
                   'environment_variables': [{'key': key, 'value': '<redacted>'} for key in initial_values]}}}

    def respond(request):
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.url.path.endswith('/kms/ca'):
            return httpx.Response(200, json={'certificate': 'test-ca'})
        if request.url.path == '/health/ready':
            return httpx.Response(200)
        if request.method == 'PUT':
            service['user_config'] = body['user_config']
        if request.method == 'POST':
            assert request.url.path.endswith('/prototype-agent/application/redeploy')
            return httpx.Response(204)
        return httpx.Response(200, json={'service': service})

    path = tmp_path / 'private.json'
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        runner = deploy.Deployer(client, client)
        result = deploy.apply_agent(runner, private, path, 'release/ui-refresh', 'b' * 40)
        # Explicit retries rebuild even when the selected branch has not changed.
        deploy.apply_agent(runner, deploy.load_state(path), path, 'release/ui-refresh', 'b' * 40)
    mutations = [(method, url, body) for method, url, body in requests if method != 'GET']
    assert all('/service/prototype-agent' in url for _, url, _ in mutations)
    assert len([1 for method, _, _ in mutations if method == 'POST']) == 2
    app = next(body['user_config']['application'] for method, _, body in mutations if method == 'PUT')
    env = {entry['key']: entry['value'] for entry in app['environment_variables']}
    assert app['source']['branch'] == 'release/ui-refresh'
    assert env['APP_RELEASE'] == 'b' * 40
    for key in ('APP_PASSWORD', 'APP_API_KEY', 'SESSION_SECRET', 'MODEL_API_KEY'):
        assert env[key] == initial_values[key]
    assert env['LANGFUSE_SECRET_KEY'] == initial_values['LANGFUSE_INIT_PROJECT_SECRET_KEY']
    assert '<redacted>' not in env.values() and 'DATABASE_URL' not in env
    saved = deploy.load_state(path)
    assert saved['values'] == initial_values
    assert saved['branch'] == 'release/step1' and saved['release'] == 'a' * 40
    assert saved['agent_source'] == {'branch': 'release/ui-refresh', 'release': 'b' * 40}
    assert result['build_commit_verification'] == 'pending'


@pytest.mark.parametrize('existing', [None, {'tags': {'prototype_step1': 'someone-else'}}])
def test_agent_only_missing_or_unowned_service_never_writes_state_or_creates_resources(tmp_path, existing):
    requests = []
    def respond(request):
        requests.append(request.method)
        return httpx.Response(404) if existing is None else httpx.Response(200, json={'service': existing})
    path = tmp_path / 'private.json'
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(deploy.DeploymentError):
            deploy.apply_agent(deploy.Deployer(client, client), agent_state(), path, 'release/ui-refresh', 'b' * 40)
    assert requests == ['GET'] and not path.exists()


def test_agent_only_plan_accepts_new_release_and_does_not_write(monkeypatch, tmp_path, capsys):
    private, requests = agent_state(), []
    path = tmp_path / 'private.json'
    deploy.save_state(path, private)
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'service': {
            'tags': {'prototype_step1': private['owner']}, 'service_type': 'application',
            'cloud_name': deploy.CLOUD, 'plan': deploy.APPS['prototype-agent'][0]}})
    original_client = httpx.Client
    monkeypatch.setattr(deploy.httpx, 'Client', lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setenv('AIVEN_API_TOKEN', 'private-test-token')
    assert deploy.main(['--agent-only', '--state', str(path), '--branch', 'release/ui-refresh',
                        '--release', 'b' * 40]) == 0
    assert len(requests) == 1 and requests[0].method == 'GET'
    assert requests[0].url.path.endswith('/service/prototype-agent')
    assert deploy.load_state(path) == private
    output = json.loads(capsys.readouterr().out)
    assert output['creates_resources'] is False and output['services'] == ['prototype-agent']
