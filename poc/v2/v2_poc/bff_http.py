"""Opt-in Google login HTTP application; Calendar/consent execution stays closed."""
import hashlib
import hmac
from html import escape
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .bff_browser_consent import OfflineBrowserConsent, session_cookie
from .bff_google_login_state import OfflineLoginState
from .bff_google_provider import GoogleProvider
from .bff_offline import application as inert_application

SESSION = '__Host-agency_session'
BINDER = '__Host-agency_oidc_tx'


def clear_cookie(name):
    return name + '=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax'


def cookie(environ, name):
    raw = environ.get('HTTP_COOKIE', '')
    if len(raw) > 8192:
        raise PermissionError()
    # Reject ambiguous duplicate cookies instead of choosing one.
    parts = [p.strip().split('=', 1)[0] for p in raw.split(';')]
    if parts.count(name) > 1:
        raise PermissionError()
    jar = SimpleCookie()
    jar.load(raw)
    return jar[name].value if name in jar else ''


class GoogleLoginApplication:
    def __init__(self, *, store, login, provider, origin, allowed_subject,
                 trusted_proxy_ip=None):
        if not allowed_subject or len(allowed_subject) > 255:
            raise ValueError('explicit allowed Google subject required')
        self.store, self.login, self.provider = store, login, provider
        self.origin, self.subject = origin, allowed_subject
        self.proxy = trusted_proxy_ip

    def __call__(self, env, start_response):
        headers = []
        status, body = '403 Forbidden', 'Request denied'
        try:
            path, method = env.get('PATH_INFO'), env.get('REQUEST_METHOD')
            if path == '/_internal/live' and method in ('GET', 'HEAD'):
                return inert_application(env, start_response)
            secure = env.get('wsgi.url_scheme') == 'https'
            if self.proxy and env.get('REMOTE_ADDR') == self.proxy:
                secure = env.get('HTTP_X_FORWARDED_PROTO') == 'https'
            if not secure or env.get('HTTP_HOST') != urlsplit(self.origin).netloc:
                raise PermissionError()
            if path == '/auth/google/login' and method == 'GET':
                attempt = self.login.begin()
                headers = [('Location', attempt['authorization_url']),
                           ('Set-Cookie', attempt['browser_cookie'])]
                status, body = '303 See Other', ''
            elif path == '/auth/google/callback' and method == 'GET':
                headers = [('Set-Cookie', clear_cookie(BINDER))]
                query = env.get('QUERY_STRING', '')
                if len(query) > 8192:
                    raise PermissionError()
                params = parse_qs(query, keep_blank_values=True, max_num_fields=16)
                if any(len(v) != 1 for v in params.values()):
                    raise PermissionError()
                transaction = self.login.consume(
                    state=params.get('state', [''])[0], browser_binding=cookie(env, BINDER))
                if 'error' in params or not params.get('code'):
                    raise PermissionError()
                identity = self.provider.exchange(code=params['code'][0], transaction=transaction)
                if not hmac.compare_digest(identity.subject, self.subject):
                    raise PermissionError()
                old = cookie(env, SESSION)
                if old:
                    try:
                        self.store.logout(session_token=old)
                    except PermissionError:
                        pass
                session = self.store.create_session(verified_identity=identity)
                headers += [('Set-Cookie', session_cookie(session['session_token'])),
                            ('Location', '/')]
                status, body = '303 See Other', ''
            elif path == '/' and method == 'GET':
                token = cookie(env, SESSION)
                self.store.authenticate(session_token=token)
                csrf = hashlib.sha256(('logout:' + token).encode()).hexdigest()
                status = '200 OK'
                body = ('<!doctype html><title>Agency</title><h1>Signed in</h1>'
                        '<p>Calendar actions are unavailable.</p>'
                        '<form method="post" action="/auth/logout">'
                        '<input type="hidden" name="csrf" value="' + escape(csrf) + '">'
                        '<button type="submit">Log out</button></form>')
            elif path == '/auth/logout' and method == 'POST':
                token = cookie(env, SESSION)
                self.store.authenticate(session_token=token)
                if (env.get('HTTP_ORIGIN') != self.origin or
                        env.get('CONTENT_TYPE') != 'application/x-www-form-urlencoded'):
                    raise PermissionError()
                length = int(env.get('CONTENT_LENGTH', '0'))
                if not 0 < length <= 256:
                    raise PermissionError()
                params = parse_qs(env['wsgi.input'].read(length).decode('ascii'),
                                  keep_blank_values=True, max_num_fields=2)
                expected = hashlib.sha256(('logout:' + token).encode()).hexdigest()
                if len(params.get('csrf', [])) != 1 or not hmac.compare_digest(params['csrf'][0], expected):
                    raise PermissionError()
                self.store.logout(session_token=token)
                headers = [('Set-Cookie', clear_cookie(SESSION)),
                           ('Set-Cookie', clear_cookie(BINDER))]
                status, body = '200 OK', 'Signed out of Agency'
            else:
                status, body = '503 Service Unavailable', 'Route unavailable'
        except (PermissionError, ValueError, TypeError, KeyError):
            status, body = '403 Forbidden', 'Request denied'
        except Exception:
            status, body = '503 Service Unavailable', 'Service unavailable'
        raw = body.encode('utf-8')
        headers += [('Content-Type', 'text/html; charset=utf-8'),
                    ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
                    ('Referrer-Policy', 'no-referrer'), ('X-Content-Type-Options', 'nosniff'),
                    ('X-Frame-Options', 'DENY'),
                    ('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
        start_response(status, headers)
        return [raw]


def configured_application():
    """No credentials/no opt-in retains the original inert application."""
    if os.environ.get('AGENCY_BFF_ENABLE_LOGIN') != '1':
        return inert_application
    os.umask(0o077)
    config = json.loads(Path(os.environ['AGENCY_BFF_CONFIG_FILE']).read_text())
    origin, client = config['origin'], config['client_id']
    store = OfflineBrowserConsent(config['database_path'], oidc_client_id=client,
                                  trusted_origin=origin)
    redirect = origin + '/auth/google/callback'
    login = OfflineLoginState(config['database_path'], client_id=client, redirect_uri=redirect)
    provider = GoogleProvider(client_id=client, client_secret=config['client_secret'],
                              redirect_uri=redirect)
    return GoogleLoginApplication(store=store, login=login, provider=provider,
                                  origin=origin, allowed_subject=config['allowed_subject'],
                                  trusted_proxy_ip=config.get('trusted_proxy_ip'))
