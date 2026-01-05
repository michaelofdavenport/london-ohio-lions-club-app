# app/emailer.py

import os
import smtplib
import socket
from email.message import EmailMessage


def send_email_if_configured(to_email: str, subject: str, body: str) -> bool:
    """
    Sends email only if SMTP is configured.
    NEVER raises. Returns True if attempted+sent, False if skipped/failed.
    """
    enabled = (os.getenv("EMAIL_ENABLED", "false") or "false").strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return False

    host = (os.getenv("SMTP_HOST") or "").strip()
    port_str = (os.getenv("SMTP_PORT") or "587").strip()
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    from_name = (os.getenv("SMTP_FROM_NAME") or "London Lions").strip()
    from_email = (os.getenv("SMTP_FROM_EMAIL") or username).strip()

    # If not configured, skip quietly
    if not host or not username or not password or not from_email:
        print("EMAIL SKIPPED: Missing SMTP_* env vars (host/username/password/from).")
        return False

    try:
        port = int(port_str)
    except Exception:
        port = 587

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg.set_content(body)

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(username, password)
            server.send_message(msg)

        print(f"EMAIL SENT to {to_email}")
        return True

    except socket.gaierror as e:
        print(f"EMAIL FAILED: DNS/host lookup failed for SMTP_HOST='{host}'. Error: {e}")
        return False
    except Exception as e:
        print(f"EMAIL FAILED: {e}")
        return False
