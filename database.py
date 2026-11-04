"""SQLite database layer for AI Study Buddy."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "study_buddy.db"


@contextmanager
def get_connection():
    """Open a connection, commit on success, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                document_id INTEGER,
                title TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS quiz_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                document_id INTEGER,
                document_name TEXT,
                difficulty TEXT,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
            );
            """
        )


# ---------- Documents ----------

def add_document(user_id, filename, content):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO documents (user_id, filename, content) VALUES (?, ?, ?)",
            (user_id, filename, content),
        )
        return cur.lastrowid


def list_documents(user_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, filename, content, uploaded_at, LENGTH(content) AS chars
            FROM documents WHERE user_id = ? ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()


def get_document(user_id, doc_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        ).fetchone()


def delete_document(user_id, doc_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        )


# ---------- Chats ----------

def create_chat(user_id, document_id, title):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO chats (user_id, document_id, title) VALUES (?, ?, ?)",
            (user_id, document_id, title),
        )
        return cur.lastrowid


def list_chats(user_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, title, document_id FROM chats WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()


def get_chat(user_id, chat_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()


def delete_chat(user_id, chat_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM chats WHERE id = ? AND user_id = ?",
            (chat_id, user_id),
        )


def add_message(chat_id, role, content):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )


def get_messages(chat_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT role, content FROM chat_messages WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()


# ---------- Quiz sessions ----------

def add_quiz_session(user_id, document_id, document_name, difficulty, score, total):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO quiz_sessions
                (user_id, document_id, document_name, difficulty, score, total)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, document_id, document_name, difficulty, score, total),
        )


def list_quiz_sessions(user_id):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT document_name, difficulty, score, total, created_at
            FROM quiz_sessions WHERE user_id = ? ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
