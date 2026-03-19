import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import pytest

from src.email_news_agent.email_fetcher import fetch_unseen_emails, parse_email_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_simple_message(
    subject="Test Subject",
    sender="sender@example.com",
    date="Mon, 01 Jan 2024 10:00:00 +0000",
    body="Hello World",
    content_type="plain",
) -> email.message.Message:
    msg = MIMEText(body, content_type)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = date
    return msg


def _build_multipart_message(
    subject="Multipart Subject",
    sender="sender@example.com",
    date="Mon, 01 Jan 2024 10:00:00 +0000",
    plain_body="Plain text",
    html_body="<p>HTML text</p>",
) -> email.message.Message:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = date
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


# ---------------------------------------------------------------------------
# parse_email_content tests
# ---------------------------------------------------------------------------

class TestParseEmailContent:
    def test_basic_fields_are_extracted(self):
        msg = _build_simple_message(
            subject="Hello",
            sender="alice@example.com",
            date="Mon, 01 Jan 2024 10:00:00 +0000",
            body="Test body",
        )
        result = parse_email_content(msg)

        assert result["subject"] == "Hello"
        assert result["sender"] == "alice@example.com"
        assert result["date"] == "Mon, 01 Jan 2024 10:00:00 +0000"
        assert "Test body" in result["body"]

    def test_not_forwarded_by_default(self):
        msg = _build_simple_message(subject="Regular email")
        result = parse_email_content(msg)

        assert result["is_forwarded"] is False
        assert result["original_sender"] is None

    def test_detects_fwd_prefix(self):
        msg = _build_simple_message(subject="Fwd: Some news")
        result = parse_email_content(msg)

        assert result["is_forwarded"] is True

    def test_detects_fw_prefix(self):
        msg = _build_simple_message(subject="FW: Some news")
        result = parse_email_content(msg)

        assert result["is_forwarded"] is True

    def test_extracts_original_sender_from_forwarded_body(self):
        body = (
            "-------- Forwarded Message --------\n"
            "From: original@example.com\n"
            "Subject: Original\n\n"
            "Original body text."
        )
        msg = _build_simple_message(subject="Fwd: Check this", body=body)
        result = parse_email_content(msg)

        assert result["is_forwarded"] is True
        assert result["original_sender"] is not None
        assert "original@example.com" in result["original_sender"]

    def test_multipart_prefers_plain_text(self):
        msg = _build_multipart_message(plain_body="Plain content", html_body="<p>HTML</p>")
        result = parse_email_content(msg)

        assert "Plain content" in result["body"]
        assert "<p>" not in result["body"]

    def test_multipart_falls_back_to_html(self):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "HTML only"
        msg["From"] = "sender@example.com"
        msg["Date"] = "Mon, 01 Jan 2024 10:00:00 +0000"
        msg.attach(MIMEText("<p>HTML only body</p>", "html"))

        result = parse_email_content(msg)
        assert "<p>HTML only body</p>" in result["body"]

    def test_missing_headers_return_empty_strings(self):
        msg = email.message.Message()
        msg.set_payload("body text")
        result = parse_email_content(msg)

        assert result["subject"] == ""
        assert result["sender"] == ""
        assert result["date"] == ""


# ---------------------------------------------------------------------------
# fetch_unseen_emails tests
# ---------------------------------------------------------------------------

class TestFetchUnseenEmails:
    def _make_imap_config(self):
        return {
            "host": "imap.example.com",
            "port": 993,
            "username": "user@example.com",
            "password": "secret",
        }

    def _mock_imap(self, message_ids=b"1 2", messages=None):
        """Return a mock IMAP4_SSL instance."""
        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [b"Logged in"])
        mock_mail.select.return_value = ("OK", [b"2"])
        mock_mail.search.return_value = ("OK", [message_ids])

        if messages is None:
            msg = _build_simple_message()
            raw = msg.as_bytes()
            messages = {b"1": raw, b"2": raw}

        def fetch_side_effect(msg_id, fmt):
            raw = messages.get(msg_id, b"")
            return ("OK", [(None, raw)])

        mock_mail.fetch.side_effect = fetch_side_effect
        return mock_mail

    @patch("email_fetcher.imaplib.IMAP4_SSL")
    def test_returns_list_of_dicts(self, mock_imap_cls):
        msg = _build_simple_message(subject="News", sender="news@example.com")
        raw = msg.as_bytes()
        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [b"OK"])
        mock_mail.select.return_value = ("OK", [b"1"])
        mock_mail.search.return_value = ("OK", [b"1"])
        mock_mail.fetch.return_value = ("OK", [(None, raw)])
        mock_imap_cls.return_value = mock_mail

        result = fetch_unseen_emails(self._make_imap_config())

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["subject"] == "News"
        assert result[0]["sender"] == "news@example.com"

    @patch("email_fetcher.imaplib.IMAP4_SSL")
    def test_returns_empty_list_when_no_unseen(self, mock_imap_cls):
        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [b"OK"])
        mock_mail.select.return_value = ("OK", [b"0"])
        mock_mail.search.return_value = ("OK", [b""])
        mock_imap_cls.return_value = mock_mail

        result = fetch_unseen_emails(self._make_imap_config())

        assert result == []

    @patch("email_fetcher.imaplib.IMAP4")
    def test_uses_plain_imap_when_ssl_disabled(self, mock_imap_cls):
        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [b"OK"])
        mock_mail.select.return_value = ("OK", [b"0"])
        mock_mail.search.return_value = ("OK", [b""])
        mock_imap_cls.return_value = mock_mail

        config = self._make_imap_config()
        config["use_ssl"] = False
        fetch_unseen_emails(config)

        mock_imap_cls.assert_called_once()

    @patch("email_fetcher.imaplib.IMAP4_SSL")
    def test_logout_called_even_on_exception(self, mock_imap_cls):
        mock_mail = MagicMock()
        mock_mail.login.return_value = ("OK", [b"OK"])
        mock_mail.select.side_effect = Exception("select failed")
        mock_imap_cls.return_value = mock_mail

        with pytest.raises(Exception, match="select failed"):
            fetch_unseen_emails(self._make_imap_config())

        mock_mail.logout.assert_called_once()
