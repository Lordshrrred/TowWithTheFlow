"""
One-time script to obtain a Blogger API refresh token.

Usage:
    pip install google-auth-oauthlib python-dotenv
    python scripts/get_blogger_token.py

After running, copy the printed refresh token into your .env file as:
    BLOGGER_REFRESH_TOKEN=<token>

Requires http://localhost:8080/ to be registered as an authorized
redirect URI in your Google Cloud Console OAuth2 credentials.
If port 8080 is unavailable, the script falls back to OOB mode
where Google displays the auth code on-screen for you to paste.
"""

import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/blogger"]

load_dotenv()

client_id = os.getenv("BLOGGER_CLIENT_ID")
client_secret = os.getenv("BLOGGER_CLIENT_SECRET")

if not client_id or not client_secret:
    raise SystemExit("ERROR: BLOGGER_CLIENT_ID and BLOGGER_CLIENT_SECRET must be set in .env")

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/", "urn:ietf:wg:oauth:2.0:oob"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

# Primary: localhost:8080 — Google redirects back here automatically.
# Fallback: OOB — Google shows the code on-screen; user pastes it in.
try:
    print("\nStarting local server on http://localhost:8080/ ...")
    credentials = flow.run_local_server(port=8080)
except OSError:
    print("Port 8080 unavailable. Falling back to OOB flow.")
    print("Google will display an authorization code on-screen — copy and paste it here.\n")
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("Open this URL in your browser and authorize:\n")
    print(auth_url + "\n")
    code = input("Paste the authorization code here: ").strip()
    flow.fetch_token(code=code)
    credentials = flow.credentials

print("\n" + "=" * 60)
print("SUCCESS! Add this to your .env file:")
print("=" * 60)
print(f"BLOGGER_REFRESH_TOKEN={credentials.refresh_token}")
print("=" * 60 + "\n")
