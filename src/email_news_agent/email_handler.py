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
import re
import html as _html_module

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


def _html_to_text(html_text: str) -> str:
    """Rudimentäre HTML->Text Konvertierung: Scripts/Styles entfernen, Tags löschen, Entities entescapen."""
    if not html_text:
        return ""
    # remove scripts/styles
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    # strip tags
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    # unescape HTML entities and collapse whitespace
    text = _html_module.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_email_content(msg) -> dict:
    """Robuste Extraktion von E-Mail-Feldern.

    Liefert ein Dictionary mit Schlüsseln, die im Rest der App erwartet werden:
      - subject (str)
      - sender (str)
      - date (str)
      - body (str): bevorzugt text/plain, ansonsten aus HTML konvertiert
      - html_body (str): originaler HTML-Teil falls vorhanden

    Der Parser überspringt Attachments, decodeiert Charset-sicher und versucht
    best-effort, lesbaren Text zurückzugeben.
    """
    subject = _decode_header_value(msg.get("Subject", ""))
    sender = _decode_header_value(msg.get("From", ""))
    date = _decode_header_value(msg.get("Date", ""))

    body = ""
    html_body = ""

    try:
        is_multipart = getattr(msg, "is_multipart", lambda: False)()
        if is_multipart:
            # Sammle bevorzugt text/plain und text/html
            for part in msg.walk():
                try:
                    cdisp = part.get_content_disposition()
                except Exception:
                    cdisp = part.get("Content-Disposition")
                if cdisp == "attachment":
                    continue

                ctype = part.get_content_type()
                try:
                    payload = part.get_payload(decode=True)
                except Exception:
                    try:
                        payload = part.get_payload()
                    except Exception:
                        payload = None

                if payload is None:
                    continue

                charset = part.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace") if isinstance(payload, (bytes, bytearray)) else str(payload)
                except Exception:
                    text = str(payload)

                if ctype == "text/plain" and not body:
                    body = text
                elif ctype == "text/html" and not html_body:
                    html_body = text

            # fallback: wenn kein text/plain, dann html->text
            if not body and html_body:
                body = _html_to_text(html_body)
        else:
            # non-multipart: direkt payload
            try:
                payload = msg.get_payload(decode=True)
            except Exception:
                try:
                    payload = msg.get_payload()
                except Exception:
                    payload = None

            if payload is not None:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    body = payload.decode(charset, errors="replace") if isinstance(payload, (bytes, bytearray)) else str(payload)
                except Exception:
                    body = str(payload)

            # If content type is html, convert
            if msg.get_content_type() == "text/html" and body:
                html_body = body
                body = _html_to_text(html_body)
    except Exception:
        # Best-effort fallback: versuche raw payload
        try:
            raw = msg.get_payload(decode=True)
            if isinstance(raw, (bytes, bytearray)):
                body = raw.decode("utf-8", errors="replace")
            else:
                body = str(raw)
        except Exception:
            body = ""

    return {
        "subject": subject,
        "sender": sender,
        "date": date,
        "body": body or "",
        "html_body": html_body or "",
    }


def send_email(
    smtp_config: Optional[dict],
    to: str,
    subject: str,
    content: str,
    html_content: str = "",
    timeout: float = 10.0,
) -> bool:
    """Send an email using SMTP with a connection timeout and robust error handling.

    If ``smtp_config`` is None or an empty dict, the function will load the local
    configuration file via :func:`load_imap_config()` and use the contained ``smtp`` section.

    Args:
        smtp_config: Optional SMTP configuration dict. When omitted the local
                     config file is used.
        to: The recipient's email address.
        subject: The subject of the email.
        content: The plain text content of the email.
        html_content: The HTML content of the email, if available.
        timeout: Socket timeout in seconds for the SMTP connection.

    Returns:
        True on success, False on failure (no blocking/hangs).
    """
    import socket

    # treat empty dict as missing config (so we load saved config)
    if smtp_config is None or (isinstance(smtp_config, dict) and len(smtp_config) == 0):
        cfg_all = load_imap_config()
        smtp_cfg = cfg_all.get("smtp") or {}
    else:
        smtp_cfg = smtp_config

    host = smtp_cfg.get("host", "localhost")
    port = int(smtp_cfg.get("port", 587))
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")
    use_tls = bool(smtp_cfg.get("use_tls", True))
    use_ssl = bool(smtp_cfg.get("use_ssl", False)) or (port == 465)
    from_addr = smtp_cfg.get("from") or username or f"noreply@{host}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(content or "")
    if html_content:
        msg.add_alternative(html_content, subtype="html")

    server = None
    try:
        # Choose SSL or plain connection with optional STARTTLS.
        if use_ssl:
            server = smtplib.SMTP_SSL(host=host, port=port, timeout=timeout)
            server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        else:
            server = smtplib.SMTP(host=host, port=port, timeout=timeout)
            server.ehlo()
            if use_tls:
                # STARTTLS may fail quickly if server doesn't support it, but we set a timeout.
                try:
                    server.starttls()
                    server.ehlo()
                except (smtplib.SMTPException, OSError) as e:
                    # If STARTTLS fails, proceed depending on whether credentials are provided.
                    # Log and continue to attempt login/send over plain (some servers allow it on submit ports).
                    pass
            if username and password:
                try:
                    server.login(username, password)
                except smtplib.SMTPException:
                    # authentication failed; raise or return False
                    return False
            server.send_message(msg)
    except (smtplib.SMTPException, socket.timeout, ConnectionRefusedError, OSError) as e:
        # Do not hang — report failure
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass

    return True
