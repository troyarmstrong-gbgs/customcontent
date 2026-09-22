# First-time setup after bootstrap

If you used the service app's **Bootstrap New App** flow, almost
everything is done already — skip to the "Run it" section.

If you cloned this template manually, do the steps below.

## 1. Register the app in the service app

1. Sign into https://sso.cgdata.app
2. Apps → **+ Register App**
3. Fill in the form. For redirect URIs, include both:
   ```
   https://<your-railway-url>/auth/sso/callback
   http://localhost:8000/auth/sso/callback
   ```
4. Copy the displayed `SSO_*` env vars.

## 2. Set env vars on Railway

```
SESSION_SECRET=<run: python3 -c "import secrets; print(secrets.token_urlsafe(48))">
PUBLIC_URL=https://<your-railway-url>
SSO_ISSUER=https://sso.cgdata.app
SSO_AUTHORIZATION_URL=https://sso.cgdata.app/auth/authorize
SSO_JWKS_URL=https://sso.cgdata.app/.well-known/jwks.json
SSO_CLIENT_ID=<from step 1>
SSO_CLIENT_SECRET=<from step 1>
```

> Replace the `SESSION_SECRET` placeholder with a real value — actually
> run the python command and paste the output, don't paste the
> placeholder text.

## 3. Run it

Visit your Railway URL. You should see the welcome page with a
"Sign in with Curiosity Games" button. Click it, get bounced to
`sso.cgdata.app`, sign in with Google, get redirected back signed in.

## Troubleshooting

**"redirect_uri is not registered for this client"**
Check that the URI you added in step 1 is *exactly* what your app
sends. Common slip: missing trailing slash, http vs https.

**"Sign-in failed: no token returned"**
The browser callback page didn't get an `id_token` in the URL fragment.
Usually means the service app rejected the auth (wrong domain, wrong
client). Check the service app's logs.

**JWT verification fails locally**
PyJWKClient caches the JWKS for 1 hour. If the service app rotated its
key, restart your app.
