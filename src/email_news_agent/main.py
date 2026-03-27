from __future__ import annotations

import sys
import textwrap
from typing import Any

from email_news_agent import email_fetcher, analyze_mail, email_storage


def _shorten(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def main(model: str = "llama3.2:3b") -> int:
    """Hauptfunktion: lädt IMAP-Config, holt ungelesene E-Mails, analysiert und speichert Ergebnisse.

    Returns:
        Exit code (0 bei Erfolg, >0 bei Fehlern).
    """
    print("Lade IMAP-Konfiguration...")
    try:
        cfg = email_fetcher.load_imap_config()
    except Exception as e:
        print(f"Fehler beim Laden der IMAP-Konfiguration: {e}")
        return 2

    print("Hole ungelesene E-Mails...")
    try:
        mails = email_fetcher.fetch_unseen_emails(cfg)
    except Exception as e:
        print(f"Fehler beim Abrufen von E-Mails: {e}")
        return 3

    if not mails:
        print("Keine ungelesenen E-Mails gefunden.")
        return 0

    print(f"Gefundene E-Mails: {len(mails)}. Starte Analyse...")
    for idx, mail in enumerate(mails, start=1):
        subject = mail.get("subject") or "(kein Betreff)"
        sender = mail.get("sender") or "(unbekannter Absender)"
        date = mail.get("date") or "(kein Datum)"
        body = mail.get("body") or ""

        print(f"\n[{idx}/{len(mails)}] {subject} — {sender} ({date})")

        try:
            analysis = analyze_mail.analyze_mail(body, model=model)
        except Exception as e:
            print(f"Analyse fehlgeschlagen: {e}")
            analysis = {
                "category": "error",
                "original_sender": None,
                "original_sent_date": None,
                "heading": None,
                "summary": None,
                "event_date": None,
                "event_time": None,
                "event_location": None,
                "link_to_event": None,
                "registration_info": None,
            }

        # Merge metadata + analysis for storage
        store_record: dict[str, Any] = {
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": _shorten(body, 2000),
        }
        # normalized keys: analyze_mail returns keys matching MailContent fields
        store_record.update(analysis)

        try:
            email_storage.store(store_record)
            print("Ergebnis gespeichert.")
        except Exception as e:
            print(f"Fehler beim Speichern: {e}")

        # Console summary
        heading = _shorten(analysis.get("heading"), 80)
        summary = _shorten(analysis.get("summary"), 320)
        category = analysis.get("category")
        print(textwrap.dedent(f"""
            Kategorie: {category}
            Überschrift: {heading}
            Zusammenfassung: {summary}
        """))

    print("Fertig.")
    return


if __name__ == "__main__":
    sys.exit(main())
