#!/usr/bin/env python3
"""
Tumblr OAuth 1.0a Token Exchange
Run this to get fresh TUMBLR_TOKEN and TUMBLR_TOKEN_SECRET.

Usage:
  python scripts/get_tumblr_tokens.py

Requires TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET in .env
"""

import os
import sys
import webbrowser
from pathlib import Path

# Load .env
env_path = Path("C:/Users/Earth/OneDrive/TowWithTheFlow/.env")
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY", "")
CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")

if not CONSUMER_KEY or not CONSUMER_SECRET:
    print("ERROR: TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET must be set in .env")
    sys.exit(1)

try:
    import requests
    from requests_oauthlib import OAuth1
except ImportError:
    print("ERROR: Install requests and requests-oauthlib first:")
    print("  pip install requests requests-oauthlib")
    sys.exit(1)

REQUEST_TOKEN_URL  = "https://www.tumblr.com/oauth/request_token"
AUTHORIZE_URL      = "https://www.tumblr.com/oauth/authorize"
ACCESS_TOKEN_URL   = "https://www.tumblr.com/oauth/access_token"

print("\n=== Tumblr OAuth 1.0a Token Exchange ===\n")
print(f"Consumer Key:    {CONSUMER_KEY[:8]}...")
print(f"Consumer Secret: {CONSUMER_SECRET[:8]}...\n")

# Step 1: Get request token
oauth_step1 = OAuth1(CONSUMER_KEY, CONSUMER_SECRET)
r = requests.post(REQUEST_TOKEN_URL, auth=oauth_step1, timeout=30)

if r.status_code != 200:
    print(f"ERROR getting request token: {r.status_code} {r.text}")
    sys.exit(1)

params = dict(pair.split('=') for pair in r.text.split('&') if '=' in pair)
request_token    = params.get('oauth_token', '')
request_token_secret = params.get('oauth_token_secret', '')

if not request_token:
    print(f"ERROR: No oauth_token in response: {r.text}")
    sys.exit(1)

print(f"Request token:   {request_token[:20]}...")

# Step 2: Open browser for user authorization
auth_url = f"{AUTHORIZE_URL}?oauth_token={request_token}"
print(f"\nOpening browser to authorize app:")
print(f"  {auth_url}\n")
webbrowser.open(auth_url)

print("After authorizing in the browser, Tumblr will show you a numeric VERIFIER code.")
print("(It may also redirect to a callback URL — look for oauth_verifier in the URL)\n")
verifier = input("Paste the oauth_verifier here: ").strip()

if not verifier:
    print("ERROR: No verifier provided.")
    sys.exit(1)

# Step 3: Exchange for access token
oauth_step3 = OAuth1(
    CONSUMER_KEY, CONSUMER_SECRET,
    request_token, request_token_secret,
    verifier=verifier
)
r2 = requests.post(ACCESS_TOKEN_URL, auth=oauth_step3, timeout=30)

if r2.status_code != 200:
    print(f"\nERROR getting access token: {r2.status_code}")
    print(r2.text)
    sys.exit(1)

params2 = dict(pair.split('=') for pair in r2.text.split('&') if '=' in pair)
access_token        = params2.get('oauth_token', '')
access_token_secret = params2.get('oauth_token_secret', '')

if not access_token:
    print(f"ERROR: No access token in response: {r2.text}")
    sys.exit(1)

print("\n=== SUCCESS! New access tokens: ===\n")
print(f"TUMBLR_TOKEN={access_token}")
print(f"TUMBLR_TOKEN_SECRET={access_token_secret}")
print("\nUpdate your .env file and GitHub secrets with these values.")
print("Then re-run: python scripts/retry_tumblr.py")
