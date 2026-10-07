"""
Microsoft Graph: read mailbox messages with OAuth2 (client credentials).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.parse import quote

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"


def _encode_user(mailbox: str) -> str:
    return quote(mailbox, safe="")


@dataclass
class AttachmentInfo:
    name: str
    content_type: str
    size: int
    id: str


@dataclass
class OutlookMessage:
    graph_id: str
    internet_message_id: str
    subject: str
    from_email: str
    from_name: str
    to_recipients: list[str]
    cc_recipients: list[str]
    received_date_time: str
    body_plain: str
    body_html: str
    body_normalized: str
    has_attachments: bool
    conversation_id: str = ""
    attachments: list[AttachmentInfo] = field(default_factory=list)
    is_read: bool = False
    raw_body_content_type: str = ""

def _token_client_credentials(
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"],
    )
    if not result or "access_token" not in result:
        err = (result or {}).get("error_description") or (result or {}).get("error")
        raise RuntimeError(f"Token acquisition failed: {err}")
    return result["access_token"]


def _addr_from_from_field(from_obj: dict[str, Any] | None) -> tuple[str, str]:
    if not from_obj or "emailAddress" not in from_obj:
        return "", ""
    em = from_obj["emailAddress"]
    return (em.get("address") or "").strip(), (em.get("name") or "").strip()


def _to_list(to_recipients: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for r in to_recipients or []:
        em = r.get("emailAddress") or {}
        a = (em.get("address") or "").strip()
        if a:
            out.append(a)
    return out


def fetch_attachments(
    token: str,
    mailbox: str,
    message_id: str,
) -> list[AttachmentInfo]:
    mid = quote(message_id, safe="")
    url = f"{GRAPH}/users/{_encode_user(mailbox)}/messages/{mid}/attachments"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    data = r.json()
    items: list[AttachmentInfo] = []
    for a in data.get("value", []):
        if a.get("@odata.type") == "#microsoft.graph.fileAttachment":
            items.append(
                AttachmentInfo(
                    id=a.get("id") or "",
                    name=a.get("name") or "",
                    content_type=a.get("contentType") or "",
                    size=int(a.get("size") or 0),
                )
            )
    return items


def fetch_attachment_detail(
    token: str,
    mailbox: str,
    message_id: str,
    attachment_id: str,
) -> dict[str, Any]:
    """Return full Graph attachment object (may include contentBytes for fileAttachment)."""
    mid = quote(message_id, safe="")
    aid = quote(attachment_id, safe="")
    url = f"{GRAPH}/users/{_encode_user(mailbox)}/messages/{mid}/attachments/{aid}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


import time

def _get_with_retry(url: str, headers: dict[str, str], timeout: int = 120, max_retries: int = 5) -> requests.Response:
    """Execute GET request with exponential backoff and Retry-After honouring for 429/5xx (S6)."""
    last_r: requests.Response | None = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            last_r = r
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 5))
                time.sleep(max(1, retry_after))
                continue
            if r.status_code >= 500:
                time.sleep(min(2 ** attempt, 30))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == max_retries:
                raise
            time.sleep(min(2 ** attempt, 30))
    if last_r is not None:
        last_r.raise_for_status()
        return last_r
    raise RuntimeError("Failed after max retries")


def iter_inbox_messages(
    token: str,
    mailbox: str,
    *,
    limit: int | None = None,
    top_per_page: int = 50,
    min_received_time: str | None = None,
    orderby: str = "receivedDateTime asc",
) -> Iterator[dict[str, Any]]:
    """Yield raw Graph message objects from Inbox in ascending order (S3)."""
    select = (
        "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,"
        "isRead,internetMessageId,conversationId"
    )
    query_parts = [
        f"$orderby={orderby}",
        f"$select={select}",
        f"$top={top_per_page}",
    ]
    if min_received_time:
        clean_iso = min_received_time.strip().replace("+00:00", "Z")
        query_parts.append(f"$filter=receivedDateTime ge {clean_iso}")

    query_str = "&".join(query_parts)
    url = f"{GRAPH}/users/{_encode_user(mailbox)}/mailFolders/inbox/messages?{query_str}"
    headers = {"Authorization": f"Bearer {token}"}
    count = 0
    while url:
        r = _get_with_retry(url, headers=headers, timeout=120)
        payload = r.json()
        items = payload.get("value", [])
        if not items:
            break
        all_older = True
        for m in items:
            rec = m.get("receivedDateTime") or ""
            if min_received_time and rec and rec < min_received_time:
                continue
            all_older = False
            yield m
            count += 1
            if limit is not None and count >= limit:
                return
        if min_received_time and all_older:
            break
        url = payload.get("@odata.nextLink")


def fetch_message_by_id(
    token: str,
    mailbox: str,
    message_id: str,
) -> dict[str, Any]:
    """Fetch one raw Graph message by its id."""
    mid = quote(message_id, safe="")
    select = (
        "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,"
        "isRead,internetMessageId,conversationId"
    )
    url = f"{GRAPH}/users/{_encode_user(mailbox)}/messages/{mid}?$select={select}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


def message_to_outlook(
    raw: dict[str, Any],
    *,
    body_plain: str,
    body_html: str,
    body_normalized: str,
    attachments: list[AttachmentInfo],
) -> OutlookMessage:
    fe, fn = _addr_from_from_field(raw.get("from"))
    body_obj = raw.get("body") or {}
    return OutlookMessage(
        graph_id=raw.get("id") or "",
        internet_message_id=raw.get("internetMessageId") or "",
        subject=raw.get("subject") or "",
        from_email=fe,
        from_name=fn,
        to_recipients=_to_list(raw.get("toRecipients")),
        cc_recipients=_to_list(raw.get("ccRecipients")),
        received_date_time=raw.get("receivedDateTime") or "",
        body_plain=body_plain,
        body_html=body_html,
        body_normalized=body_normalized,
        has_attachments=bool(raw.get("hasAttachments")),
        conversation_id=raw.get("conversationId") or "",
        attachments=attachments,
        is_read=bool(raw.get("isRead")),
        raw_body_content_type=(body_obj.get("contentType") or "").lower(),
    )


def acquire_token_from_env() -> str:
    tenant = os.environ.get("AZURE_TENANT_ID", "").strip()
    cid = os.environ.get("AZURE_CLIENT_ID", "").strip()
    secret = os.environ.get("AZURE_CLIENT_SECRET", "").strip()
    if not tenant or not cid or not secret:
        raise RuntimeError(
            "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET in .env"
        )
    return _token_client_credentials(tenant, cid, secret)
