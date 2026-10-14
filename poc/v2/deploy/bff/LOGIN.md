# Google login integration (experimental, opt-in)

The image defaults to the inert application. No deployment or public route is
created by this change. The new HTTP application is a login-only staging slice;
Calendar and consent endpoints still fail closed. Logout revokes the local
session and pending local consent. It does not log out Google or propagate to
the separate approval issuer; no approval issuance is exposed here.

## Private runtime configuration

An operator must supply a protected JSON file outside Git, readable by UID
10001, set `AGENCY_BFF_ENABLE_LOGIN=1` and `AGENCY_BFF_CONFIG_FILE` to its mounted
path, and mount a private writable directory for SQLite. Keep the existing
read-only container, dropped capabilities and loopback-only host port.
The JSON requires `origin` (exact HTTPS origin with no port/path), `client_id`,
`client_secret`, `allowed_subject` (independently established Google `sub`, not
email or a first-login enrollment), and `database_path` (inside that volume).
Do not paste secrets in chat, logs, Docker build args, or committed examples.

Only `/auth/google/callback` on the exact origin is a callback. Register that
exact URI in the Google web OAuth client. The optional `trusted_proxy_ip` must
be the exact source IP of an independently controlled HTTPS reverse proxy;
only that peer's `X-Forwarded-Proto: https` is accepted. Host must match the
configured origin. Arbitrary forwarding/Cloudflare identity headers do not
establish identity. Keep access/query logging disabled at the proxy as well.
The standard-library listener remains a private staging server, not a hardened
public production server. Do not add a public tunnel before deployment review.

## Behavior and verification

Google's fixed discovery URL is fetched with certificate/hostname-verified TLS.
Issuer and authorization/token/JWKS endpoints must match the pinned Google
URLs. Fresh JWKS are fetched on every exchange; no stale cache or token-supplied
key URL is used. Redirects, oversized responses, invalid keys and network errors
fail closed. Code exchange sends the original redirect URI, confidential client
secret and PKCE verifier exactly once. ID token signature, nonce, issuer,
audience and time checks run before the subject allowlist and session creation.
Access/refresh tokens are discarded; this is not Calendar authorization.

Routes: GET `/auth/google/login`, GET `/auth/google/callback`, protected GET `/`,
and Origin/CSRF/session-protected POST `/auth/logout`. Successful callbacks
rotate the session; cookies are host-only Secure HttpOnly SameSite=Lax. Local
sessions last at most 15 minutes and never beyond the ID token expiry.

CI builds the image, validates Compose, runs signed fictional-provider HTTP
regressions inside the non-root/read-only image, and starts the default inert
container to verify its response and isolation configuration. This is not a
live Google login, browser-cookie interoperability test, image vulnerability
scan or deployment proof. The base digest is pinned to the image resolved by CI.

Private live acceptance still requires: open the login route in a real browser,
complete Google sign-in with the allowed account, confirm the protected page,
log out, verify refresh/back/replayed session no longer grants access, reject a
different Google account, and inspect expiry and proxy/TLS behavior. Record only
redacted pass/fail evidence and commit identity, never codes/tokens/cookies.

Provider protocol reference:
https://developers.google.com/identity/openid-connect/openid-connect
