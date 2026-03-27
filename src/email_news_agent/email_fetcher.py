import imaplib
import email
from email.header import decode_header
import json
import stat
from pathlib import Path
import getpass
from typing import Any


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
        # Interaktive Abfrage
        print("Keine lokale Mail-Konfiguration gefunden. Bitte IMAP-Einstellungen eingeben.")
        host = input("IMAP Host (z.B. imap.example.com): ").strip()
        username = input("Benutzername / E-Mail: ").strip()
        port_raw = input("Port [993]: ").strip()
        password = getpass.getpass("Passwort (wird nicht angezeigt): ")
        use_ssl_raw = input("Use SSL/TLS? [Y/n]: ").strip()

        if not host or not username or not password:
            raise ValueError("host, username und password sind erforderlich")

        try:
            port = int(port_raw) if port_raw else 993
        except ValueError:
            port = 993

        use_ssl = _to_bool(use_ssl_raw) if use_ssl_raw != "" else True

        data = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "use_ssl": use_ssl,
        }

        # Schreibe Datei (sicherstellen, dass Verzeichnis existiert)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        # Schreibe zuerst und setze dann die Rechte
        with cfg_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        try:
            cfg_path.chmod(0o600)
        except Exception:
            pass

    # Typkonversionen / Validierung
    host = data.get("host")
    username = data.get("username")
    password = data.get("password")
    port_raw = data.get("port", 993)
    use_ssl = _to_bool(data.get("use_ssl", True))

    if not host or not username or not password:
        raise ValueError("IMAP-Konfiguration benötigt 'host', 'username' und 'password'.")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 993

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "use_ssl": use_ssl,
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
