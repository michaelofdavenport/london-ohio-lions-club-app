# app/email_templates.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmailParts:
    subject: str
    body: str


def _clean(s: Optional[str]) -> str:
    return (s or "").strip()


def _line(label: str, value: Optional[str]) -> str:
    v = _clean(value) or "—"
    return f"{label}: {v}"


def _footer(org_name: str) -> str:
    return (
        "\n\n"
        "Regards,\n"
        f"{org_name}\n"
    )


def _links_block(base_url: str) -> str:
    base = _clean(base_url).rstrip("/")
    if not base:
        return ""
    return (
        "\n\n"
        "Links:\n"
        f"- Member Login: {base}/static/index.html\n"
        f"- Admin Tools:  {base}/admin/tools\n"
    )


def request_received(
    org_name: str,
    request_id: int,
    category: str,
    status: str,
    requester_name: str,
    base_url: str = "",
) -> EmailParts:
    subject = f"{org_name} — Request Received (#{request_id})"
    body = (
        f"Hello {_clean(requester_name) or 'there'},\n\n"
        "This message confirms we received your request. Our team will review it as soon as possible.\n\n"
        f"{_line('Request ID', str(request_id))}\n"
        f"{_line('Category', category)}\n"
        f"{_line('Current Status', status)}"
        f"{_links_block(base_url)}"
        f"{_footer(org_name)}"
    )
    return EmailParts(subject=subject, body=body)


def admin_new_request(
    org_name: str,
    club_slug: str,
    request_id: int,
    category: str,
    requester_name: str,
    requester_email: Optional[str],
    requester_phone: Optional[str],
    requester_address: Optional[str],
    description: str,
    base_url: str = "",
) -> EmailParts:
    subject = f"{org_name} — New Request #{request_id} ({_clean(category) or 'Uncategorized'})"
    body = (
        "A new request was submitted.\n\n"
        f"{_line('Organization', org_name)}\n"
        f"{_line('Club Slug', club_slug)}\n"
        f"{_line('Request ID', str(request_id))}\n"
        f"{_line('Category', category)}\n\n"
        f"{_line('Requester Name', requester_name)}\n"
        f"{_line('Requester Email', requester_email)}\n"
        f"{_line('Requester Phone', requester_phone)}\n"
        f"{_line('Requester Address', requester_address)}\n\n"
        "Description:\n"
        f"{_clean(description) or '—'}"
        f"{_links_block(base_url)}"
        f"{_footer(org_name)}"
    )
    return EmailParts(subject=subject, body=body)


def assignment_notice(
    org_name: str,
    request_id: int,
    category: str,
    status: str,
    created_at_str: str,
    requester_name: str,
    requester_email: Optional[str],
    requester_phone: Optional[str],
    requester_address: Optional[str],
    description: str,
    notes_block: str,
    assigned_by: str = "Admin",
    base_url: str = "",
) -> EmailParts:
    subject = f"{org_name} — Assignment: Request #{request_id} ({_clean(category) or 'Uncategorized'})"
    body = (
        "You have been assigned a request.\n\n"
        f"{_line('Request ID', str(request_id))}\n"
        f"{_line('Category', category)}\n"
        f"{_line('Status', status)}\n"
        f"{_line('Submitted (UTC)', created_at_str)}\n"
        f"{_line('Assigned By', assigned_by)}\n\n"
        f"{_line('Requester Name', requester_name)}\n"
        f"{_line('Requester Email', requester_email)}\n"
        f"{_line('Requester Phone', requester_phone)}\n"
        f"{_line('Requester Address', requester_address)}\n\n"
        "Description:\n"
        f"{_clean(description) or '—'}\n\n"
        "Notes (latest first):\n"
        f"{_clean(notes_block) or '— (no notes yet)'}"
        f"{_links_block(base_url)}"
        f"{_footer(org_name)}"
    )
    return EmailParts(subject=subject, body=body)


def requester_decision(
    org_name: str,
    request_id: int,
    category: str,
    decision: str,
    requester_name: str,
    decision_note: Optional[str] = None,
    base_url: str = "",
) -> EmailParts:
    subject = f"{org_name} — Update on Request #{request_id}: {decision}"
    note = _clean(decision_note)
    body = (
        f"Hello {_clean(requester_name) or 'there'},\n\n"
        "This is an update regarding your request.\n\n"
        f"{_line('Request ID', str(request_id))}\n"
        f"{_line('Category', category)}\n"
        f"{_line('Decision', decision)}\n\n"
        + (f"Decision Note:\n{note}\n" if note else "Decision Note:\n—\n")
        + f"{_links_block(base_url)}"
        + f"{_footer(org_name)}"
    )
    return EmailParts(subject=subject, body=body)
