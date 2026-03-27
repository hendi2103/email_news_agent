"""Newsletter-Generator.

Dieses Modul holt analysierte (aber noch nicht als 'retrieved' markierte)
E-Mail-Datensätze aus der lokalen SQLite-Datenbank, formatiert sie zu einem
einfachen HTML-Newsletter sowie einer Plain-Text-Version (unterteilt in
'Neuigkeiten' und 'Veranstaltungsankündigungen') und versendet den Newsletter
per SMTP.

Öffentliche Funktionen:
- run_newsletter(to_email, smtp_config=None, subject=None) -> bool

Hilfsfunktionen:
- build_newsletter_html(records)
- build_newsletter_text(records)
- send_newsletter(...)
- _is_event_category(category)
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
import html
import textwrap

from email_news_agent import email_storage, email_handler


def _is_event_category(category: Optional[str]) -> bool:
    """Determiniert heuristisch, ob eine Kategorie auf eine Veranstaltung hinweist.

    Args:
        category: Ein optionaler Kategorie-String (kann None sein).

    Returns:
        True, wenn der String Begriffe enthält, die typischerweise auf
        Veranstaltungsankündigungen hindeuten (z. B. 'event', 'veranstaltung').
        Andernfalls False.
    """
    if not category:
        return False
    cat = category.strip().lower()
    return any(k in cat for k in ("event", "veranst", "veranstaltung", "veranstaltungs"))


def build_newsletter_html(records: Iterable[Dict[str, Any]]) -> str:
    """Erzeugt ein einfaches, responsives HTML-Newsletter-Layout.

    Die Einträge werden in zwei Sektionen aufgeteilt: "Neuigkeiten" und
    "Veranstaltungsankündigungen". Erwartete Feldnamen in `records`:
      - subject, sender, date, heading, summary, event_date, event_time,
        event_location, link_to_event, registration_info

    Args:
        records: Iterierbare von Datensätzen (dictionaries), wie von
                 ``email_storage.retrieve()`` zurückgegeben.

    Returns:
        Ein kompletter HTML-String, der als E-Mail-Body verwendet werden kann.
    """
    news: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    for r in records:
        if _is_event_category(r.get("category")):
            events.append(r)
        else:
            news.append(r)

    def render_item(r: Dict[str, Any]) -> str:
        """Rendert einen einzelnen Datensatz als HTML-Fragment.

        Args:
            r: Ein Datensatz mit erwarteten Schlüsseln wie 'heading', 'summary',
               'body', 'sender', 'date', 'event_date', 'event_time',
               'event_location', 'link_to_event', 'registration_info'.

        Returns:
            Ein HTML-String für das Artikel-Fragment.
        """
        heading = html.escape(str(r.get("heading") or r.get("subject") or "(kein Betreff)"))
        # Länge wird extern sichergestellt; hier nur HTML-escaping
        summary = html.escape(str(r.get("summary") or r.get("body") or ""))
        # sender = html.escape(str(r.get("sender") or ""))
        # date = html.escape(str(r.get("date") or ""))

        event_meta_parts: List[str] = []
        if r.get("event_date"):
            event_meta_parts.append(html.escape(str(r.get("event_date"))))
        if r.get("event_time"):
            event_meta_parts.append(html.escape(str(r.get("event_time"))))
        if r.get("event_location"):
            event_meta_parts.append(html.escape(str(r.get("event_location"))))
        meta = " — ".join([p for p in event_meta_parts if p])

        # Unterstützung für mehrere Links, getrennt durch Semikolon
        link_html = ""
        raw_links = r.get("link_to_event")
        if raw_links:
            # Sicherstellen, dass wir einen String haben, dann auf ';' splitten
            links = [s.strip() for s in str(raw_links).split(";") if s.strip()]
            if links:
                list_items = []
                for link in links:
                    esc = html.escape(link)
                    list_items.append(f'<li style="margin-bottom:4px;"><a href="{esc}">{esc}</a></li>')
                link_html = "<p style=\"margin:6px 0 4px 0;\"><strong>Links:</strong></p><ul style=\"margin:0 0 8px 16px;padding:0;\">"
                link_html += "".join(list_items) + "</ul>"

        registration_html = ""
        if r.get("registration_info"):
            registration_html = f'<p><strong>Anmeldung:</strong> {html.escape(str(r.get("registration_info")))}</p>'

        return textwrap.dedent(f"""
            <article style="margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid #eee;">
              <h3 style="margin:0 0 6px 0;font-size:1.05rem;">{heading}</h3>
              <div style="margin-bottom:8px;font-size:0.95rem;line-height:1.4;">{summary}</div>
              {(meta) if meta else ''}
              {link_html}
              {registration_html}
            </article>
        """)

    # Build HTML
    parts: List[str] = [
        '<!doctype html>',
        '<html lang="de">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Newsletter</title>',
        '</head>',
        '<body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;line-height:1.5;padding:18px;">',
        '<header style="margin-bottom:18px;">',
        '<h1 style="margin:0 0 6px 0;">Newsletter</h1>',
        '<p style="color:#666;margin:0 0 0 0;">Eine Zusammenfassung der neuesten Nachrichten und Veranstaltungen.</p>',
        '</header>',
    ]

    if news:
        parts.append('<section>')
        parts.append('<h2 style="font-size:1rem;margin-bottom:6px;">Neuigkeiten</h2>')
        for r in news:
            parts.append(render_item(r))
        parts.append('</section>')

    if events:
        parts.append('<section style="margin-top:18px;">')
        parts.append('<h2 style="font-size:1rem;margin-bottom:6px;">Veranstaltungsankündigungen</h2>')
        for r in events:
            parts.append(render_item(r))
        parts.append('</section>')

    if not news and not events:
        parts.append('<p>Keine neuen Inhalte verfügbar.</p>')

    parts.append('</body></html>')

    return "\n".join(parts)


def build_newsletter_text(records: Iterable[Dict[str, Any]]) -> str:
    """Erzeugt eine Plain-Text-Version des Newsletters.

    Die Einträge werden in zwei Sektionen aufgeteilt: "Neuigkeiten" und
    "Veranstaltungsankündigungen". Erwartete Feldnamen in `records`:
      - subject, sender, date, heading, summary, event_date, event_time,
        event_location, link_to_event, registration_info

    Args:
        records: Iterierbare von Datensätzen (dictionaries), wie von
                 ``email_storage.retrieve()`` zurückgegeben.

    Returns:
        Ein Plain-Text-String, der als alternativer E-Mail-Body verwendet werden kann.
    """
    news: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    for r in records:
        if _is_event_category(r.get("category")):
            events.append(r)
        else:
            news.append(r)

    separator = "-" * 60

    def render_item_text(r: Dict[str, Any]) -> str:
        """Rendert einen einzelnen Datensatz als Plain-Text-Fragment.

        Args:
            r: Ein Datensatz mit erwarteten Schlüsseln wie 'heading', 'summary',
               'body', 'event_date', 'event_time', 'event_location',
               'link_to_event', 'registration_info'.

        Returns:
            Ein Plain-Text-String für den Artikel.
        """
        heading = str(r.get("heading") or r.get("subject") or "(kein Betreff)")
        summary = str(r.get("summary") or r.get("body") or "")

        event_meta_parts: List[str] = []
        if r.get("event_date"):
            event_meta_parts.append(str(r.get("event_date")))
        if r.get("event_time"):
            event_meta_parts.append(str(r.get("event_time")))
        if r.get("event_location"):
            event_meta_parts.append(str(r.get("event_location")))
        meta = " — ".join([p for p in event_meta_parts if p])

        lines = [heading]
        if summary:
            lines.append(summary)
        if meta:
            lines.append(meta)
        if r.get("link_to_event"):
            lines.append(str(r.get("link_to_event")))
        if r.get("registration_info"):
            lines.append(f"Anmeldung: {r.get('registration_info')}")
        lines.append(separator)
        return "\n".join(lines)

    parts: List[str] = [
        "Newsletter",
        "Eine Zusammenfassung der neuesten Nachrichten und Veranstaltungen.",
        separator,
    ]

    if news:
        parts.append("NEUIGKEITEN")
        parts.append(separator)
        for r in news:
            parts.append(render_item_text(r))

    if events:
        parts.append("")
        parts.append("VERANSTALTUNGSANKÜNDIGUNGEN")
        parts.append(separator)
        for r in events:
            parts.append(render_item_text(r))

    if not news and not events:
        parts.append("Keine neuen Inhalte verfügbar.")

    return "\n".join(parts)


def run_newsletter(
    to_email: str,
    smtp_config: Optional[Dict[str, Any]] = None,
    subject: Optional[str] = None,
    filter: Optional[str] = "not retrieved",
) -> bool:
    """Hole alle noch nicht abgerufenen Mails aus der DB, generiere HTML und sende Newsletter.

    Returns True bei erfolgreichem Versand, False wenn keine Mails zu senden waren.
    """
    # retrieve() markiert gefundene Zeilen als retrieved=1
    records = email_storage.retrieve(filter=filter)
    if not records:
        print("Keine ungelesenen Datensätze in der Datenbank.")
        return False

    html_body = build_newsletter_html(records)
    text_body = build_newsletter_text(records)
    if subject is None:
        subject = "Newsletter — Neuigkeiten & Veranstaltungen"

    print(f"Sende Newsletter an {to_email} (Einträge: {len(records)})...")
    # Pass smtp_config through as provided; when None, send_email will load stored config.
    success = email_handler.send_email(
        smtp_config=smtp_config,
        to=to_email,
        subject=subject,
        content=text_body,
        html_content=html_body
    )
    if not success:
        print("Fehler: Newsletter-Versand fehlgeschlagen.")
        return False
    print("Newsletter versendet.")
    return True


if __name__ == "__main__":
    # Beispielaufruf: run_newsletter("
    run_newsletter("hendrik@ger-ev.de", subject='Test-Newsletter', filter="all")