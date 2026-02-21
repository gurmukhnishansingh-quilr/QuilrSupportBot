from __future__ import annotations

import sqlite3
import os
import hashlib
import hmac
import secrets
import base64
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "config.db")
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 200_000
ADMIN_SESSION_HOURS = 72


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS
    )
    digest_b64 = base64.b64encode(digest).decode("utf-8")
    return f"{PASSWORD_HASH_PREFIX}${PASSWORD_HASH_ITERATIONS}${salt}${digest_b64}"


def _verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    parts = stored_hash.split("$", 3)
    if len(parts) != 4:
        return False
    prefix, iterations, salt, expected = parts
    if prefix != PASSWORD_HASH_PREFIX:
        return False
    try:
        iter_count = int(iterations)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iter_count
    )
    actual = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(actual, expected)


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            provider_type TEXT NOT NULL DEFAULT 'openai',
            provider_url TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            model_name TEXT NOT NULL DEFAULT '',
            api_version TEXT NOT NULL DEFAULT '',
            include_video_transcripts_in_rag INTEGER NOT NULL DEFAULT 0,
            temperature REAL NOT NULL DEFAULT 0.7,
            max_tokens INTEGER NOT NULL DEFAULT 1024
        )
    """)
    # Migrate existing tables: add new columns if missing
    existing = {r[1] for r in cursor.execute("PRAGMA table_info(llm_config)").fetchall()}
    if "provider_type" not in existing:
        cursor.execute("ALTER TABLE llm_config ADD COLUMN provider_type TEXT NOT NULL DEFAULT 'openai'")
    if "api_version" not in existing:
        cursor.execute("ALTER TABLE llm_config ADD COLUMN api_version TEXT NOT NULL DEFAULT ''")
    if "include_video_transcripts_in_rag" not in existing:
        cursor.execute("ALTER TABLE llm_config ADD COLUMN include_video_transcripts_in_rag INTEGER NOT NULL DEFAULT 0")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            upload_date TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            link TEXT NOT NULL DEFAULT ''
        )
    """)
    # Migrate documents table: add link column if missing
    doc_cols = {r[1] for r in cursor.execute("PRAGMA table_info(documents)").fetchall()}
    if "link" not in doc_cols:
        cursor.execute("ALTER TABLE documents ADD COLUMN link TEXT NOT NULL DEFAULT ''")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            transcript TEXT NOT NULL DEFAULT ''
        )
    """)
    # Migrate video_links table: add transcript column if missing
    video_cols = {r[1] for r in cursor.execute("PRAGMA table_info(video_links)").fetchall()}
    if video_cols and "transcript" not in video_cols:
        cursor.execute("ALTER TABLE video_links ADD COLUMN transcript TEXT NOT NULL DEFAULT ''")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            upload_date TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL DEFAULT ''
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    # Migrate images table: add description column if missing
    img_cols = {r[1] for r in cursor.execute("PRAGMA table_info(images)").fetchall()}
    if img_cols and "description" not in img_cols:
        cursor.execute("ALTER TABLE images ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    # Ensure a single config row exists
    cursor.execute("INSERT OR IGNORE INTO llm_config (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO admin_settings (id) VALUES (1)")
    row = cursor.execute(
        "SELECT password_hash FROM admin_settings WHERE id = 1"
    ).fetchone()
    if row and not row["password_hash"]:
        default_password = os.getenv("ADMIN_PASSWORD", "admin")
        cursor.execute(
            "UPDATE admin_settings SET password_hash = ? WHERE id = 1",
            (_hash_password(default_password),)
        )
    now_iso = _utc_now().isoformat()
    cursor.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now_iso,))
    conn.commit()
    conn.close()


def verify_admin_password(password: str) -> bool:
    if not password:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT password_hash FROM admin_settings WHERE id = 1"
    ).fetchone()
    conn.close()
    if not row:
        return False
    return _verify_password(password, row["password_hash"])


def create_admin_session() -> dict:
    conn = get_db()
    token = secrets.token_urlsafe(48)
    now = _utc_now()
    expires_at = now + timedelta(hours=ADMIN_SESSION_HOURS)
    conn.execute(
        "INSERT INTO admin_sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
        (token, now.isoformat(), expires_at.isoformat())
    )
    conn.commit()
    conn.close()
    return {"session_token": token, "expires_at": expires_at.isoformat()}


def validate_admin_session(token: str) -> bool:
    if not token:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT token, expires_at FROM admin_sessions WHERE token = ?",
        (token,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    try:
        expires_at = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        conn.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _utc_now():
        conn.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return False
    conn.close()
    return True


def delete_admin_session(token: str):
    if not token:
        return
    conn = get_db()
    conn.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def delete_all_admin_sessions():
    conn = get_db()
    conn.execute("DELETE FROM admin_sessions")
    conn.commit()
    conn.close()


def change_admin_password(new_password: str):
    conn = get_db()
    conn.execute(
        "UPDATE admin_settings SET password_hash = ? WHERE id = 1",
        (_hash_password(new_password),)
    )
    conn.commit()
    conn.close()


def get_llm_config() -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM llm_config WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return {}
    return dict(row)


def update_llm_config(provider_type: str, provider_url: str, api_key: str,
                      model_name: str, api_version: str,
                      include_video_transcripts_in_rag: bool,
                      temperature: float, max_tokens: int) -> dict:
    conn = get_db()
    conn.execute("""
        UPDATE llm_config SET provider_type = ?, provider_url = ?, api_key = ?,
            model_name = ?, api_version = ?, include_video_transcripts_in_rag = ?,
            temperature = ?, max_tokens = ?
        WHERE id = 1
    """, (provider_type, provider_url, api_key, model_name, api_version,
          1 if include_video_transcripts_in_rag else 0,
          temperature, max_tokens))
    conn.commit()
    row = conn.execute("SELECT * FROM llm_config WHERE id = 1").fetchone()
    conn.close()
    return dict(row)


def add_document(filename: str, chunk_count: int = 0,
                 status: str = "pending") -> dict:
    conn = get_db()
    now = datetime.utcnow().isoformat()
    try:
        conn.execute("""
            INSERT INTO documents (filename, upload_date, chunk_count, status)
            VALUES (?, ?, ?, ?)
        """, (filename, now, chunk_count, status))
        conn.commit()
        doc_id = conn.execute(
            "SELECT id FROM documents WHERE filename = ?", (filename,)
        ).fetchone()["id"]
    except sqlite3.IntegrityError:
        # Already exists — update instead
        conn.execute("""
            UPDATE documents SET chunk_count = ?, status = ?, upload_date = ?
            WHERE filename = ?
        """, (chunk_count, status, now, filename))
        conn.commit()
        doc_id = conn.execute(
            "SELECT id FROM documents WHERE filename = ?", (filename,)
        ).fetchone()["id"]
    conn.close()
    return get_document(doc_id)


def get_document(doc_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_document_by_filename(filename: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM documents WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_documents() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY upload_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document(doc_id: int) -> bool:
    conn = get_db()
    cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def update_document_status(doc_id: int, status: str,
                           chunk_count: int | None = None):
    conn = get_db()
    if chunk_count is not None:
        conn.execute(
            "UPDATE documents SET status = ?, chunk_count = ? WHERE id = ?",
            (status, chunk_count, doc_id)
        )
    else:
        conn.execute(
            "UPDATE documents SET status = ? WHERE id = ?", (status, doc_id)
        )
    conn.commit()
    conn.close()


def update_document_link(doc_id: int, link: str) -> dict | None:
    conn = get_db()
    conn.execute("UPDATE documents SET link = ? WHERE id = ?", (link, doc_id))
    conn.commit()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_document_links() -> dict:
    """Return a mapping of filename -> link for all documents that have links."""
    conn = get_db()
    rows = conn.execute(
        "SELECT filename, link FROM documents WHERE link != ''"
    ).fetchall()
    conn.close()
    return {r["filename"]: r["link"] for r in rows}


# --- Video Links ---

def list_video_links() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM video_links ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_video_link(title: str, url: str, description: str = "",
                   transcript: str = "") -> dict:
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO video_links (title, url, description, transcript) VALUES (?, ?, ?, ?)",
        (title, url, description, transcript)
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM video_links WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    conn.close()
    return dict(row)


def delete_video_link(link_id: int) -> bool:
    conn = get_db()
    cursor = conn.execute("DELETE FROM video_links WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def update_video_link_transcript(link_id: int, transcript: str) -> dict | None:
    conn = get_db()
    conn.execute(
        "UPDATE video_links SET transcript = ? WHERE id = ?",
        (transcript, link_id)
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM video_links WHERE id = ?", (link_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# --- Images ---

def list_images() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM images ORDER BY upload_date DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_image(filename: str, original_name: str,
              description: str = "") -> dict:
    conn = get_db()
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        "INSERT INTO images (filename, original_name, description, upload_date) VALUES (?, ?, ?, ?)",
        (filename, original_name, description, now)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def update_image_description(image_id: int, description: str) -> dict | None:
    conn = get_db()
    conn.execute("UPDATE images SET description = ? WHERE id = ?", (description, image_id))
    conn.commit()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_image(image_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row:
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        conn.commit()
    conn.close()
    return dict(row) if row else None
