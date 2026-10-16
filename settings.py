import base64
from dataclasses import dataclass
import os
from pathlib import Path
import ssl
from urllib.parse import urlsplit, urlunsplit, urlencode


@dataclass
class Settings:
    database_url: str
    password: str
    session_secret: str
    api_key: str
    local: bool = False
    mode: str = "mock"
    model: str = ""
    model_key: str = ""
    model_base: str = "https://ai.aiven.io/v1"
    langfuse_base: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    trace_content: bool = False
    environment: str = "development"
    release: str = ""

    @classmethod
    def load(cls, env=None, ca_path=Path('/tmp/langgraph-ca.pem')):
        env = os.environ if env is None else env
        for key, size in [('APP_PASSWORD', 16), ('SESSION_SECRET', 32), ('APP_API_KEY', 32)]:
            if len(env.get(key, '')) < size:
                raise ValueError(f'{key} must be at least {size} characters')
        if len({env['APP_PASSWORD'], env['SESSION_SECRET'], env['APP_API_KEY']}) != 3:
            raise ValueError('Generate independent login, session and API secrets')
        local = env.get('LOCAL_DEVELOPMENT', '').lower() == 'true'
        uri = urlsplit(env.get('DATABASE_URL', ''))
        if uri.scheme not in ('postgres', 'postgresql') or not uri.hostname or not uri.port or not uri.username or not uri.password or uri.path in ('', '/'):
            raise ValueError('DATABASE_URL requires a PostgreSQL URI with credentials, host, port and database')
        if local:
            query = {'sslmode': 'disable'}
        else:
            try:
                pem = base64.b64decode(env.get('PG_CA_CERT_BASE64', ''), validate=True).decode('ascii')
                if not pem:
                    raise ValueError('Empty certificate')
                ssl.create_default_context(cadata=pem)
                ca_path.write_text(pem)
                ca_path.chmod(0o600)
            except (ValueError, UnicodeError, ssl.SSLError) as exc:
                raise ValueError('PG_CA_CERT_BASE64 must contain a valid base64 PEM CA') from exc
            query = {'sslmode': 'verify-full', 'sslrootcert': str(ca_path)}
        db = urlunsplit(('postgresql', uri.netloc, uri.path, urlencode(query), ''))
        mode = env.get('MODEL_MODE', 'mock')
        if mode not in ('mock', 'openai-compatible'):
            raise ValueError('MODEL_MODE must be mock or openai-compatible')
        model, key = env.get('MODEL_NAME', ''), env.get('MODEL_API_KEY', '')
        base = env.get('MODEL_BASE_URL', 'https://ai.aiven.io/v1').rstrip('/')
        target = urlsplit(base)
        if mode != 'mock' and (not model or not key or target.scheme != 'https' or not target.hostname or target.username or target.query or target.fragment):
            raise ValueError('Real model mode requires MODEL_NAME, MODEL_API_KEY and an HTTPS MODEL_BASE_URL')
        lf_base = env.get('LANGFUSE_BASE_URL', '').rstrip('/')
        lf_public = env.get('LANGFUSE_PUBLIC_KEY', '')
        lf_secret = env.get('LANGFUSE_SECRET_KEY', '')
        if any((lf_base, lf_public, lf_secret)):
            target = urlsplit(lf_base)
            local_http = local and target.scheme == 'http' and target.hostname in ('localhost', '127.0.0.1')
            if (not all((lf_base, lf_public, lf_secret)) or not target.hostname
                    or (target.scheme != 'https' and not local_http)
                    or target.username or target.password or target.query or target.fragment or target.path):
                raise ValueError('Langfuse requires an explicit HTTPS origin and both project keys (local loopback HTTP is allowed)')
        return cls(db, env['APP_PASSWORD'], env['SESSION_SECRET'], env['APP_API_KEY'], local, mode, model, key, base,
                   lf_base, lf_public, lf_secret, env.get('TRACE_CONTENT', '').lower() == 'true',
                   env.get('APP_ENVIRONMENT', 'development'), env.get('APP_RELEASE', ''))
