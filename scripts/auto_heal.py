#!/usr/bin/env python3
"""
Self-healer for the TWTF syndication platform.

Reads platform_health.json, diagnoses each failure with Claude, and
applies fixes automatically (Tier 1: known config fixes, Tier 3: Claude-
generated config updates or code patches). Emails a plain-English summary
of what was healed and what (if anything) still needs human attention.
"""
from __future__ import annotations

import base64
import json
import os
import re
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
STATE_FILE = SCRIPTS_DIR / "platform_health.json"
HEAL_LOG_FILE = SCRIPTS_DIR / "heal_log.json"
ALERT_TO = "earthlingoflight@gmail.com"
GH_REPO = os.getenv("GH_REPO", "Lordshrrred/TowWithTheFlow")

# Only these files may be patched automatically
PATCHABLE_FILES = {
    "scripts/check_platform_health.py",
    "scripts/syndicate_post.py",
    "scripts/syndicate_backlog.py",
    "scripts/syndicate_blogger_backlog.py",
    "scripts/syndicate_wordpress_backlog.py",
    "scripts/generate_post.py",
}

CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def env(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if not isinstance(val, str):
        return default
    val = val.strip().lstrip("﻿")
    for q in ('"', "'"):
        if len(val) >= 2 and val[0] == q and val[-1] == q:
            val = val[1:-1].strip().lstrip("﻿")
            break
    m = re.match(rf"^(?:export\s+)?{re.escape(key)}\s*=\s*(.*)$", val)
    if m:
        inner = m.group(1).strip()
        for q in ('"', "'"):
            if len(inner) >= 2 and inner[0] == q and inner[-1] == q:
                inner = inner[1:-1].strip()
        val = inner
    return val


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_health() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_heal_log() -> list:
    try:
        return json.loads(HEAL_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_heal_log(log: list) -> None:
    HEAL_LOG_FILE.write_text(json.dumps(log[-50:], indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Context builders for Claude
# ---------------------------------------------------------------------------

def read_file_head_tail(path: Path, head: int = 100, tail: int = 60) -> str:
    """Read the first `head` + last `tail` lines of a file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    if len(lines) <= head + tail:
        return "\n".join(lines)
    return "\n".join(lines[:head] + ["... (truncated) ..."] + lines[-tail:])


def syndicate_snippet(platform: str) -> str:
    """Extract the main platform function block from syndicate_post.py."""
    path = SCRIPTS_DIR / "syndicate_post.py"
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    # Find the function definition for this platform
    pattern = rf"(^def (?:syndicate_{platform}|get_{platform}_token|resolve_{platform}|check_{platform})[^\n]*\n(?:.*\n){{0,120}})"
    m = re.search(pattern, content, re.MULTILINE)
    return m.group(0)[:4000] if m else ""


def log_tail(lines: int = 50) -> str:
    log_path = SCRIPTS_DIR / "syndication_log.txt"
    try:
        all_lines = log_path.read_text(encoding="utf-8").splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# GitHub secret update (via REST API + PyNaCl)
# ---------------------------------------------------------------------------

def update_secret(name: str, value: str) -> tuple[bool, str]:
    gh_pat = env("GH_PAT")
    if not gh_pat:
        return False, "GH_PAT not configured"
    try:
        from nacl import encoding, public
    except ImportError:
        return False, "PyNaCl not installed (add to pip install step)"

    headers = {
        "Authorization": f"token {gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
        headers=headers, timeout=20,
    )
    if not r.ok:
        return False, f"public-key fetch failed: HTTP {r.status_code}"
    kd = r.json()
    pk = public.PublicKey(kd["key"].encode(), encoding.Base64Encoder())
    encrypted = base64.b64encode(public.SealedBox(pk).encrypt(value.encode())).decode()
    r = requests.put(
        f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{name}",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": kd["key_id"]},
        timeout=20,
    )
    if r.status_code in (201, 204):
        return True, ""
    return False, f"HTTP {r.status_code}: {r.text[:200]}"


# ---------------------------------------------------------------------------
# Code-patch application
# ---------------------------------------------------------------------------

def apply_patch(file_rel: str, old_code: str, new_code: str) -> tuple[bool, str]:
    if file_rel not in PATCHABLE_FILES:
        return False, f"{file_rel} not in allowed patchable files"
    path = ROOT / file_rel
    if not path.exists():
        return False, "file not found"
    content = path.read_text(encoding="utf-8")
    if old_code not in content:
        return False, "old_code not found in file (already patched or wrong excerpt)"
    path.write_text(content.replace(old_code, new_code, 1), encoding="utf-8")
    return True, ""


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git(*args: str) -> tuple[bool, str]:
    result = subprocess.run(["git"] + list(args), cwd=ROOT, capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def commit_and_push(files: list[str], message: str) -> tuple[bool, str]:
    git("config", "user.name", "twtf-auto-healer[bot]")
    git("config", "user.email", "auto-healer@twtf.invalid")
    for f in files:
        git("add", f)
    staged_ok, staged_out = git("diff", "--staged", "--quiet")
    if staged_ok:
        return True, "nothing to commit"
    ok, out = git("commit", "-m", message)
    if not ok:
        return False, f"commit failed: {out}"
    git("pull", "--rebase", "--autostash", "origin", "main")
    ok, out = git("push")
    return ok, out


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

def ask_claude(platform: str, error_detail: str) -> dict | None:
    api_key = env("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    health_check_code = (SCRIPTS_DIR / "check_platform_health.py").read_text(encoding="utf-8")
    syndi_snippet = syndicate_snippet(platform)
    recent_log = log_tail(50)

    prompt = f"""You are the automated self-healing system for "Tow With The Flow", a Denver towing blog with multi-platform syndication (Dev.to, Tumblr, Blogger, WordPress, Feeder).

FAILED PLATFORM: {platform.upper()}
ERROR: {error_detail}

== RECENT SYNDICATION LOG (last 50 lines) ==
{recent_log}

== HEALTH CHECK SCRIPT (check_platform_health.py) ==
{health_check_code}

{f"== SYNDICATION CODE FOR {platform.upper()} =={chr(10)}{syndi_snippet}" if syndi_snippet else ""}

Diagnose the root cause and return ONLY a valid JSON object with this exact structure (no markdown, no extra text):
{{
  "diagnosis": "one or two sentence human-readable root cause explanation",
  "fix_type": "config_update|code_patch|retry|human_required",
  "confidence": "high|medium|low",
  "action": {{}}
}}

The "action" object depends on fix_type:
- config_update: {{"secret_name": "EXACT_SECRET_NAME", "new_value": "value", "reason": "why"}}
- code_patch: {{"file": "scripts/filename.py", "old_code": "exact verbatim string to replace", "new_code": "replacement string", "explanation": "one line"}}
- retry: {{"description": "what should be retried"}}
- human_required: {{"instructions": "numbered steps the human must take"}}

Rules:
1. Use confidence "high" only if you are certain — wrong high-confidence patches will be auto-applied.
2. For code_patch, old_code must be an exact verbatim substring of the file shown above. No paraphrasing.
3. For config_update, only suggest values you can derive from API responses visible in the error or from the code — never invent values.
4. When in doubt, use human_required with detailed instructions.
"""

    max_retries = 3
    r = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=90,
            )
        except Exception as e:
            print(f"[Claude] call failed (attempt {attempt}/{max_retries}): {e}")
            r = None
        else:
            if r.ok:
                break
            if r.status_code == 429 or r.status_code >= 500:
                print(f"[Claude] API error {r.status_code} (attempt {attempt}/{max_retries}): {r.text[:200]}")
            else:
                print(f"[Claude] API error {r.status_code}: {r.text[:200]}")
                return None

        if attempt < max_retries:
            delay = 2 ** attempt
            print(f"[Claude] retrying in {delay}s")
            time.sleep(delay)

    if r is None or not r.ok:
        print(f"[Claude] giving up after {max_retries} attempts")
        return None

    try:
        text = r.json()["content"][0]["text"].strip()
        # Strip markdown fences if present
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
        return json.loads(text)
    except Exception as e:
        print(f"[Claude] response parse failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Tier 1: known deterministic fixes
# ---------------------------------------------------------------------------

def tier1_blogger_wrong_id(error_detail: str) -> dict | None:
    """If Blogger returns 403/404 fetching the blog, auto-discover the correct ID."""
    if "blog fetch HTTP" not in error_detail:
        return None
    cid = env("BLOGGER_CLIENT_ID")
    csec = env("BLOGGER_CLIENT_SECRET")
    rtok = env("BLOGGER_REFRESH_TOKEN")
    if not all([cid, csec, rtok]):
        return None
    try:
        tr = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"client_id": cid, "client_secret": csec, "refresh_token": rtok, "grant_type": "refresh_token"},
            timeout=20,
        )
        access = tr.json().get("access_token", "")
        if not access:
            return None
        r = requests.get(
            "https://www.googleapis.com/blogger/v3/users/self/blogs",
            headers={"Authorization": f"Bearer {access}"},
            timeout=20,
        )
        if not r.ok:
            return None
        items = r.json().get("items", [])
        if len(items) == 1:
            correct_id = str(items[0].get("id", "")).strip()
            if correct_id:
                ok, err = update_secret("BLOGGER_BLOG_ID", correct_id)
                return {
                    "tier": 1, "action": "config_update",
                    "secret": "BLOGGER_BLOG_ID", "value": correct_id,
                    "status": "applied" if ok else f"failed: {err}",
                    "diagnosis": f"Auto-discovered correct Blogger blog ID: {correct_id}",
                }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main heal loop
# ---------------------------------------------------------------------------

def heal_platform(platform: str, error_detail: str) -> dict:
    print(f"\n[HEAL] {platform.upper()} — {error_detail[:120]}")

    # Tier 1 per-platform known fixes
    if platform == "blogger":
        result = tier1_blogger_wrong_id(error_detail)
        if result:
            print(f"[HEAL] Tier 1 fix applied: {result['status']}")
            return result

    # Tier 2/3 — ask Claude
    response = ask_claude(platform, error_detail)
    if not response:
        return {
            "tier": 0, "action": "none", "status": "claude_unavailable",
            "diagnosis": "Claude API unavailable — manual investigation required.",
        }

    diagnosis = response.get("diagnosis", "")
    fix_type = response.get("fix_type", "human_required")
    confidence = response.get("confidence", "low")
    action = response.get("action", {})

    print(f"[HEAL] Claude: fix_type={fix_type} confidence={confidence}")
    print(f"[HEAL] Diagnosis: {diagnosis}")

    if confidence != "high":
        return {
            "tier": 2, "action": fix_type, "confidence": confidence,
            "diagnosis": diagnosis,
            "instructions": action.get("instructions", action.get("description", "")),
            "status": "human_required",
        }

    # === Apply high-confidence fix ===

    if fix_type == "config_update":
        secret_name = action.get("secret_name", "")
        new_value = action.get("new_value", "")
        reason = action.get("reason", "")
        if not secret_name or not new_value:
            return {"tier": 3, "action": fix_type, "status": "invalid_action_fields", "diagnosis": diagnosis}
        ok, err = update_secret(secret_name, new_value)
        return {
            "tier": 3, "action": "config_update",
            "secret": secret_name, "reason": reason,
            "diagnosis": diagnosis,
            "status": "applied" if ok else f"failed: {err}",
        }

    if fix_type == "code_patch":
        file_rel = action.get("file", "")
        old_code = action.get("old_code", "")
        new_code = action.get("new_code", "")
        explanation = action.get("explanation", "")
        if not all([file_rel, old_code, new_code]):
            return {"tier": 3, "action": fix_type, "status": "invalid_patch_fields", "diagnosis": diagnosis}
        ok, err = apply_patch(file_rel, old_code, new_code)
        if not ok:
            return {"tier": 3, "action": "code_patch", "file": file_rel, "status": f"patch_failed: {err}", "diagnosis": diagnosis}
        commit_ok, commit_err = commit_and_push(
            [file_rel],
            f"Auto-heal: {platform} — {explanation[:72]}\n\nDiagnosis: {diagnosis}\n\nCo-Authored-By: Claude Haiku <noreply@anthropic.com>",
        )
        return {
            "tier": 3, "action": "code_patch", "file": file_rel,
            "explanation": explanation, "diagnosis": diagnosis,
            "status": "applied_and_committed" if commit_ok else f"patched_push_failed: {commit_err}",
        }

    # retry or human_required
    return {
        "tier": 2, "action": fix_type, "confidence": confidence,
        "diagnosis": diagnosis,
        "instructions": action.get("instructions", action.get("description", "")),
        "status": "human_required",
    }


# ---------------------------------------------------------------------------
# Email summary
# ---------------------------------------------------------------------------

def send_summary(results: dict[str, dict]) -> None:
    gmail = env("GMAIL_ADDRESS")
    pw = env("GMAIL_APP_PASSWORD")
    if not gmail or not pw:
        print("[HEAL] Email credentials missing, skipping summary email.")
        return

    healed = [p for p, r in results.items() if r.get("status") in ("applied", "applied_and_committed")]
    broken = [p for p, r in results.items() if r.get("status") not in ("applied", "applied_and_committed")]

    if healed and not broken:
        subject = f"TWTF Self-Healed: {', '.join(healed)} fixed automatically"
    elif healed:
        subject = f"TWTF Partial Heal: {len(healed)} fixed, {len(broken)} need attention"
    else:
        subject = f"TWTF Needs Attention: {', '.join(broken)}"

    lines = [
        "Tow With The Flow — Auto-Heal Report",
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    for platform, result in results.items():
        status = result.get("status", "unknown")
        lines.append(f"── {platform.upper()} ──")

        if status in ("applied", "applied_and_committed"):
            lines.append("  SELF-HEALED ✓")
            action = result.get("action", "")
            if action == "config_update":
                lines.append(f"  Updated secret: {result.get('secret')}")
                if result.get("reason"):
                    lines.append(f"  Reason: {result['reason']}")
            elif action == "code_patch":
                lines.append(f"  Code patch applied: {result.get('file')}")
                if result.get("explanation"):
                    lines.append(f"  Change: {result['explanation']}")
            if result.get("diagnosis"):
                lines.append(f"  Root cause: {result['diagnosis']}")
        else:
            lines.append("  NEEDS YOUR ATTENTION")
            if result.get("diagnosis"):
                lines.append(f"  Diagnosis: {result['diagnosis']}")
            instructions = result.get("instructions", "")
            if instructions:
                lines.append(f"  Fix: {instructions}")
            else:
                lines.append(f"  Status: {status}")
        lines.append("")

    lines.append("— TWTF Auto-Healer")
    body = "\n".join(lines)

    msg = MIMEText(body, "plain")
    msg["From"] = gmail
    msg["To"] = ALERT_TO
    msg["Subject"] = subject
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, pw)
            server.sendmail(gmail, ALERT_TO, msg.as_string())
        print(f"[HEAL] Email sent: {subject}")
    except Exception as e:
        print(f"[HEAL] Email failed: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    state = load_health()
    checks = state.get("checks", {})
    unhealthy = {k: v for k, v in checks.items() if v.get("status") == "unhealthy"}

    if not unhealthy:
        print("[HEAL] No unhealthy platforms in state — nothing to do.")
        return 0

    print(f"[HEAL] Unhealthy: {list(unhealthy.keys())}")

    results: dict[str, dict] = {}
    for platform, check in unhealthy.items():
        results[platform] = heal_platform(platform, check.get("detail", "unknown error"))

    # Persist heal log
    log = load_heal_log()
    log.append({"healed_at": datetime.now(timezone.utc).isoformat(), "results": results})
    save_heal_log(log)
    commit_and_push(
        ["scripts/heal_log.json"],
        f"Auto: heal log {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
    )

    send_summary(results)

    print(f"\n[HEAL] Complete:\n{json.dumps(results, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
