"""Compatibility shim: previously `email_fetcher` provided IMAP helpers.

Now moved to `email_handler`. This module re-exports the same functions for
backwards compatibility with existing code and tests.
"""
from __future__ import annotations

from email_news_agent.email_handler import (
    load_imap_config,
    fetch_unseen_emails,
    parse_email_content,
)

__all__ = ["load_imap_config", "fetch_unseen_emails", "parse_email_content"]
