# WordPress.com OAuth Setup

This repo supports two ways to get a WordPress.com bearer token for direct API work on your own site.

Official docs:
- https://developer.wordpress.com/docs/api/oauth2/

## What To Create In WordPress.com

1. Open the WordPress.com Applications Manager.
2. Create a new application.
3. Set the redirect URI to:

```text
http://localhost:9878/callback
```

4. Copy the client id and client secret.
5. Create a WordPress.com Application Password for your account if you use 2FA.

## Env Vars

Add these to `../TWTF_Feeder/.env` or the repo `.env`:

```env
WORDPRESS_CLIENT_ID=...
WORDPRESS_CLIENT_SECRET=...
WORDPRESS_REDIRECT_URI=http://localhost:9878/callback
WORDPRESS_SCOPE=posts media
WORDPRESS_BLOG=https://towwiththeflowyo.wordpress.com
WORDPRESS_USERNAME=...
WORDPRESS_APPLICATION_PASSWORD=...
```

## Fast Dev Token For Your Own Site

This is the quickest way to let Codex manage your WordPress.com content during development.

```bash
python3 scripts/get_wordpress_oauth_token.py --flow password --write-env
```

That stores:

```env
WORDPRESS_OAUTH2_TOKEN=...
```

## Full OAuth Code Flow

Generate the authorization URL:

```bash
python3 scripts/get_wordpress_oauth_token.py --flow auth-url
```

Authorize in the browser, then paste either the `code` value or the full callback URL:

```bash
python3 scripts/get_wordpress_oauth_token.py --flow exchange --code 'PASTE_CODE_OR_CALLBACK_URL' --write-env
```

## Verify The Token

```bash
python3 scripts/get_wordpress_oauth_token.py --flow verify
```

If verification succeeds, the script prints the authenticated WordPress.com user payload.
