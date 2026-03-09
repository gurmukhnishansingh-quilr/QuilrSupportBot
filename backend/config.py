from __future__ import annotations

import sqlite3
import os
import hashlib
import hmac
import secrets
import base64
import json
import re
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "config.db")
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 200_000
ADMIN_SESSION_HOURS = 72
ACCESS_ENTITY_TYPES = {"document", "video", "image"}
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_oauth_access_emails (
            email TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_access (
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id, email)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            actor_type TEXT NOT NULL DEFAULT '',
            actor_email TEXT NOT NULL DEFAULT '',
            actor_first_name TEXT NOT NULL DEFAULT '',
            actor_last_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'success',
            target_type TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '',
            ip_address TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    audit_cols = {r[1] for r in cursor.execute("PRAGMA table_info(audit_logs)").fetchall()}
    if audit_cols and "actor_first_name" not in audit_cols:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN actor_first_name TEXT NOT NULL DEFAULT ''")
    if audit_cols and "actor_last_name" not in audit_cols:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN actor_last_name TEXT NOT NULL DEFAULT ''")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_email ON audit_logs(actor_email)")
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


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _normalize_person_name(value: str) -> str:
    return " ".join((value or "").strip().split())


def _normalize_entity_type(entity_type: str) -> str:
    normalized = (entity_type or "").strip().lower()
    if normalized not in ACCESS_ENTITY_TYPES:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    return normalized


def normalize_content_access_emails(emails: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen = set()
    for raw in emails or []:
        email = _normalize_email(raw)
        if not email:
            continue
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError(f"Invalid email format: {raw}")
        if email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return normalized


def list_admin_oauth_access_emails() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT email, created_at FROM admin_oauth_access_emails ORDER BY email"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_admin_oauth_access_email(email: str) -> dict:
    normalized = _normalize_email(email)
    if not normalized:
        raise ValueError("Email is required")
    conn = get_db()
    now = _utc_now().isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO admin_oauth_access_emails (email, created_at) VALUES (?, ?)",
        (normalized, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT email, created_at FROM admin_oauth_access_emails WHERE email = ?",
        (normalized,),
    ).fetchone()
    conn.close()
    return dict(row) if row else {"email": normalized, "created_at": now}


def delete_admin_oauth_access_email(email: str) -> bool:
    normalized = _normalize_email(email)
    if not normalized:
        return False
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM admin_oauth_access_emails WHERE email = ?",
        (normalized,),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def is_admin_oauth_email_allowed(email: str) -> bool:
    normalized = _normalize_email(email)
    if not normalized:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT email FROM admin_oauth_access_emails WHERE email = ?",
        (normalized,),
    ).fetchone()
    conn.close()
    return bool(row)


def list_content_access_emails(entity_type: str, entity_id: int) -> list[str]:
    normalized_type = _normalize_entity_type(entity_type)
    conn = get_db()
    rows = conn.execute(
        """
        SELECT email FROM content_access
        WHERE entity_type = ? AND entity_id = ?
        ORDER BY email
        """,
        (normalized_type, int(entity_id)),
    ).fetchall()
    conn.close()
    return [r["email"] for r in rows]


