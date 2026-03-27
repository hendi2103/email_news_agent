import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from email_news_agent.newsletter_generator import (
    build_newsletter_html,
    build_newsletter_text,
    _is_event_category,
)


# ---------------------------------------------------------------------------
# _is_event_category
# ---------------------------------------------------------------------------

def test_is_event_category_returns_false_for_none():
    assert _is_event_category(None) is False


def test_is_event_category_returns_false_for_news():
    assert _is_event_category("news") is False


def test_is_event_category_returns_true_for_event():
    assert _is_event_category("event") is True


def test_is_event_category_returns_true_for_veranstaltung():
    assert _is_event_category("Veranstaltung") is True


# ---------------------------------------------------------------------------
# build_newsletter_text
# ---------------------------------------------------------------------------

NEWS_RECORD = {
    "subject": "Wichtige Neuigkeit",
    "heading": "Neue Funktion veröffentlicht",
    "summary": "Wir haben eine neue Funktion eingeführt.",
    "category": "news",
}

EVENT_RECORD = {
    "subject": "Konferenz 2026",
    "heading": "Entwicklerkonferenz",
    "summary": "Große Entwicklerkonferenz in Berlin.",
    "category": "event",
    "event_date": "2026-05-15",
    "event_time": "09:00",
    "event_location": "Berlin",
    "link_to_event": "https://example.com/konferenz",
    "registration_info": "Anmeldung unter example.com",
}


def test_build_newsletter_text_empty_records():
    result = build_newsletter_text([])
    assert "Keine neuen Inhalte verfügbar." in result


def test_build_newsletter_text_contains_header():
    result = build_newsletter_text([NEWS_RECORD])
    assert "Newsletter" in result
    assert "Neuigkeiten" in result.upper() or "NEUIGKEITEN" in result


def test_build_newsletter_text_news_section():
    result = build_newsletter_text([NEWS_RECORD])
    assert "Neue Funktion veröffentlicht" in result
    assert "Wir haben eine neue Funktion eingeführt." in result
    # should not contain an events section for a pure news record
    assert "VERANSTALTUNGSANKÜNDIGUNGEN" not in result


def test_build_newsletter_text_events_section():
    result = build_newsletter_text([EVENT_RECORD])
    assert "VERANSTALTUNGSANKÜNDIGUNGEN" in result
    assert "Entwicklerkonferenz" in result
    assert "Berlin" in result
    assert "https://example.com/konferenz" in result
    assert "Anmeldung" in result
    assert "NEUIGKEITEN" not in result


def test_build_newsletter_text_both_sections():
    result = build_newsletter_text([NEWS_RECORD, EVENT_RECORD])
    assert "NEUIGKEITEN" in result
    assert "VERANSTALTUNGSANKÜNDIGUNGEN" in result


def test_build_newsletter_text_event_meta_combined():
    result = build_newsletter_text([EVENT_RECORD])
    # date, time and location should appear joined with em-dash separator
    assert "2026-05-15" in result
    assert "09:00" in result
    assert "Berlin" in result


def test_build_newsletter_text_returns_string():
    result = build_newsletter_text([NEWS_RECORD])
    assert isinstance(result, str)


def test_build_newsletter_text_no_html_tags():
    result = build_newsletter_text([NEWS_RECORD, EVENT_RECORD])
    assert "<" not in result
    assert ">" not in result


def test_build_newsletter_text_fallback_to_subject_when_no_heading():
    record = {"subject": "Nur ein Betreff", "category": "news"}
    result = build_newsletter_text([record])
    assert "Nur ein Betreff" in result


# ---------------------------------------------------------------------------
# build_newsletter_html (smoke test – ensure HTML is not broken by our changes)
# ---------------------------------------------------------------------------

def test_build_newsletter_html_still_works():
    result = build_newsletter_html([NEWS_RECORD, EVENT_RECORD])
    assert "<!doctype html>" in result
    assert "Neue Funktion veröffentlicht" in result
    assert "Entwicklerkonferenz" in result
