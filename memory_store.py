from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_MEMORY_CHARS = 1200
MAX_CATEGORY_CHARS = 40
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bapi[_ -]?key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~-]{24,}", re.IGNORECASE),
)


def database_path() -> Path:
    override = os.environ.get("JARVIS_MEMORY_DB", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "JARVIS" / "memory.sqlite3"
    return Path.home() / ".jarvis" / "memory.sqlite3"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            UNIQUE(content COLLATE NOCASE)
        )
        """
    )
    return conn


@contextmanager
def _database():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "content": row["content"],
        "category": row["category"],
        "created_at": row["created_at"],
    }


def save_memory(content: str, category: str = "general") -> dict[str, Any]:
    text = content.strip()
    label = category.strip() or "general"
    if not text:
        raise ValueError("Memory content cannot be empty.")
    if len(text) > MAX_MEMORY_CHARS:
        raise ValueError(f"Memory exceeds the {MAX_MEMORY_CHARS}-character limit.")
    if len(label) > MAX_CATEGORY_CHARS:
        raise ValueError(f"Category exceeds the {MAX_CATEGORY_CHARS}-character limit.")
    if any(pattern.search(value) for value in (text, label) for pattern in _SECRET_PATTERNS):
        raise ValueError("This looks like a password, API key, access token, or private key. JARVIS will not save secrets.")

    with _database() as conn:
        existing = conn.execute(
            "SELECT id, content, category, created_at FROM memories WHERE content = ? COLLATE NOCASE",
            (text,),
        ).fetchone()
        if existing:
            return {"ok": True, "saved": False, "duplicate": True, "memory": _record(existing)}
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = conn.execute(
            "INSERT INTO memories(content, category, created_at) VALUES (?, ?, ?)",
            (text, label, created),
        )
        row = conn.execute(
            "SELECT id, content, category, created_at FROM memories WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return {"ok": True, "saved": True, "memory": _record(row)}


def update_memory(memory_id: int, content: str, category: str = "general") -> dict[str, Any]:
    try:
        memory_id = int(memory_id)
    except (TypeError, ValueError):
        raise ValueError("Provide the exact numeric memory ID.") from None
    text = content.strip()
    label = category.strip() or "general"
    if memory_id < 1:
        raise ValueError("Provide the exact numeric memory ID.")
    if not text:
        raise ValueError("Memory content cannot be empty.")
    if len(text) > MAX_MEMORY_CHARS:
        raise ValueError(f"Memory exceeds the {MAX_MEMORY_CHARS}-character limit.")
    if len(label) > MAX_CATEGORY_CHARS:
        raise ValueError(f"Category exceeds the {MAX_CATEGORY_CHARS}-character limit.")
    if any(pattern.search(value) for value in (text, label) for pattern in _SECRET_PATTERNS):
        raise ValueError("This looks like a password, API key, access token, or private key. JARVIS will not save secrets.")

    with _database() as conn:
        row = conn.execute(
            "SELECT id, content, category, created_at FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if not row:
            raise ValueError("No saved memory exists with that ID.")
        try:
            conn.execute(
                "UPDATE memories SET content = ?, category = ? WHERE id = ?",
                (text, label, memory_id),
            )
        except sqlite3.IntegrityError:
            raise ValueError("An identical memory is already saved.") from None
        updated = conn.execute(
            "SELECT id, content, category, created_at FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        return {"ok": True, "updated": True, "memory": _record(updated)}


def search_memories(query: str, limit: int = 10) -> dict[str, Any]:
    term = query.strip()
    if not term:
        raise ValueError("Provide a non-empty search phrase.")
    if len(term) > 200:
        raise ValueError("Search phrase exceeds the 200-character limit.")
    limit = max(1, min(int(limit), 20))
    with _database() as conn:
        rows = conn.execute(
            """
            SELECT id, content, category, created_at
            FROM memories
            WHERE instr(lower(content), lower(?)) > 0
               OR instr(lower(category), lower(?)) > 0
            ORDER BY id DESC LIMIT ?
            """,
            (term, term, limit),
        ).fetchall()
    return {"ok": True, "query": term, "count": len(rows), "memories": [_record(r) for r in rows]}


def list_memories(limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    with _database() as conn:
        rows = conn.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return {"ok": True, "total": int(count), "memories": [_record(r) for r in rows]}


def export_memories() -> dict[str, Any]:
    with _database() as conn:
        rows = conn.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY id"
        ).fetchall()
    return {"ok": True, "total": len(rows), "memories": [_record(row) for row in rows]}


def forget_memory(memory_id: int) -> dict[str, Any]:
    try:
        memory_id = int(memory_id)
    except (TypeError, ValueError):
        raise ValueError("Provide the exact numeric memory ID.") from None
    if memory_id < 1:
        raise ValueError("Provide the exact numeric memory ID.")
    with _database() as conn:
        row = conn.execute(
            "SELECT id, content, category, created_at FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if not row:
            raise ValueError("No saved memory exists with that ID.")
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    return {"ok": True, "forgotten": _record(row), "message": "Only this exact memory was deleted."}