def get_content_access_map(entity_type: str, entity_ids: list[int] | None = None) -> dict[int, list[str]]:
    normalized_type = _normalize_entity_type(entity_type)
    ids = sorted({int(i) for i in (entity_ids or []) if int(i) > 0})
    conn = get_db()
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        rows = conn.execute(
            f"""
            SELECT entity_id, email
            FROM content_access
            WHERE entity_type = ? AND entity_id IN ({placeholders})
            ORDER BY entity_id, email
            """,
            [normalized_type, *ids],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT entity_id, email
            FROM content_access
            WHERE entity_type = ?
            ORDER BY entity_id, email
            """,
            (normalized_type,),
        ).fetchall()
    conn.close()

    access_map: dict[int, list[str]] = {}
    for row in rows:
        entity_id = int(row["entity_id"])
        access_map.setdefault(entity_id, []).append(row["email"])
    return access_map


def set_content_access_emails(entity_type: str, entity_id: int, emails: list[str] | None) -> list[str]:
    normalized_type = _normalize_entity_type(entity_type)
    normalized_emails = normalize_content_access_emails(emails)
    entity_id_int = int(entity_id)
    if entity_id_int <= 0:
        raise ValueError("entity_id must be a positive integer")

    conn = get_db()
    conn.execute(
        "DELETE FROM content_access WHERE entity_type = ? AND entity_id = ?",
        (normalized_type, entity_id_int),
    )
    now = _utc_now().isoformat()
    for email in normalized_emails:
        conn.execute(
            """
            INSERT INTO content_access (entity_type, entity_id, email, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (normalized_type, entity_id_int, email, now),
        )
    conn.commit()
    conn.close()
    return normalized_emails


def delete_content_access(entity_type: str, entity_id: int):
    normalized_type = _normalize_entity_type(entity_type)
    conn = get_db()
    conn.execute(
        "DELETE FROM content_access WHERE entity_type = ? AND entity_id = ?",
        (normalized_type, int(entity_id)),
    )
    conn.commit()
    conn.close()


def is_entity_visible_to_email(entity_type: str, entity_id: int, email: str) -> bool:
    normalized_type = _normalize_entity_type(entity_type)
    entity_id_int = int(entity_id)
    normalized_email = _normalize_email(email)

    conn = get_db()
    total = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM content_access
        WHERE entity_type = ? AND entity_id = ?
        """,
        (normalized_type, entity_id_int),
    ).fetchone()["cnt"]
    if total == 0:
        conn.close()
        return True
    if not normalized_email:
        conn.close()
        return False
    row = conn.execute(
        """
        SELECT email FROM content_access
        WHERE entity_type = ? AND entity_id = ? AND email = ?
        """,
        (normalized_type, entity_id_int, normalized_email),
    ).fetchone()
    conn.close()
    return bool(row)


def filter_items_by_access_email(entity_type: str, items: list[dict], email: str) -> list[dict]:
    normalized_type = _normalize_entity_type(entity_type)
    normalized_email = _normalize_email(email)
    ids = []
    for item in items:
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id > 0:
            ids.append(item_id)

    access_map = get_content_access_map(normalized_type, ids)
    filtered = []
    for item in items:
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        allowed = access_map.get(item_id, [])
        if not allowed:
            filtered.append(item)
            continue
        if normalized_email and normalized_email in allowed:
            filtered.append(item)
    return filtered


def add_audit_log(event_type: str, actor_type: str = "", actor_email: str = "",
                  actor_first_name: str = "", actor_last_name: str = "",
                  status: str = "success", target_type: str = "",
                  target_id: str = "", message: str = "",
                  metadata: dict | list | str | None = None,
                  ip_address: str = "") -> dict:
    event = (event_type or "").strip()
    if not event:
        raise ValueError("event_type is required")

    actor_type_norm = (actor_type or "").strip()
    actor_email_norm = _normalize_email(actor_email)
    actor_first_name_norm = _normalize_person_name(actor_first_name)
    actor_last_name_norm = _normalize_person_name(actor_last_name)
    status_norm = (status or "success").strip().lower() or "success"
    target_type_norm = (target_type or "").strip().lower()
    target_id_norm = str(target_id or "").strip()
    message_norm = (message or "").strip()
    ip_norm = (ip_address or "").strip()
    now = _utc_now().isoformat()

    if isinstance(metadata, (dict, list)):
        metadata_text = json.dumps(metadata, ensure_ascii=True)
    elif metadata is None:
        metadata_text = ""
    else:
        metadata_text = str(metadata).strip()

    conn = get_db()
    cursor = conn.execute(
        """
        INSERT INTO audit_logs (
            event_type, actor_type, actor_email, actor_first_name, actor_last_name, status,
            target_type, target_id, message, metadata, ip_address, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event,
            actor_type_norm,
            actor_email_norm,
            actor_first_name_norm,
            actor_last_name_norm,
            status_norm,
            target_type_norm,
            target_id_norm,
            message_norm,
            metadata_text,
            ip_norm,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM audit_logs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def list_audit_logs(limit: int = 200, offset: int = 0, event_type: str = "",
                    actor_email: str = "", status: str = "") -> list[dict]:
    limit_clamped = min(max(int(limit or 50), 1), 1000)
    offset_clamped = max(int(offset or 0), 0)
    filters = []
    params: list[str | int] = []

    event = (event_type or "").strip()
    if event:
        filters.append("event_type = ?")
        params.append(event)

    actor = _normalize_email(actor_email)
    if actor:
        filters.append("actor_email = ?")
        params.append(actor)

    status_norm = (status or "").strip().lower()
    if status_norm:
        filters.append("status = ?")
        params.append(status_norm)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT *
        FROM audit_logs
        {where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit_clamped, offset_clamped])

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    out = []
    for row in rows:
        item = dict(row)
        meta_text = (item.get("metadata") or "").strip()
        if meta_text:
            try:
                item["metadata_json"] = json.loads(meta_text)
            except json.JSONDecodeError:
                item["metadata_json"] = None
        else:
            item["metadata_json"] = None
        out.append(item)
    return out


def list_user_activity(limit: int = 300, email_query: str = "") -> list[dict]:
    limit_clamped = min(max(int(limit or 300), 1), 2000)
    q = _normalize_email(email_query)
    params: list[str | int] = []
    where = "WHERE a.actor_email != ''"
    if q:
        where += " AND a.actor_email LIKE ?"
        params.append(f"%{q}%")
    params.append(limit_clamped)

    conn = get_db()
    rows = conn.execute(
        f"""
        SELECT a.actor_email,
               COUNT(*) AS event_count,
               MAX(a.created_at) AS last_seen,
               GROUP_CONCAT(DISTINCT a.actor_type) AS actor_types,
               COALESCE(
                 (
                   SELECT x.actor_first_name
                   FROM audit_logs x
                   WHERE x.actor_email = a.actor_email
                     AND x.actor_first_name != ''
                   ORDER BY x.created_at DESC, x.id DESC
                   LIMIT 1
                 ),
                 ''
               ) AS first_name,
               COALESCE(
                 (
                   SELECT x.actor_last_name
                   FROM audit_logs x
                   WHERE x.actor_email = a.actor_email
                     AND x.actor_last_name != ''
                   ORDER BY x.created_at DESC, x.id DESC
                   LIMIT 1
                 ),
                 ''
               ) AS last_name
        FROM audit_logs a
        {where}
        GROUP BY a.actor_email
        ORDER BY last_seen DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()

    out = []
    for row in rows:
        actor_types_raw = (row["actor_types"] or "").strip()
        actor_types = [t for t in actor_types_raw.split(",") if t] if actor_types_raw else []
        out.append({
            "email": row["actor_email"],
            "first_name": row["first_name"] or "",
            "last_name": row["last_name"] or "",
            "event_count": int(row["event_count"] or 0),
            "last_seen": row["last_seen"] or "",
            "actor_types": actor_types,
        })
    return out


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
    conn.execute(
        "DELETE FROM content_access WHERE entity_type = 'document' AND entity_id = ?",
        (doc_id,),
    )
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
    conn.execute(
        "DELETE FROM content_access WHERE entity_type = 'video' AND entity_id = ?",
        (link_id,),
    )
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


def update_video_link_description(link_id: int, description: str) -> dict | None:
    conn = get_db()
    conn.execute(
        "UPDATE video_links SET description = ? WHERE id = ?",
        (description, link_id)
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
        conn.execute(
            "DELETE FROM content_access WHERE entity_type = 'image' AND entity_id = ?",
            (image_id,),
        )
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        conn.commit()
    conn.close()
    return dict(row) if row else None
