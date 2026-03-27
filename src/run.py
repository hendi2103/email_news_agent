"""Runner: start the package main() from the src folder.

Usage from project root:
  python src/run.py

This keeps the package layout intact (package lives in src/email_news_agent) and
lets python find the package because the script is executed from the `src` dir.
"""

from __future__ import annotations

from email_news_agent.main import main


if __name__ == "__main__":
    raise SystemExit(main())
