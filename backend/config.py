from __future__ import annotations

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "config.db")


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
    # Migrate images table: add description column if missing
    img_cols = {r[1] for r in cursor.execute("PRAGMA table_info(images)").fetchall()}
    if img_cols and "description" not in img_cols:
        cursor.execute("ALTER TABLE images ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    # Ensure a single config row exists
    cursor.execute("INSERT OR IGNORE INTO llm_config (id) VALUES (1)")
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
                      temperature: float, max_tokens: int) -> dict:
    conn = get_db()
    conn.execute("""
        UPDATE llm_config SET provider_type = ?, provider_url = ?, api_key = ?,
            model_name = ?, api_version = ?, temperature = ?, max_tokens = ?
        WHERE id = 1
    """, (provider_type, provider_url, api_key, model_name, api_version,
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
