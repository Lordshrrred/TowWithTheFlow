#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "scripts" / "platform_health.json"
ALERT_TO = "earthlingoflight@gmail.com"
WORDPRESS_TOKEN_INFO_URL = "https://public-api.wordpress.com/oauth2/token-info"
WRITE_PROBE_TITLE = "TWTF Blogger Health Check Draft"
WRITE_PROBE_CONTENT = "<p>Temporary unpublished draft created by health check.</p>"


def env_clean(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if not isinstance(val, str):
        return default
    val = val.strip()
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
        val = val[1:-1].strip()
    prefix = f"{key}="
    if val.startswith(prefix):
        val = val[len(prefix):].strip()
    export_prefix = f"export {key}="
    if val.startswith(export_prefix):
        val = val[len(export_prefix):].strip()
    return val


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except Exception:
        pass


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def send_alert(subject: str, body: str, gmail_address: str, gmail_app_password: str) -> bool:
    if not gmail_address or not gmail_app_password:
        return False
    msg = MIMEText(body, "plain")
    msg["From"] = gmail_address
    msg["To"] = ALERT_TO
    msg["Subject"] = subject
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, ALERT_TO, msg.as_string())
        return True
    except Exception:
        return False


def should_alert(state: dict, now: datetime, unhealthy_count: int) -> bool:
    if unhealthy_count == 0:
        return False
    last = state.get("last_alert_at", "")
    prev = int(state.get("unhealthy_count", 0) or 0)
    if prev == 0:
        return True
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return now - last_dt >= timedelta(hours=12)


def check_devto() -> dict:
    key = env_clean("DEVTO_API_KEY")
    if not key:
        return {"status": "missing", "detail": "DEVTO_API_KEY missing"}
    try:
        r = requests.get("https://dev.to/api/articles/me/published", headers={"api-key": key}, timeout=20)
        if r.ok:
            return {"status": "healthy"}
        return {"status": "unhealthy", "detail": f"HTTP {r.status_code}: {r.text[:180]}"}
    except Exception as e:
        return {"status": "unhealthy", "detail": str(e)}


def check_tumblr() -> dict:
    try:
        from requests_oauthlib import OAuth1
    except Exception:
        return {"status": "missing", "detail": "requests-oauthlib unavailable"}

    creds = {
        "consumer_key": env_clean("TUMBLR_CONSUMER_KEY"),
        "consumer_secret": env_clean("TUMBLR_CONSUMER_SECRET"),
        "token": env_clean("TUMBLR_TOKEN"),
        "token_secret": env_clean("TUMBLR_TOKEN_SECRET"),
        "blog": env_clean("TUMBLR_BLOG_NAME"),
    }
    if not all(creds.values()):
        return {"status": "missing", "detail": "Tumblr credentials missing"}
    try:
        oauth = OAuth1(creds["consumer_key"], creds["consumer_secret"], creds["token"], creds["token_secret"])
        r = requests.get(f"https://api.tumblr.com/v2/blog/{creds['blog']}/info", auth=oauth, timeout=20)
        if r.ok:
            return {"status": "healthy"}
        return {"status": "unhealthy", "detail": f"HTTP {r.status_code}: {r.text[:180]}"}
    except Exception as e:
        return {"status": "unhealthy", "detail": str(e)}


def blogger_write_probe(access_token: str, blog_id: str) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    create = requests.post(
        f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/",
        params={"isDraft": "true"},
        headers=headers,
        json={"title": WRITE_PROBE_TITLE, "content": WRITE_PROBE_CONTENT, "labels": ["health-check"]},
        timeout=20,
    )
    if not create.ok:
        return False, f"draft create HTTP {create.status_code}: {(create.text or '')[:180]}"

    post_id = str(create.json().get("id", "")).strip()
    if not post_id:
        return False, "draft create succeeded but response had no post id"

    delete = requests.delete(
        f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/{post_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if not delete.ok:
        return False, f"draft delete HTTP {delete.status_code}: {(delete.text or '')[:180]}"

    return True, ""


def check_blogger() -> dict:
    cid = env_clean("BLOGGER_CLIENT_ID")
    csec = env_clean("BLOGGER_CLIENT_SECRET")
    rtok = env_clean("BLOGGER_REFRESH_TOKEN")
    blog_id = env_clean("BLOGGER_BLOG_ID")
    if not all([cid, csec, rtok, blog_id]):
        return {"status": "missing", "detail": "Blogger credentials missing"}
    try:
        tr = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"client_id": cid, "client_secret": csec, "refresh_token": rtok, "grant_type": "refresh_token"},
            timeout=20,
        )
        tdata = tr.json()
        access = tdata.get("access_token", "")
        if not access:
            return {"status": "unhealthy", "detail": str(tdata)[:180]}
        ok, detail = blogger_write_probe(access, blog_id)
        if ok:
            return {"status": "healthy"}
        return {"status": "unhealthy", "detail": detail}
    except Exception as e:
        return {"status": "unhealthy", "detail": str(e)}


def check_wordpress() -> dict:
    client_id = env_clean("WORDPRESS_CLIENT_ID")
    token = env_clean("WORDPRESS_OAUTH2_TOKEN")
    if not client_id or not token:
        return {"status": "missing", "detail": "WordPress client/token missing"}
    try:
        r = requests.get(
            WORDPRESS_TOKEN_INFO_URL,
            params={"client_id": client_id, "token": token},
            timeout=20,
        )
        if r.ok:
            return {"status": "healthy", "detail": r.text[:180]}
        return {"status": "unhealthy", "detail": f"HTTP {r.status_code}: {r.text[:180]}"}
    except Exception as e:
        return {"status": "unhealthy", "detail": str(e)}


def check_feeder() -> dict:
    token = env_clean("FEEDER_TRIGGER_TOKEN") or env_clean("GITHUB_TOKEN")
    if not token:
        return {"status": "missing", "detail": "Feeder token missing"}
    try:
        r = requests.get(
            "https://api.github.com/repos/Lordshrrred/TWTF_Feeder",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            timeout=20,
        )
        if r.ok:
            return {"status": "healthy"}
        return {"status": "unhealthy", "detail": f"HTTP {r.status_code}: {r.text[:180]}"}
    except Exception as e:
        return {"status": "unhealthy", "detail": str(e)}


def main() -> int:
    load_env()
    now = datetime.now(timezone.utc)
    gmail_address = env_clean("GMAIL_ADDRESS")
    gmail_app_password = env_clean("GMAIL_APP_PASSWORD")
    checks = {
        "devto": check_devto(),
        "tumblr": check_tumblr(),
        "blogger": check_blogger(),
        "wordpress": check_wordpress(),
        "feeder": check_feeder(),
    }
    unhealthy = {k: v for k, v in checks.items() if v.get("status") == "unhealthy"}
    state = load_state()
    alert_sent = False
    if should_alert(state, now, len(unhealthy)):
        body = "\n".join(f"{name}: {info.get('detail', info.get('status'))}" for name, info in checks.items())
        alert_sent = send_alert(
            subject=f"TWTF Platform Health: {len(unhealthy)} unhealthy",
            body=f"UTC: {now.isoformat()}\n\n{body}",
            gmail_address=gmail_address,
            gmail_app_password=gmail_app_password,
        )

    snapshot = {
        "checked_at": now.isoformat(),
        "checks": checks,
        "unhealthy_count": len(unhealthy),
        "last_alert_at": now.isoformat() if alert_sent else state.get("last_alert_at", ""),
    }
    save_state(snapshot)
    print(json.dumps(snapshot, indent=2))
    return 0 if not unhealthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
