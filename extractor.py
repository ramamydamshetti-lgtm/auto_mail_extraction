"""
Legacy IMAP email fetching (not used by main.py).

Current entry point uses Microsoft Graph (see main.py, outlook_graph.py).
"""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass, field
from email.header import decode_header
from email.message import Message
from typing import Iterator


EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _get_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp.lower():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return str(payload or "")


def extract_addresses_from_text(text: str) -> list[str]:
    """Return unique email addresses found in arbitrary text."""
    seen: set[str] = set()
    out: list[str] = []
    for m in EMAIL_PATTERN.finditer(text or ""):
        addr = m.group(0).lower()
        if addr not in seen:
            seen.add(addr)
            out.append(m.group(0))
    return out


@dataclass
class ExtractedEmail:
    uid: str
    subject: str
    from_addr: str
    to_addrs: str
    date: str
    body: str
    addresses_in_body: list[str] = field(default_factory=list)


def parse_rfc822(raw: bytes, uid: str) -> ExtractedEmail:
    msg = email.message_from_bytes(raw)
    subject = _decode_mime_header(msg.get("Subject"))
    from_addr = _decode_mime_header(msg.get("From"))
    to_addrs = _decode_mime_header(msg.get("To"))
    date = msg.get("Date") or ""
    body = _get_body(msg)
    addrs = extract_addresses_from_text(body)
    return ExtractedEmail(
        uid=uid,
        subject=subject,
        from_addr=from_addr,
        to_addrs=to_addrs,
        date=date,
        body=body,
        addresses_in_body=addrs,
    )


class IMAPExtractor:
    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        port: int = 993,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self._conn: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> IMAPExtractor:
        self._conn = imaplib.IMAP4_SSL(self.host, self.port)
        self._conn.login(self.user, self.password)
        return self

    def __exit__(self, *args: object) -> None:
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def fetch_messages(
        self,
        mailbox: str = "INBOX",
        search_criteria: str = "ALL",
        limit: int | None = None,
    ) -> Iterator[ExtractedEmail]:
        assert self._conn is not None
        self._conn.select(mailbox, readonly=True)
        typ, data = self._conn.search(None, search_criteria)
        if typ != "OK" or not data or not data[0]:
            return
        uids = data[0].split()
        if limit is not None:
            uids = uids[-limit:] if limit > 0 else uids
        for uid in uids:
            uid_s = uid.decode("ascii", errors="replace")
            typ, msg_data = self._conn.fetch(uid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0]
            if not isinstance(raw, tuple) or len(raw) < 2:
                continue
            body_bytes = raw[1]
            if not isinstance(body_bytes, (bytes, bytearray)):
                continue
            yield parse_rfc822(bytes(body_bytes), uid_s)
