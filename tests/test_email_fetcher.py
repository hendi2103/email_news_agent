import os
import sys
import json
from email.message import EmailMessage
import pytest

# Ensure src is importable when running tests from repo root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import imaplib
from email_news_agent import email_fetcher, analyze_mail

# Use the user's Ollama model; allow override via environment variable
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def _make_email(subject: str, sender: str, date: str, body: str, html: bool = False) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "recipient@example.com"
    msg["Date"] = date
    if html:
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    return msg.as_bytes()


class MockIMAP:
    def __init__(self, host, port):
        # prepare five mock emails
        self.emails = [
            # 1: simple event announcement (plain text)
            _make_email(
                subject="Community Meetup",
                sender="organizer@example.com",
                date="Mon, 15 Mar 2026 10:00:00 +0100",
                body=(
                    "You're invited to the Community Meetup on 2026-04-01 at 18:00 in Berlin. "
                    "Please register at https://example.com/register"
                ),
                html=False,
            ),
            # 2: formal event announcement (HTML)
            _make_email(
                subject="Event: AI Conference 2026",
                sender="events@conference.org",
                date="Tue, 16 Mar 2026 09:30:00 +0100",
                body=(
                    "<html><body><h1>AI Conference 2026</h1>\n"
                    "<p>Date: April 20, 2026</p>\n"
                    "<p>Location: Convention Center, City</p>\n"
                    "<a href=\"https://conference.example/tickets\">Tickets</a>\n"
                    "</body></html>"
                ),
                html=True,
            ),
            # 3: forwarded event (body contains original From line)
            _make_email(
                subject="Fwd: Workshop Invitation",
                sender="forwarder@example.com",
                date="Wed, 17 Mar 2026 11:00:00 +0100",
                body=(
                    "---------- Forwarded message ----------\n"
                    "From: original_sender@example.com\n"
                    "Subject: Hands-on Workshop\n\n"
                    "Join our hands-on workshop on May 5th at 14:00. Venue: Makerspace. "
                    "Register: https://example.com/workshop"
                ),
                html=False,
            ),
            # 4: general information (newsletter)
            _make_email(
                subject="Weekly Update",
                sender="newsletter@updates.example",
                date="Thu, 18 Mar 2026 08:00:00 +0100",
                body=(
                    "This week's highlights:\n- Feature releases\n- Bug fixes\n"
                    "Read more on our blog: https://blog.example/weekly"
                ),
                html=False,
            ),
            # 5: informal announcement embedded in text
            _make_email(
                subject="Invitation: Casual Drinks",
                sender="social@example.org",
                date="Fri, 19 Mar 2026 19:00:00 +0100",
                body=(
                    "Hey team,\nWe're having casual drinks next Friday (April 2) at 20:00 at The Rooftop Bar. "
                    "No registration required. See you there!"
                ),
                html=False,
            ),
        ]

    def login(self, username, password):
        return "OK", [b"Logged in"]

    def select(self, mailbox):
        return "OK", [b"1"]

    def search(self, charset, criterion):
        # return five message ids (as a single bytes string)
        return "OK", [b"1 2 3 4 5"]

    def fetch(self, msg_id, what):
        # msg_id will be bytes like b"1"
        try:
            idx = int(msg_id.decode() if isinstance(msg_id, bytes) else msg_id)
        except Exception:
            idx = 1
        # IMAP message sequence numbers are 1-based
        if 1 <= idx <= len(self.emails):
            return "OK", [(None, self.emails[idx - 1])]
        return "NO", []

    def logout(self):
        return "BYE", [b"Logged out"]


def test_fetch_and_analyze_5_mock_emails(monkeypatch, capsys):
    # Patch IMAP4_SSL used in email_fetcher
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda host, port: MockIMAP(host, port))

    # Try to contact the real Ollama service once; if it fails, skip the test
    try:
        analyze_mail.ollama.chat(model=MODEL, messages=[{"role": "user", "content": "ping"}])
    except Exception as e:
        pytest.skip(f"Ollama not available or model not loaded: {e}")

    imap_config = {
        "host": "mock.imap.server",
        "username": "user@example.com",
        "password": "password",
        # port and use_ssl default are fine
    }

    emails = email_fetcher.fetch_unseen_emails(imap_config)

    assert len(emails) == 5, "Expected 5 mock emails to be fetched"

    results = []
    for e in emails:
        # pass the body to analyze_relevance (this will call the real ollama.chat)
        res = analyze_mail.analyze_relevance(e["body"], model=MODEL)
        results.append(res)
        print(json.dumps(res, ensure_ascii=False, indent=2))

    # basic sanity checks
    assert all(isinstance(r, dict) for r in results)
    assert any(r["category"] == "event announcement" for r in results), "At least one event announcement expected"


if __name__ == "__main__":
    # Allow running the test file directly for quick manual verification
    test_fetch_and_analyze_5_mock_emails(monkeypatch=__import__("pytest").MonkeyPatch(), capsys=None)
