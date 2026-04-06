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
LOG_FILE = ROOT / "scripts" / "syndication_log.txt"
STATE_FILE = ROOT / "scripts" / "blogger_health.json"
ALERT_TO = "earthlingoflight@gmail.com"


def env_clean(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if not isinstance(val, str):
        return default
    val = val.strip()
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
        val = val[1:-1].strip()
    return val


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] BLOGGER_HEALTH | {msg}\n"
    print(line, end="", flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)


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
        log("ALERT | skipped email (missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD)")
        return False
    msg = MIMEText(body, "plain")
    msg["From"] = gmail_address
    msg["To"] = ALERT_TO
    msg["Subject"] = subject
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, ALERT_TO, msg.as_string())
        log(f"ALERT | email sent to {ALERT_TO}")
        return True
    except Exception as e:
        log(f"ALERT | FAILED to send email: {e}")
        return False


def should_send_alert(state: dict, now: datetime, status: str) -> bool:
    prev_status = state.get("status")
    last_alert_at = state.get("last_alert_at", "")

    if status == "healthy":
        return False

    # Always alert on transition from healthy/unknown -> unhealthy.
    if prev_status != "unhealthy":
        return True

    # If still unhealthy, remind at most once every 24 hours.
    if not last_alert_at:
        return True
    try:
        last = datetime.fromisoformat(last_alert_at)
    except Exception:
        return True
    return now - last >= timedelta(hours=24)


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=True)
    except Exception:
        pass

    cid = env_clean("BLOGGER_CLIENT_ID")
    csec = env_clean("BLOGGER_CLIENT_SECRET")
    rtok = env_clean("BLOGGER_REFRESH_TOKEN")
    blog_id = env_clean("BLOGGER_BLOG_ID")
    gmail_address = env_clean("GMAIL_ADDRESS")
    gmail_app_password = env_clean("GMAIL_APP_PASSWORD")

    now = datetime.now(timezone.utc)
    state = load_state()

    missing = [
        k
        for k, v in [
            ("BLOGGER_CLIENT_ID", cid),
            ("BLOGGER_CLIENT_SECRET", csec),
            ("BLOGGER_REFRESH_TOKEN", rtok),
            ("BLOGGER_BLOG_ID", blog_id),
        ]
        if not v
    ]

    status = "healthy"
    reason = "ok"
    detail = ""

    if missing:
        status = "unhealthy"
        reason = "missing_credentials"
        detail = ", ".join(missing)
    else:
        try:
            tr = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": cid,
                    "client_secret": csec,
                    "refresh_token": rtok,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
            tdata = tr.json()
            access = tdata.get("access_token", "")
            if not access:
                status = "unhealthy"
                reason = str(tdata.get("error", "token_refresh_failed"))
                detail = str(tdata.get("error_description", "no description"))
            else:
                vr = requests.get(
                    f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts",
                    params={"maxResults": 1},
                    headers={"Authorization": f"Bearer {access}"},
                    timeout=20,
                )
                if not vr.ok:
                    status = "unhealthy"
                    reason = f"blog_api_http_{vr.status_code}"
                    detail = (vr.text or "")[:240]
        except Exception as e:
            status = "unhealthy"
            reason = "network_error"
            detail = f"{type(e).__name__}: {e}"

    if status == "healthy":
        log("STATUS | healthy | token refresh + blog API check passed")
    else:
        log(f"STATUS | unhealthy | {reason} | {detail}")

    alert_sent = False
    if should_send_alert(state, now, status):
        subject = f"TWTF Blogger Health Alert: {reason}"
        body = (
            f"Blogger health check is unhealthy.\n\n"
            f"Time (UTC): {now.isoformat()}\n"
            f"Reason: {reason}\n"
            f"Detail: {detail}\n\n"
            f"Action: Re-run Blogger OAuth consent and update BLOGGER_REFRESH_TOKEN secret."
        )
        alert_sent = send_alert(subject, body, gmail_address, gmail_app_password)

    next_state = {
        "checked_at": now.isoformat(),
        "status": status,
        "reason": reason,
        "detail": detail,
        "alert_target": ALERT_TO,
        "last_alert_at": now.isoformat() if alert_sent else state.get("last_alert_at", ""),
    }
    save_state(next_state)

    return 0 if status == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
