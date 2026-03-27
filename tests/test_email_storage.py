import os
import sys
import sqlite3
from datetime import date, datetime

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC_DIR = os.path.join(ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import email_news_agent.email_storage as email_storage


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect the database directory to a temporary folder for every test."""
    monkeypatch.setattr(email_storage, '_DB_DIR', str(tmp_path))
    yield tmp_path


# ---------------------------------------------------------------------------
# store()
# ---------------------------------------------------------------------------

def test_store_creates_database_and_table():
    db_path = email_storage._db_path()
    assert not os.path.exists(db_path)

    email_storage.store({'subject': 'Hello', 'sender': 'a@b.com'})

    assert os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mails'")
    assert cursor.fetchone() is not None
    conn.close()


def test_store_inserts_record_with_timestamp_and_retrieved_false():
    email_storage.store({'subject': 'Test', 'body': 'Hello world'})

    conn = sqlite3.connect(email_storage._db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM mails').fetchone()
    conn.close()

    assert row['subject'] == 'Test'
    assert row['body'] == 'Hello world'
    assert row['retrieved'] == 0
    # timestamp should be a parseable ISO datetime
    datetime.fromisoformat(row['timestamp'])


def test_store_adds_missing_columns_to_existing_table():
    email_storage.store({'subject': 'First'})
    email_storage.store({'subject': 'Second', 'extra_field': 'new'})

    conn = sqlite3.connect(email_storage._db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT * FROM mails ORDER BY id').fetchall()
    conn.close()

    assert len(rows) == 2
    # Both rows should have the extra_field column; first row value is NULL
    assert rows[0]['extra_field'] is None
    assert rows[1]['extra_field'] == 'new'


def test_store_multiple_records():
    for i in range(3):
        email_storage.store({'index': i, 'subject': f'Mail {i}'})

    conn = sqlite3.connect(email_storage._db_path())
    count = conn.execute('SELECT COUNT(*) FROM mails').fetchone()[0]
    conn.close()
    assert count == 3


# ---------------------------------------------------------------------------
# retrieve()
# ---------------------------------------------------------------------------

def test_retrieve_returns_empty_list_when_no_db():
    result = email_storage.retrieve()
    assert result == []


def test_retrieve_unretrieved_records_when_no_dates():
    email_storage.store({'subject': 'A'})
    email_storage.store({'subject': 'B'})

    records = email_storage.retrieve()

    assert len(records) == 2
    assert {r['subject'] for r in records} == {'A', 'B'}


def test_retrieve_sets_retrieved_flag_to_true():
    email_storage.store({'subject': 'A'})

    email_storage.retrieve()

    conn = sqlite3.connect(email_storage._db_path())
    row = conn.execute('SELECT retrieved FROM mails').fetchone()
    conn.close()
    assert row[0] == 1


def test_retrieve_no_dates_skips_already_retrieved():
    email_storage.store({'subject': 'A'})
    email_storage.retrieve()          # marks as retrieved

    second = email_storage.retrieve()  # should return nothing new

    assert second == []


class _ControlledDatetime(datetime):
    """Subclass of datetime whose ``now()`` returns a configurable value.

    Assign the desired return value to the ``_ts`` class attribute before
    calling :func:`email_storage.store`.
    """
    _ts: datetime = datetime(2026, 1, 1)

    @classmethod
    def now(cls, tz=None):
        return cls._ts


@pytest.fixture()
def fake_datetime(monkeypatch):
    """Patch email_storage.datetime with _ControlledDatetime and return it."""
    monkeypatch.setattr(email_storage, 'datetime', _ControlledDatetime)
    return _ControlledDatetime


def test_retrieve_with_from_date(fake_datetime):
    fake_datetime._ts = datetime(2026, 3, 10, 12, 0, 0)
    email_storage.store({'subject': 'Old'})

    fake_datetime._ts = datetime(2026, 3, 20, 12, 0, 0)
    email_storage.store({'subject': 'New'})

    records = email_storage.retrieve(from_date=date(2026, 3, 15))

    assert len(records) == 1
    assert records[0]['subject'] == 'New'


def test_retrieve_with_to_date(fake_datetime):
    fake_datetime._ts = datetime(2026, 3, 10, 12, 0, 0)
    email_storage.store({'subject': 'Old'})

    fake_datetime._ts = datetime(2026, 3, 20, 12, 0, 0)
    email_storage.store({'subject': 'New'})

    records = email_storage.retrieve(to_date=date(2026, 3, 15))

    assert len(records) == 1
    assert records[0]['subject'] == 'Old'


def test_retrieve_with_from_and_to_date(fake_datetime):
    fake_datetime._ts = datetime(2026, 3, 1, 0, 0, 0)
    email_storage.store({'subject': 'Before'})

    fake_datetime._ts = datetime(2026, 3, 15, 0, 0, 0)
    email_storage.store({'subject': 'Within'})

    fake_datetime._ts = datetime(2026, 3, 31, 0, 0, 0)
    email_storage.store({'subject': 'After'})

    records = email_storage.retrieve(from_date=date(2026, 3, 10), to_date=date(2026, 3, 20))

    assert len(records) == 1
    assert records[0]['subject'] == 'Within'


def test_retrieve_to_date_inclusive(fake_datetime):
    """A record stored on to_date itself must be included."""
    fake_datetime._ts = datetime(2026, 3, 20, 23, 59, 59)
    email_storage.store({'subject': 'EndOfDay'})

    records = email_storage.retrieve(to_date=date(2026, 3, 20))

    assert len(records) == 1
    assert records[0]['subject'] == 'EndOfDay'


def test_retrieve_returns_list_of_dicts():
    email_storage.store({'subject': 'Dict check', 'sender': 'x@y.com'})
    records = email_storage.retrieve()
    assert isinstance(records, list)
    assert all(isinstance(r, dict) for r in records)
