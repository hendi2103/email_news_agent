"""Email handler: IMAP fetching and SMTP sending utilities.

Enthält:
- load_imap_config()
- fetch_unseen_emails()
- parse_email_content()
- send_email()  (SMTP, configurable host/port/credentials/STARTTLS)
"""

from __future__ import annotations

import imaplib
import email
from email.header import decode_header
import json
import stat
from pathlib import Path
import getpass
from typing import Any, Dict, Optional

import smtplib
from email.message import EmailMessage


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return False


def _ensure_private_file(path: Path) -> None:
    """
    Setzt Dateirechte auf 0o600, wenn Datei zu offen ist.
    """
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return
    # Wenn Group/Other Rechte gesetzt sind, entferne sie
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        try:
            path.chmod(0o600)
        except Exception:
            # best effort; falls chmod fehlschlägt, ignore
            pass


def load_imap_config(path: str | Path | None = None) -> dict:
    """
    Lädt die IMAP-Konfiguration aus einer JSON-Datei oder fragt den Benutzer interaktiv
    und speichert die Daten dann sicher ab.

    Standard-Pfad: ~/.config/email_news_agent/mail_config.json

    Rückgabe: dict mit keys: host (str), port (int), username (str), password (str), use_ssl (bool)
    """
    default_path = Path.home() / ".config" / "email_news_agent" / "mail_config.json"
    cfg_path = Path(path) if path else default_path

    data: dict[str, Any] = {}
    if cfg_path.exists():
        # Stelle sicher, dass die Datei private Rechte hat
        _ensure_private_file(cfg_path)
        with cfg_path.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                raise ValueError(f"Konfigurationsdatei {cfg_path} enthält kein gültiges JSON")

    else:
        # Interaktive Abfrage für IMAP
        print("Keine lokale Mail-Konfiguration gefunden. Bitte IMAP-Einstellungen eingeben.")
        imap_host = input("IMAP Host (z.B. imap.example.com): ").strip()
        imap_username = input("Benutzername / E-Mail: ").strip()
        imap_port_raw = input("Port [993]: ").strip()
        imap_password = getpass.getpass("Passwort (wird nicht angezeigt): ")
        imap_use_ssl_raw = input("Use SSL/TLS? [Y/n]: ").strip()

        if not imap_host or not imap_username or not imap_password:
            raise ValueError("IMAP: host, username und password sind erforderlich")

        try:
            imap_port = int(imap_port_raw) if imap_port_raw else 993
        except ValueError:
            imap_port = 993

        imap_use_ssl = _to_bool(imap_use_ssl_raw) if imap_use_ssl_raw != "" else True

        # Interaktive Abfrage für SMTP (Voreinstellungen basierend auf IMAP)
        print("Bitte SMTP-Einstellungen eingeben (für das Versenden von Newslettern).")
        smtp_host = input(f"SMTP Host [{imap_host}]: ").strip() or imap_host
        smtp_port_raw = input("SMTP Port [587]: ").strip()
        smtp_username = input(f"SMTP username [{imap_username}]: ").strip() or imap_username
        smtp_password = getpass.getpass("SMTP Passwort (leerlassen, um IMAP-Passwort zu verwenden): ")
        smtp_use_tls_raw = input("Use STARTTLS für SMTP? [Y/n]: ").strip()
        smtp_from = input(f"From-Adresse [{imap_username}]: ").strip() or imap_username

        try:
            smtp_port = int(smtp_port_raw) if smtp_port_raw else 587
        except ValueError:
            smtp_port = 587

        smtp_use_tls = _to_bool(smtp_use_tls_raw) if smtp_use_tls_raw != "" else True

        # wenn kein smtp_password angegeben wurde, nutze das IMAP-passwort als Fallback
        smtp_password_final = smtp_password or imap_password

        data = {
            "imap": {
                "host": imap_host,
                "port": imap_port,
                "username": imap_username,
                "password": imap_password,
                "use_ssl": imap_use_ssl,
            },
            "smtp": {
                "host": smtp_host,
                "port": smtp_port,
                "username": smtp_username,
                "password": smtp_password_final,
                "use_tls": smtp_use_tls,
                "from": smtp_from,
            },
        }

        # Schreibe Datei (sicherstellen, dass Verzeichnis existiert)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with cfg_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        try:
            cfg_path.chmod(0o600)
        except Exception:
            pass

    # normalize when file contains structured data with 'imap' and 'smtp'
    if data.get("imap"):
        imap_data = data.get("imap") or {}
    else:
        # legacy flat format
        imap_data = data

    # Extract imap fields
    host = imap_data.get("host")
    username = imap_data.get("username")
    password = imap_data.get("password")
    port_raw = imap_data.get("port", 993)
    use_ssl = _to_bool(imap_data.get("use_ssl", True))

    if not host or not username or not password:
        raise ValueError("IMAP-Konfiguration benötigt 'host', 'username' und 'password'.")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 993

    # Extract smtp config if present
    smtp_cfg: Dict[str, Any] = {}
    if data.get("smtp"):
        smtp_cfg = data.get("smtp") or {}
    else:
        # try to find smtp keys at top-level or infer from imap
        smtp_cfg = {
            "host": data.get("smtp_host") or imap_data.get("smtp_host") or host,
            "port": int(data.get("smtp_port") or imap_data.get("smtp_port") or 587),
            "username": data.get("smtp_username") or imap_data.get("smtp_username") or username,
            "password": data.get("smtp_password") or imap_data.get("smtp_password") or password,
            "use_tls": _to_bool(data.get("smtp_use_tls") or imap_data.get("smtp_use_tls") or True),
            "from": data.get("smtp_from") or imap_data.get("smtp_from") or username,
        }

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "use_ssl": use_ssl,
        "smtp": smtp_cfg,
    }


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
        if status != "OK" or not message_ids or not message_ids[0]:
            return []

        emails = []
        for msg_id in message_ids[0].split():
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data:
                continue

            # Sicherer Zugriff auf die Rohdaten des E-Mails
            try:
                # msg_data is typically a list/tuple whose first element is a
                # tuple like (b'1 (RFC822 {..})', b'<raw bytes>')
                first = msg_data[0] if isinstance(msg_data, (list, tuple)) and len(msg_data) > 0 else None
                if not isinstance(first, (list, tuple)) or len(first) < 2:
                    continue
                raw_email = first[1]
            except Exception:
                continue

            msg = email.message_from_bytes(raw_email)
            parsed = parse_email_content(msg)
            emails.append(parsed)

        return emails
    finally:
        try:
            mail.logout()
        except Exception:
            pass


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
            - subject (str): The subject of the email.
            - from (str): The sender's email address.
            - to (str): The recipient's email address.
            - date (str): The date the email was sent.
            - content (str): The plain text content of the email.
            - html_content (str, optional): The HTML content of the email, if available.
    """
    subject = _decode_header_value(msg.get("Subject", ""))
    from_ = _decode_header_value(msg.get("From", ""))
    to = _decode_header_value(msg.get("To", ""))
    date = _decode_header_value(msg.get("Date", ""))
    content = ""
    html_content = ""

    # Versuche, den Inhalt aus dem Payload zu extrahieren
    try:
        if msg.is_multipart():
            # Bei multipart Nachrichten den Text-Teil finden
            for part in msg.walk():
                # Ignoriere Attachments und andere nicht-Text Teile
                if part.get_content_maintype() == "text" and part.get("Content-Disposition") is None:
                    content_type = part.get_content_type()
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)  # type: ignore
                    if payload is not None:
                        if content_type == "text/plain":
                            content = payload.decode(charset, errors="replace")
                        elif content_type == "text/html":
                            html_content = payload.decode(charset, errors="replace")
        else:
            # Bei einfachen Nachrichten (nicht-multipart) direkt den Payload verwenden
            payload = msg.get_payload(decode=True)  # type: ignore
            charset = msg.get_content_charset() or "utf-8"
            if payload is not None:
                content = payload.decode(charset, errors="replace")
    except Exception:
        pass  # Bei Fehlern beim Dekodieren einfach weitermachen

    return {
        "subject": subject,
        "from": from_,
        "to": to,
        "date": date,
        "content": content,
        "html_content": html_content,
    }


def send_email(
    smtp_config: Optional[dict],
    to: str,
    subject: str,
    content: str,
    html_content: str = "",
) -> bool:
    """Send an email using SMTP.

    If ``smtp_config`` is None, the function will load the local configuration
    file via :func:`load_imap_config()` and use the contained ``smtp`` section.

    Args:
        smtp_config: Optional SMTP configuration dict. When omitted the local
                     config file is used.
        to: The recipient's email address.
        subject: The subject of the email.
        content: The plain text content of the email.
        html_content: The HTML content of the email, if available.

    Returns:
        True on success. Raises smtplib.SMTPException on failure.
    """
    if not smtp_config:
        cfg_all = load_imap_config()
        smtp_cfg = cfg_all.get("smtp") or {}
    else:
        smtp_cfg = smtp_config

    host = smtp_cfg.get("host", "localhost")
    port = int(smtp_cfg.get("port", 587))
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")
    use_tls = bool(smtp_cfg.get("use_tls", True))
    from_addr = smtp_cfg.get("from") or username or f"noreply@{host}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(content or "")
    if html_content:
        msg.add_alternative(html_content, subtype="html")

    # Verbindung und (optionale) Authentifizierung
    if use_tls:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)

    return True
