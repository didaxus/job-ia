"""Non-interactive device-code login bridge for Codex CLI.

The dashboard enqueues one request in PostgreSQL. Only the worker runs
the official Codex CLI login command and owns CODEX_HOME. PostgreSQL stores
a short-lived user-visible device code, never OAuth access/refresh tokens.
"""
from __future__ import annotations

import re
import subprocess
import threading

from codex_provider import CODEX_BIN, login_status, safe_environment

VERIFY_URL = "https://auth.openai.com/codex/device"
CODES = re.compile(r"^[A-Z0-9]{4,8}(?:-[A-Z0-9]{4,8}){1,3}$")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
MAX_SECONDS = 930
_device_thread: threading.Thread | None = None


def request_login(db_connect):
    """Claim one queued login and expire old (including crashed) sessions."""
    with db_connect() as db:
        db.execute("""
            UPDATE codex_device_logins SET state='expired',
                user_code=NULL,verification_url=NULL,error_code='expired',
                finished_at=now()
            WHERE state IN ('queued','starting','awaiting_user')
              AND expires_at < now()
        """)
        row = db.execute("""
            SELECT id FROM codex_device_logins WHERE state='queued'
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
        """).fetchone()
        if row:
            db.execute("""
                UPDATE codex_device_logins SET state='starting' WHERE id=%s
            """, (row[0],))
        db.commit()
        return row[0] if row else None


def update_request(db_connect, request_id, state, code=None, error_code=None):
    if state not in {"starting", "awaiting_user", "connected", "failed", "expired"}:
        raise ValueError("Invalid device-auth state")
    if state == "awaiting_user" and (not code or not CODES.fullmatch(code)):
        raise ValueError("Invalid device code")
    with db_connect() as db:
        db.execute("""
            UPDATE codex_device_logins SET state=%s,
                user_code=%s,
                verification_url=%s,
                error_code=%s,
                finished_at=CASE WHEN %s IN ('connected','failed','expired')
                                 THEN now() ELSE NULL END
            WHERE id=%s AND state IN ('queued','starting','awaiting_user')
              AND expires_at > now()
        """, (state, code if state == "awaiting_user" else None,
              VERIFY_URL if state == "awaiting_user" else None,
              error_code, state, request_id))
        db.commit()


def parse_device_output(lines):
    """Extract the user code only after the official device-code marker."""
    found_marker = False
    for raw in lines:
        line = ANSI.sub("", raw).strip()
        if "Enter this one-time code" in line:
            found_marker = True
            continue
        if found_marker and CODES.fullmatch(line):
            return line
    return None


def run_device_flow(db_connect, request_id):
    """Run Codex device authorization without blocking the search scheduler."""
    if login_status() == "connected":
        update_request(db_connect, request_id, "connected")
        return
    proc = None
    expiry_timer = None
    code_timer = None
    has_code = threading.Event()
    try:
        proc = subprocess.Popen(
            [CODEX_BIN, "login", "--device-auth"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=safe_environment(),
            text=True,
            bufsize=1,
            stdin=subprocess.DEVNULL,
        )
        expiry_timer = threading.Timer(MAX_SECONDS, proc.kill)
        expiry_timer.daemon = True
        expiry_timer.start()

        def no_code_timeout():
            if not has_code.is_set() and proc.poll() is None:
                proc.kill()

        code_timer = threading.Timer(90, no_code_timeout)
        code_timer.daemon = True
        code_timer.start()

        expecting_code = False
        for raw in proc.stdout:
            line = ANSI.sub("", raw).strip()
            if "Enter this one-time code" in line:
                expecting_code = True
                continue
            if expecting_code and CODES.fullmatch(line):
                has_code.set()
                update_request(db_connect, request_id, "awaiting_user", code=line)
                expecting_code = False
                # Never log device codes, raw CLI output, or credentials.
        result = proc.wait(timeout=5)
        if result == 0 and login_status() == "connected":
            update_request(db_connect, request_id, "connected")
        else:
            error = "device_code_unavailable" if not has_code.is_set() else "authorization_incomplete"
            update_request(db_connect, request_id, "failed", error_code=error)
    except FileNotFoundError:
        update_request(db_connect, request_id, "failed", error_code="cli_unavailable")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        update_request(db_connect, request_id, "failed", error_code="device_auth_failed")
    finally:
        if expiry_timer:
            expiry_timer.cancel()
        if code_timer:
            code_timer.cancel()
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def poll_device_login(db_connect):
    """Called by the worker every 15 s; never starts two device-login jobs."""
    global _device_thread
    if _device_thread and _device_thread.is_alive():
        return False
    request_id = request_login(db_connect)
    if not request_id:
        return False
    _device_thread = threading.Thread(
        target=run_device_flow,
        args=(db_connect, request_id),
        daemon=True,
        name="codex-device-login",
    )
    _device_thread.start()
    return True
