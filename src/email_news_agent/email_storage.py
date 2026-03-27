import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

_DB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database')
)
_DB_FILE = 'email_news_storage.sqlite'


def _db_path() -> str:
    return os.path.join(_DB_DIR, _DB_FILE)


def _sqlite_type(value) -> str:
    """Map a Python value to the closest SQLite column type."""
    if isinstance(value, bool):
        return 'INTEGER'
    if isinstance(value, int):
        return 'INTEGER'
    if isinstance(value, float):
        return 'REAL'
    if isinstance(value, bytes):
        return 'BLOB'
    return 'TEXT'


def _ensure_table(conn: sqlite3.Connection, data: dict) -> None:
    """Create the 'mails' table if it does not exist, or add any missing columns."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mails'"
    )
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        col_defs = ['id INTEGER PRIMARY KEY AUTOINCREMENT', 'timestamp TEXT', 'retrieved INTEGER']
        for key, value in data.items():
            col_defs.append(f'"{key}" {_sqlite_type(value)}')
        conn.execute(f"CREATE TABLE mails ({', '.join(col_defs)})")
    else:
        cursor.execute('PRAGMA table_info(mails)')
        existing = {row[1] for row in cursor.fetchall()}
        for key, value in data.items():
            if key not in existing:
                conn.execute(f'ALTER TABLE mails ADD COLUMN "{key}" {_sqlite_type(value)}')

    conn.commit()


def store(data: dict) -> None:
    """Store a dictionary as a new record in the email_news_storage database.

    The database file is created in the ``database`` folder at the project root
    if it does not already exist.  A ``timestamp`` (current date/time) and a
    ``retrieved`` flag (``False``) are added to each record automatically.

    Args:
        data: A dictionary whose keys become column names and whose values are
              stored.  Any keys not yet present in the table are added as new
              columns.
    """
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_db_path())
    try:
        _ensure_table(conn, data)
        keys = list(data.keys())
        columns = ['timestamp', 'retrieved'] + [f'"{k}"' for k in keys]
        placeholders = ['?', '?'] + ['?' for _ in keys]
        sql = f"INSERT INTO mails ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        conn.execute(sql, [datetime.now().isoformat(), 0] + [data[k] for k in keys])
        conn.commit()
    finally:
        conn.close()


def retrieve(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    filter: str = 'not retrieved',
) -> list[dict]:
    """Retrieve records from the email_news_storage database.

    All returned records have their ``retrieved`` flag set to ``True`` in the
    database after being fetched.

    Args:
        from_date: Optional start date (inclusive).  Only records whose
                   ``timestamp`` falls on or after this date are returned.
        to_date:   Optional end date (inclusive).  Only records whose
                   ``timestamp`` falls on or before this date are returned.
        filter:    Controls whether the ``retrieved`` flag is considered. Accepted
                   values (case-insensitive, '-' or '_' accepted as spaces):
                     - 'not retrieved' (default): only records with ``retrieved`` = 0
                       are returned.
                     - 'all': ignore the ``retrieved`` flag; if no other filters
                       (from_date/to_date) are provided, this will return all rows.

    Returns:
        A list of dictionaries, one per matching record.  If no arguments are
        given and the default filter is used, only records where ``retrieved`` is
        ``False`` are returned. Returns an empty list when the database or table
        does not exist.
    """
    db = _db_path()
    if not os.path.exists(db):
        return []

    # normalize filter value: allow 'not_retrieved', 'not-retrieved', etc.
    normalized_filter = (filter or 'not retrieved').strip().lower().replace('_', ' ').replace('-', ' ')
    if normalized_filter not in ('not retrieved', 'all'):
        raise ValueError("Invalid filter value for retrieve(); expected 'not retrieved' or 'all'.")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mails'"
        )
        if cursor.fetchone() is None:
            return []

        conditions: list[str] = []
        params: list = []

        # Date range filters
        if from_date is not None:
            conditions.append('timestamp >= ?')
            params.append(from_date.isoformat())
        if to_date is not None:
            next_day = (to_date + timedelta(days=1)).isoformat()
            conditions.append('timestamp < ?')
            params.append(next_day)

        # retrieved-filter: if 'not retrieved', always require retrieved = 0
        if normalized_filter == 'not retrieved':
            conditions.append('retrieved = 0')

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        cursor.execute(f'SELECT * FROM mails {where}', params)
        rows = cursor.fetchall()

        if rows:
            ids = [row['id'] for row in rows]
            conn.execute(
                f"UPDATE mails SET retrieved = 1 WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            )
            conn.commit()

        return [dict(row) for row in rows]
    finally:
        conn.close()
