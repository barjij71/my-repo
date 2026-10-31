from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from memory_store import database_path

MAX_CHAT_MESSAGES = 500
CHAT_CONTEXT_MESSAGES = 12


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def load_messages(limit: int = MAX_CHAT_MESSAGES) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), MAX_CHAT_MESSAGES))
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT role, content, created_at
            FROM chat_messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]
    finally:
        conn.close()


def save_exchange(user_message: str, assistant_message: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.executemany(
            "INSERT INTO chat_messages(role, content, created_at) VALUES (?, ?, ?)",
            [
                ("user", user_message, created_at),
                ("assistant", assistant_message, created_at),
            ],
        )
        conn.execute(
            """
            DELETE FROM chat_messages
            WHERE id NOT IN (
                SELECT id FROM chat_messages ORDER BY id DESC LIMIT ?
            )
            """,
            (MAX_CHAT_MESSAGES,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clear_messages() -> int:
    conn = _connect()
    try:
        deleted = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        conn.execute("DELETE FROM chat_messages")
        conn.commit()
        return int(deleted)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
