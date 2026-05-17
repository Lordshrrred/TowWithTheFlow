#!/usr/bin/env python3
"""
Tumblr NPF Diagnostic Test
Tests Tumblr posting with Neue Post Format and prints the FULL response.

Usage:
  python scripts/test_tumblr_npf.py

Prints exact HTTP status, headers, and JSON response body.
"""

import os
import sys
import json
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
TOKEN           = os.getenv("TUMBLR_TOKEN", "")
TOKEN_SECRET    = os.getenv("TUMBLR_TOKEN_SECRET", "")
BLOG_NAME       = os.getenv("TUMBLR_BLOG_NAME", "")

print("=== Tumblr NPF Diagnostic ===")
print(f"Consumer Key:    {CONSUMER_KEY[:8]}..." if CONSUMER_KEY else "Consumer Key:    MISSING")
print(f"Consumer Secret: {CONSUMER_SECRET[:8]}..." if CONSUMER_SECRET else "Consumer Secret: MISSING")
print(f"Token:           {TOKEN[:8]}..." if TOKEN else "Token:           MISSING")
print(f"Token Secret:    {TOKEN_SECRET[:8]}..." if TOKEN_SECRET else "Token Secret:    MISSING")
print(f"Blog Name:       {BLOG_NAME}" if BLOG_NAME else "Blog Name:       MISSING")
print()

if not all([CONSUMER_KEY, CONSUMER_SECRET, TOKEN, TOKEN_SECRET, BLOG_NAME]):
    print("ERROR: Missing credentials. Check .env file.")
    sys.exit(1)

try:
    import requests
    from requests_oauthlib import OAuth1
except ImportError:
    print("ERROR: pip install requests requests-oauthlib")
    sys.exit(1)

# Step 1: Verify credentials work at all
print("--- Step 1: Testing credentials with GET /user/info ---")
oauth = OAuth1(CONSUMER_KEY, CONSUMER_SECRET, TOKEN, TOKEN_SECRET)
r = requests.get("https://api.tumblr.com/v2/user/info", auth=oauth, timeout=30)
print(f"Status: {r.status_code}")
try:
    print(f"Body:   {json.dumps(r.json(), indent=2)[:500]}")
except Exception:
    print(f"Body:   {r.text[:500]}")
print()

if r.status_code != 200:
    print("Credentials don't work at all. Run get_tumblr_tokens.py to refresh.")
    sys.exit(1)

# Step 2: Try NPF post with minimal content
print(f"--- Step 2: NPF POST to /v2/blog/{BLOG_NAME}/posts ---")

npf_payload = {
    "content": [
        {
            "type": "text",
            "text": "Test post from towwiththeflow.com - please ignore"
        }
    ],
    "tags": ["test"],
    "state": "draft",   # draft so it doesn't actually publish
}

print(f"Payload: {json.dumps(npf_payload, indent=2)}")
print()

r2 = requests.post(
    f"https://api.tumblr.com/v2/blog/{BLOG_NAME}/posts",
    auth=oauth,
    json=npf_payload,
    timeout=30
)

print(f"Status:  {r2.status_code}")
print(f"Headers: {dict(r2.headers)}")
print()
try:
    body = r2.json()
    print(f"Body (full):\n{json.dumps(body, indent=2)}")
except Exception:
    print(f"Body (raw): {r2.text}")

print()
if r2.status_code in (200, 201):
    print("SUCCESS - NPF posting works! Update syndicate_post.py state to 'published'.")
else:
    print(f"FAIL - status {r2.status_code}")
    print()
    print("If error code is 8001 (Unauthorized):")
    print("  1. Go to https://www.tumblr.com/oauth/apps")
    print("  2. Find your app and check 'Write' permissions are enabled")
    print("  3. Re-authorize: python scripts/get_tumblr_tokens.py")
    print()
    print("If error is 403 or 404:")
    print("  - Check TUMBLR_BLOG_NAME is your blog's URL name (e.g. 'myblog' not 'myblog.tumblr.com')")
