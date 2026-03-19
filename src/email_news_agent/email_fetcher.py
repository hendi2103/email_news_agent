import imaplib
import email
import re
from email.header import decode_header


def fetch_unseen_emails(imap_config: dict) -> list[dict]:
    """Fetch unseen emails from an IMAP server.

    Args:
        imap_config: A dictionary with the following keys:
            - host (str): IMAP server hostname.
            - port (int, optional): Server port. Defaults to 993.
            - username (str): Login username / email address.
            - password (str): Login password.
            - use_ssl (bool, optional): Use SSL/TLS connection. Defaults to True.

    Returns:
        A list of dictionaries, one per unseen email, each as returned by
        :func:`parse_email_content`.
    """
    host = imap_config["host"]
    port = imap_config.get("port", 993)
    username = imap_config["username"]
    password = imap_config["password"]
    use_ssl = imap_config.get("use_ssl", True)

    if use_ssl:
        mail = imaplib.IMAP4_SSL(host, port)
    else:
        mail = imaplib.IMAP4(host, port)

    try:
        mail.login(username, password)
        mail.select("INBOX")

        status, message_ids = mail.search(None, "UNSEEN")
        if status != "OK" or not message_ids[0]:
            return []

        emails = []
        for msg_id in message_ids[0].split():
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            parsed = parse_email_content(msg)
            emails.append(parsed)

        return emails
    finally:
        mail.logout()


def _decode_header_value(value: str) -> str:
    """Decode an encoded email header value to a plain string."""
    parts = decode_header(value)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return " ".join(decoded_parts)


def parse_email_content(msg) -> dict:
    """Extract the content, date, sender, of emails.

    Args:
        msg: An :class:`email.message.Message` object to parse.

    Returns:
        A dictionary with the following keys:
            - subject (str): Decoded email subject.
            - sender (str): Decoded sender address (``From`` header).
            - date (str): Raw ``Date`` header value.
            - body (str): Plain-text body (falls back to HTML if no plain part exists).
            - is_forwarded (bool): ``True`` when the email appears to be forwarded.
            - original_sender (str | None): Original sender extracted from the forwarded
              body, or ``None`` when the email is not forwarded or the sender cannot
              be determined.
    """
    subject_raw = msg.get("Subject", "")
    subject = _decode_header_value(subject_raw) if subject_raw else ""

    sender_raw = msg.get("From", "")
    sender = _decode_header_value(sender_raw) if sender_raw else ""

    date = msg.get("Date", "")

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
        if not body:
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/html" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")

    return {
        "subject": subject,
        "sender": sender,
        "date": date,
        "body": body
    }
