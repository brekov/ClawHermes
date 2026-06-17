"""
ClawHermes - 会话持久化管理
基于 SQLite 的会话存储，重启不丢失
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from clawhermes.agent.exceptions import (
    SessionExpiredError,
    SessionNotFoundError,
)


class SessionManager:
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        agent_name TEXT DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        metadata TEXT DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT DEFAULT '',
        tool_calls TEXT,
        tool_call_id TEXT,
        name TEXT,
        timestamp REAL NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    """

    def __init__(self, data_dir: str | Path, max_age_hours: int = 720):
        self._db_path = Path(data_dir) / "sessions.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_age = max_age_hours * 3600
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def create_session(self, agent_name: str = "", metadata: dict | None = None) -> str:
        with self._lock:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            now = time.time()
            meta_json = json.dumps(metadata or {}, ensure_ascii=False)
            assert self._conn is not None
            self._conn.execute(
                "INSERT INTO sessions (id, agent_name, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (session_id, agent_name, now, now, meta_json),
            )
            self._conn.commit()
            return session_id

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT id, agent_name, created_at, updated_at, metadata FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                raise SessionNotFoundError(f"会话不存在: {session_id}", session_id=session_id)

            if time.time() - row[3] > self._max_age:
                raise SessionExpiredError(f"会话已过期: {session_id}", session_id=session_id)

            return {
                "id": row[0],
                "agent_name": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "metadata": json.loads(row[4]),
            }

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            assert self._conn is not None
            rows = self._conn.execute(
                "SELECT id, agent_name, created_at, updated_at, metadata FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "agent_name": r[1],
                    "created_at": r[2],
                    "updated_at": r[3],
                    "metadata": json.loads(r[4]),
                }
                for r in rows
            ]

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            assert self._conn is not None
            cursor = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def add_message(self, session_id: str, role: str, content: str = "",
                    tool_calls: list | None = None, tool_call_id: str | None = None,
                    name: str | None = None):
        with self._lock:
            assert self._conn is not None
            now = time.time()
            tc_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, name, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, role, content, tc_json, tool_call_id, name, now),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            self._conn.commit()

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            assert self._conn is not None
            rows = self._conn.execute(
                "SELECT role, content, tool_calls, tool_call_id, name, timestamp "
                "FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            messages = []
            for r in rows:
                msg: dict[str, Any] = {"role": r[0], "content": r[1]}
                if r[2]:
                    msg["tool_calls"] = json.loads(r[2])
                if r[3]:
                    msg["tool_call_id"] = r[3]
                if r[4]:
                    msg["name"] = r[4]
                messages.append(msg)
            return messages

    def cleanup_expired(self) -> int:
        with self._lock:
            assert self._conn is not None
            cutoff = time.time() - self._max_age
            cursor = self._conn.execute(
                "DELETE FROM sessions WHERE updated_at < ?", (cutoff,)
            )
            self._conn.commit()
            return cursor.rowcount
