import os
import re
import json
import time
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlencode, parse_qsl, urlsplit, urlunsplit
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from config import (
    init_db, get_llm_config, update_llm_config,
    list_documents, delete_document, get_document, update_document_link,
    list_video_links, add_video_link, delete_video_link, update_video_link_transcript,
    update_video_link_description,
    list_images, add_image, update_image_description, delete_image,
    verify_admin_password, create_admin_session, validate_admin_session,
    delete_admin_session, delete_all_admin_sessions, change_admin_password,
    list_admin_oauth_access_emails, add_admin_oauth_access_email,
    delete_admin_oauth_access_email, is_admin_oauth_email_allowed,
    get_content_access_map, set_content_access_emails, is_entity_visible_to_email,
    add_audit_log, list_audit_logs, list_user_activity,
)
from embeddings import (
    auto_index_documents, index_pdf, remove_document_embeddings,
    reindex_all_documents, DOCUMENTS_DIR, auto_index_video_transcripts,
    index_video_transcript, remove_video_transcript_embeddings
)
from chat import (
    chat_stream, test_llm_connection, generate_description_from_transcript,
    generate_description_from_image,
)

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "videos")
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov"}
TRANSCRIPT_EXTENSIONS = {".txt", ".srt", ".vtt", ".md"}
MAX_TRANSCRIPT_BYTES = 1_000_000
MAX_TRANSCRIPT_CHARS = 30_000
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "images")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
CHAT_AUTH_COOKIE = "chat_auth_session"
CHAT_SESSION_TTL_SECONDS = 24 * 60 * 60
OAUTH_STATE_TTL_SECONDS = 10 * 60

oauth_states: dict[str, dict] = {}
chat_sessions: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    print("Database initialized")
    print("Auto-indexing documents...")
    count = auto_index_documents()
    print(f"Auto-indexed {count} new document(s)")
    transcript_count = auto_index_video_transcripts()
    print(f"Auto-indexed transcripts for {transcript_count} video(s)")
    yield
    # Shutdown (nothing needed)


app = FastAPI(title="Quilly Support", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth ---

def verify_admin(request: Request):
    session_token = request.headers.get("X-Admin-Session", "").strip()
    if session_token and validate_admin_session(session_token):
        request.state.admin_session_token = session_token
        request.state.admin_auth_method = "session"
        return

    oauth_user = _resolve_chat_user_from_request(request)
    email = (oauth_user or {}).get("email", "").strip().lower()
    if oauth_user and email and is_admin_oauth_email_allowed(email):
        request.state.admin_oauth_user = oauth_user
        request.state.admin_auth_method = "oauth"
        return

    # Backward-compatible fallback for clients still sending plain password.
    password = request.headers.get("X-Admin-Password", "")
    if password and verify_admin_password(password):
        request.state.admin_auth_method = "password-header"
        return

    raise HTTPException(status_code=401, detail="Unauthorized")


# --- Pydantic Models ---

class LLMConfigUpdate(BaseModel):
    provider_type: str = "openai"
    provider_url: str
    api_key: str
    model_name: str
    api_version: str = ""
    include_video_transcripts_in_rag: bool = False
    temperature: float = 0.7
    max_tokens: int = 1024


class ChatRequest(BaseModel):
    question: str


class AdminLoginRequest(BaseModel):
    password: str


class AdminPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class AdminOAuthEmailRequest(BaseModel):
    email: str


class VideoLinkCreate(BaseModel):
    title: str
    url: str
    description: str = ""
    transcript: str = ""


class DocumentLinkUpdate(BaseModel):
    link: str = ""


class ImageDescriptionUpdate(BaseModel):
    description: str = ""


class ContentAccessUpdate(BaseModel):
    emails: list[str] = []


# --- Helpers ---

def _clean_transcript_text(text: str, ext: str) -> str:
    if ext not in {".srt", ".vtt"}:
        return text.strip()

    cleaned_lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        if stripped.upper() == "WEBVTT":
            continue
        if stripped.startswith("NOTE"):
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        if "-->" in stripped:
            continue

        cleaned_lines.append(stripped)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_transcript_text(text: str) -> str:
    transcript = (text or "").strip()
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Transcript is too long. Maximum {MAX_TRANSCRIPT_CHARS} characters."
        )
    return transcript


async def _read_transcript_upload(transcript_file: UploadFile) -> str:
    ext = os.path.splitext(transcript_file.filename or "")[1].lower()
    if ext not in TRANSCRIPT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported transcript format. Allowed: {', '.join(sorted(TRANSCRIPT_EXTENSIONS))}"
        )

    content = await transcript_file.read()
    if len(content) > MAX_TRANSCRIPT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Transcript file is too large. Maximum {MAX_TRANSCRIPT_BYTES // 1_000_000} MB."
        )

    text = content.decode("utf-8-sig", errors="replace")
    cleaned = _clean_transcript_text(text, ext)
    return _normalize_transcript_text(cleaned)


def _sync_video_transcript_index(video_link: dict):
    """Best-effort transcript indexing; should not fail main admin actions."""
    try:
        index_video_transcript(video_link)
    except Exception as e:
        print(f"Warning: failed transcript indexing for video {video_link.get('id')}: {e}")


def _normalize_admin_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Email is required.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=400, detail="Invalid email format.")
    return normalized


def _normalize_person_name(value: str) -> str:
    return " ".join((value or "").strip().split())


def _split_display_name(name: str) -> tuple[str, str]:
    cleaned = _normalize_person_name(name)
    if not cleaned:
        return "", ""
    parts = cleaned.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def _chat_user_email(request: Request) -> str:
    user = _resolve_chat_user_from_request(request)
    return ((user or {}).get("email") or "").strip().lower()


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for", "") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return ""


def _audit_actor(request: Request, actor_email: str = "", actor_type: str = "",
                 actor_first_name: str = "", actor_last_name: str = "") -> tuple[str, str, str, str]:
    forced_email = (actor_email or "").strip().lower()
    forced_type = (actor_type or "").strip()
    forced_first_name = _normalize_person_name(actor_first_name)
    forced_last_name = _normalize_person_name(actor_last_name)

    def _names_for_email(email: str) -> tuple[str, str]:
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            return "", ""

        oauth_user = getattr(request.state, "admin_oauth_user", None) or {}
        oauth_email = (oauth_user.get("email") or "").strip().lower()
        if oauth_email and oauth_email == normalized_email:
            oauth_first = _normalize_person_name(oauth_user.get("first_name") or "")
            oauth_last = _normalize_person_name(oauth_user.get("last_name") or "")
            if oauth_first or oauth_last:
                return oauth_first, oauth_last

        chat_user = _resolve_chat_user_from_request(request) or {}
        chat_email = (chat_user.get("email") or "").strip().lower()
        if chat_email and chat_email == normalized_email:
            chat_first = _normalize_person_name(chat_user.get("first_name") or "")
            chat_last = _normalize_person_name(chat_user.get("last_name") or "")
            if chat_first or chat_last:
                return chat_first, chat_last
        return "", ""

    if forced_email or forced_type or forced_first_name or forced_last_name:
        if forced_email and not (forced_first_name or forced_last_name):
            inferred_first, inferred_last = _names_for_email(forced_email)
            forced_first_name = forced_first_name or inferred_first
            forced_last_name = forced_last_name or inferred_last
        return forced_email, (forced_type or "system"), forced_first_name, forced_last_name

    admin_method = getattr(request.state, "admin_auth_method", "")
    if admin_method == "oauth":
        oauth_user = getattr(request.state, "admin_oauth_user", None) or {}
        first_name = _normalize_person_name(oauth_user.get("first_name") or "")
        last_name = _normalize_person_name(oauth_user.get("last_name") or "")
        if not (first_name or last_name):
            first_name, last_name = _split_display_name(oauth_user.get("name") or "")
        return (oauth_user.get("email") or "").strip().lower(), "admin-oauth", first_name, last_name
    if admin_method == "session":
        return "", "admin-session", "", ""
    if admin_method == "password-header":
        return "", "admin-password-header", "", ""

    chat_user = _resolve_chat_user_from_request(request) or {}
    chat_email = (chat_user.get("email") or "").strip().lower()
    if chat_email:
        provider = (chat_user.get("provider") or "chat").strip().lower()
        first_name = _normalize_person_name(chat_user.get("first_name") or "")
        last_name = _normalize_person_name(chat_user.get("last_name") or "")
        if not (first_name or last_name):
            first_name, last_name = _split_display_name(chat_user.get("name") or "")
        return chat_email, f"chat-{provider}", first_name, last_name

    return "", "anonymous", "", ""


def _audit_event(request: Request, event_type: str, status: str = "success",
                 target_type: str = "", target_id: str | int = "",
                 message: str = "", metadata: dict | list | str | None = None,
                 actor_email: str = "", actor_type: str = "",
                 actor_first_name: str = "", actor_last_name: str = ""):
    try:
        resolved_email, resolved_type, resolved_first_name, resolved_last_name = _audit_actor(
            request,
            actor_email=actor_email,
            actor_type=actor_type,
            actor_first_name=actor_first_name,
            actor_last_name=actor_last_name,
        )
        add_audit_log(
            event_type=event_type,
            actor_type=resolved_type,
            actor_email=resolved_email,
            actor_first_name=resolved_first_name,
            actor_last_name=resolved_last_name,
            status=status,
            target_type=target_type,
            target_id=str(target_id or ""),
            message=message,
            metadata=metadata,
            ip_address=_client_ip(request),
        )
    except Exception as e:
        print(f"Warning: failed to write audit log ({event_type}): {e}")


def _with_access_metadata(items: list[dict], entity_type: str) -> list[dict]:
    ids = []
    for item in items:
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id > 0:
            ids.append(item_id)
    access_map = get_content_access_map(entity_type, ids)

    output = []
    for item in items:
        row = dict(item)
        try:
            item_id = int(row.get("id"))
        except (TypeError, ValueError):
            item_id = 0
        emails = access_map.get(item_id, [])
        row["access_emails"] = emails
        row["is_restricted"] = bool(emails)
        output.append(row)
    return output


def _external_base_url(request: Request) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto", "") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host", "") or "").split(",")[0].strip()
    proto = forwarded_proto or request.url.scheme
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")




def _cleanup_expired_auth_entries():
    now = int(time.time())
    expired_states = [state for state, entry in oauth_states.items() if entry.get("expires_at", 0) <= now]
    for state in expired_states:
        oauth_states.pop(state, None)

    expired_sessions = [token for token, entry in chat_sessions.items() if entry.get("expires_at", 0) <= now]
    for token in expired_sessions:
        chat_sessions.pop(token, None)


def _normalize_next_path(next_path: str) -> str:
    candidate = (next_path or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    if candidate.startswith("/api/"):
        return "/"
    return candidate


def _append_query_params(url: str, params: dict[str, str]) -> str:
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query.update({k: v for k, v in params.items() if v is not None})
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _oauth_redirect_uri(provider: str, request: Request) -> str:
    env_key = "GOOGLE_REDIRECT_URI" if provider == "google" else "MICROSOFT_REDIRECT_URI"
    configured = (os.getenv(env_key, "") or "").strip()
    if configured:
        return configured
    base = _external_base_url(request)
    return f"{base}/api/auth/{provider}/callback"


def _get_oauth_provider_config(provider: str, request: Request) -> dict:
    if provider == "google":
        client_id = (os.getenv("GOOGLE_CLIENT_ID", "") or "").strip()
        client_secret = (os.getenv("GOOGLE_CLIENT_SECRET", "") or "").strip()
        return {
            "enabled": bool(client_id and client_secret),
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _oauth_redirect_uri("google", request),
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": ["openid", "email", "profile"],
        }

    if provider == "microsoft":
        client_id = (os.getenv("MICROSOFT_CLIENT_ID", "") or os.getenv("OAUTH_CLIENT_ID", "")).strip()
        client_secret = (os.getenv("MICROSOFT_CLIENT_SECRET", "") or os.getenv("OAUTH_CLIENT_SECRET", "")).strip()
        tenant_id = (os.getenv("MICROSOFT_TENANT_ID", "") or os.getenv("OAUTH_TENANT_ID", "") or "common").strip()
        return {
            "enabled": bool(client_id and client_secret),
            "client_id": client_id,
            "client_secret": client_secret,
            "tenant_id": tenant_id,
            "redirect_uri": _oauth_redirect_uri("microsoft", request),
            "authorize_url": f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
            "token_url": f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scopes": ["openid", "profile", "email", "User.Read"],
        }

    raise HTTPException(status_code=404, detail="Unsupported provider")


def _http_post_form_json(url: str, data: dict) -> dict:
    payload = urlencode(data).encode("utf-8")
    request = UrlRequest(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=400, detail=f"OAuth token request failed: {body or exc.reason}")
    except URLError as exc:
        raise HTTPException(status_code=400, detail=f"OAuth token request failed: {exc.reason}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="OAuth token response was not valid JSON.")


def _http_get_json(url: str, headers: dict[str, str]) -> dict:
    request = UrlRequest(url, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=400, detail=f"OAuth profile request failed: {body or exc.reason}")
    except URLError as exc:
        raise HTTPException(status_code=400, detail=f"OAuth profile request failed: {exc.reason}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="OAuth profile response was not valid JSON.")


def _fetch_oauth_user_profile(provider: str, access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    if provider == "google":
        payload = _http_get_json("https://openidconnect.googleapis.com/v1/userinfo", headers=headers)
        first_name = _normalize_person_name(payload.get("given_name") or "")
        last_name = _normalize_person_name(payload.get("family_name") or "")
        if not (first_name or last_name):
            first_name, last_name = _split_display_name(payload.get("name") or "")
        full_name = _normalize_person_name(payload.get("name") or "")
        if not full_name and (first_name or last_name):
            full_name = f"{first_name} {last_name}".strip()
        return {
            "provider": "google",
            "id": (payload.get("sub") or "").strip(),
            "email": (payload.get("email") or "").strip(),
            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "picture": (payload.get("picture") or "").strip(),
        }

    payload = _http_get_json(
        "https://graph.microsoft.com/v1.0/me?$select=id,displayName,givenName,surname,userPrincipalName,mail",
        headers=headers,
    )
    email = (payload.get("mail") or payload.get("userPrincipalName") or "").strip()
    first_name = _normalize_person_name(payload.get("givenName") or "")
    last_name = _normalize_person_name(payload.get("surname") or "")
    full_name = _normalize_person_name(payload.get("displayName") or "")
    if not (first_name or last_name):
        first_name, last_name = _split_display_name(full_name or email)
    if not full_name and (first_name or last_name):
        full_name = f"{first_name} {last_name}".strip()
    return {
        "provider": "microsoft",
        "id": (payload.get("id") or "").strip(),
        "email": email,
        "name": (full_name or email or "").strip(),
        "first_name": first_name,
        "last_name": last_name,
        "picture": "",
    }


def _resolve_chat_user_from_request(request: Request) -> dict | None:
    _cleanup_expired_auth_entries()
    token = (request.cookies.get(CHAT_AUTH_COOKIE, "") or "").strip()
    if not token:
        return None
    session = chat_sessions.get(token)
    if not session:
        return None
    if session.get("expires_at", 0) <= int(time.time()):
        chat_sessions.pop(token, None)
        return None
    return {
        "provider": session.get("provider", ""),
        "email": session.get("email", ""),
        "name": session.get("name", ""),
        "first_name": session.get("first_name", ""),
        "last_name": session.get("last_name", ""),
        "picture": session.get("picture", ""),
    }


# --- Chat Auth Routes ---

@app.get("/api/auth/providers")
async def get_auth_providers(request: Request):
    google = _get_oauth_provider_config("google", request)
    microsoft = _get_oauth_provider_config("microsoft", request)
    return {
        "google": {"enabled": bool(google.get("enabled"))},
        "microsoft": {"enabled": bool(microsoft.get("enabled"))},
    }


@app.get("/api/auth/{provider}/start")
async def start_oauth_login(provider: str, request: Request, next: str = "/"):
    config = _get_oauth_provider_config(provider, request)
    if not config.get("enabled"):
        _audit_event(
            request,
            event_type="auth.oauth_start",
            status="error",
            target_type="oauth-provider",
            target_id=provider,
            message=f"{provider} sign-in is not configured",
        )
        raise HTTPException(status_code=400, detail=f"{provider.capitalize()} sign-in is not configured.")

    _cleanup_expired_auth_entries()
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {
        "provider": provider,
        "next_path": _normalize_next_path(next),
        "expires_at": int(time.time()) + OAUTH_STATE_TTL_SECONDS,
    }

    authorize_url = _append_query_params(
        config["authorize_url"],
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
            "prompt": "select_account",
        },
    )
    _audit_event(
        request,
        event_type="auth.oauth_start",
        status="success",
        target_type="oauth-provider",
        target_id=provider,
        metadata={"next": _normalize_next_path(next)},
    )
    return RedirectResponse(authorize_url)


@app.get("/api/auth/{provider}/callback")
async def oauth_callback(provider: str, request: Request,
                         state: str = "", code: str = "",
                         error: str = "", error_description: str = ""):
    _cleanup_expired_auth_entries()
    state_data = oauth_states.pop((state or "").strip(), None)
    fallback_redirect = "/"
    if state_data:
        fallback_redirect = state_data.get("next_path", "/")

    if not state_data or state_data.get("provider") != provider:
        _audit_event(
            request,
            event_type="auth.oauth_callback",
            status="error",
            target_type="oauth-provider",
            target_id=provider,
            message="Invalid OAuth state",
        )
        error_url = _append_query_params(fallback_redirect, {"auth_error": "invalid_state"})
        return RedirectResponse(error_url, status_code=302)

    if error:
        code_desc = (error_description or error or "oauth_failed").strip()
        _audit_event(
            request,
            event_type="auth.oauth_callback",
            status="error",
            target_type="oauth-provider",
            target_id=provider,
            message=code_desc[:180],
        )
        error_url = _append_query_params(fallback_redirect, {"auth_error": code_desc[:180]})
        return RedirectResponse(error_url, status_code=302)

    if not code:
        _audit_event(
            request,
            event_type="auth.oauth_callback",
            status="error",
            target_type="oauth-provider",
            target_id=provider,
            message="Missing OAuth code",
        )
        error_url = _append_query_params(fallback_redirect, {"auth_error": "missing_code"})
        return RedirectResponse(error_url, status_code=302)

    config = _get_oauth_provider_config(provider, request)
    if not config.get("enabled"):
        _audit_event(
            request,
            event_type="auth.oauth_callback",
            status="error",
            target_type="oauth-provider",
            target_id=provider,
            message="Provider not configured",
        )
        error_url = _append_query_params(fallback_redirect, {"auth_error": "provider_not_configured"})
        return RedirectResponse(error_url, status_code=302)

    try:
        token_payload = _http_post_form_json(
            config["token_url"],
            {
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config["redirect_uri"],
            },
        )
        access_token = (token_payload.get("access_token") or "").strip()
        if not access_token:
            error_url = _append_query_params(fallback_redirect, {"auth_error": "missing_access_token"})
            return RedirectResponse(error_url, status_code=302)
        user = _fetch_oauth_user_profile(provider, access_token)
    except HTTPException as exc:
        message = str(exc.detail or "oauth_failed").strip().replace("\n", " ")
        _audit_event(
            request,
            event_type="auth.oauth_callback",
            status="error",
            target_type="oauth-provider",
            target_id=provider,
            message=message[:180],
        )
        error_url = _append_query_params(fallback_redirect, {"auth_error": message[:180]})
        return RedirectResponse(error_url, status_code=302)
    session_token = secrets.token_urlsafe(48)
    chat_sessions[session_token] = {
        **user,
        "expires_at": int(time.time()) + CHAT_SESSION_TTL_SECONDS,
    }
    _audit_event(
        request,
        event_type="auth.oauth_callback",
        status="success",
        target_type="oauth-provider",
        target_id=provider,
        actor_email=(user.get("email") or "").strip().lower(),
        actor_type=f"chat-{provider}",
        actor_first_name=(user.get("first_name") or "").strip(),
        actor_last_name=(user.get("last_name") or "").strip(),
    )

    success_url = _append_query_params(fallback_redirect, {"auth": "success"})
    response = RedirectResponse(success_url, status_code=302)
    response.set_cookie(
        CHAT_AUTH_COOKIE,
        session_token,
        max_age=CHAT_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https"),
        path="/",
    )
    return response


@app.get("/api/auth/session")
async def get_chat_auth_session(request: Request):
    user = _resolve_chat_user_from_request(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": user}


@app.post("/api/auth/logout")
async def chat_auth_logout(request: Request):
    actor_email = _chat_user_email(request)
    token = (request.cookies.get(CHAT_AUTH_COOKIE, "") or "").strip()
    if token:
        chat_sessions.pop(token, None)
    _audit_event(
        request,
        event_type="auth.chat_logout",
        status="success",
        actor_email=actor_email,
        actor_type="chat-user" if actor_email else "anonymous",
    )
    out = JSONResponse({"status": "logged_out"})
    out.delete_cookie(CHAT_AUTH_COOKIE, path="/")
    return out


# --- Chat Routes ---

@app.post("/api/chat")
async def chat(request: ChatRequest, raw_request: Request):
    user_email = _chat_user_email(raw_request)
    _audit_event(
        raw_request,
        event_type="chat.question",
        status="success",
        actor_email=user_email,
        actor_type="chat-user" if user_email else "anonymous",
        metadata={"question_chars": len((request.question or "").strip())},
    )
    return StreamingResponse(
        chat_stream(request.question, user_email=user_email),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# --- Admin Config Routes ---

@app.post("/api/admin/auth/login")
async def admin_login(body: AdminLoginRequest, request: Request):
    if not verify_admin_password(body.password):
        _audit_event(
            request,
            event_type="admin.auth_login",
            status="error",
            actor_type="anonymous",
            message="Invalid admin password",
        )
        raise HTTPException(status_code=401, detail="Invalid password")
    session = create_admin_session()
    _audit_event(
        request,
        event_type="admin.auth_login",
        status="success",
        actor_type="admin-session",
    )
    return session


@app.get("/api/admin/auth/session")
async def admin_session_check(request: Request, _=Depends(verify_admin)):
    method = getattr(request.state, "admin_auth_method", "unknown")
    payload = {"authenticated": True, "method": method}
    if method == "oauth":
        payload["user"] = getattr(request.state, "admin_oauth_user", None)
    return payload


@app.post("/api/admin/auth/logout")
async def admin_logout(request: Request, _=Depends(verify_admin)):
    session_token = request.headers.get("X-Admin-Session", "").strip()
    if session_token:
        delete_admin_session(session_token)
    _audit_event(
        request,
        event_type="admin.auth_logout",
        status="success",
        actor_type="admin-session" if session_token else "",
    )
    return {"status": "logged_out"}


@app.get("/api/admin/auth/oauth-access")
async def get_admin_oauth_access(request: Request, _=Depends(verify_admin)):
    return {"emails": list_admin_oauth_access_emails()}


@app.post("/api/admin/auth/oauth-access")
async def add_admin_oauth_access(body: AdminOAuthEmailRequest, request: Request,
                                 _=Depends(verify_admin)):
    email = _normalize_admin_email(body.email)
    try:
        row = add_admin_oauth_access_email(email)
    except ValueError as exc:
        _audit_event(
            request,
            event_type="admin.oauth_access_add",
            status="error",
            target_type="admin-oauth-email",
            target_id=email,
            message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_event(
        request,
        event_type="admin.oauth_access_add",
        status="success",
        target_type="admin-oauth-email",
        target_id=email,
    )
    return row


@app.delete("/api/admin/auth/oauth-access")
async def remove_admin_oauth_access(email: str, request: Request,
                                    _=Depends(verify_admin)):
    normalized = _normalize_admin_email(email)
    removed = delete_admin_oauth_access_email(normalized)
    if not removed:
        _audit_event(
            request,
            event_type="admin.oauth_access_remove",
            status="error",
            target_type="admin-oauth-email",
            target_id=normalized,
            message="Email not found in admin access list",
        )
        raise HTTPException(status_code=404, detail="Email not found in admin access list.")
    _audit_event(
        request,
        event_type="admin.oauth_access_remove",
        status="success",
        target_type="admin-oauth-email",
        target_id=normalized,
    )
    return {"status": "deleted", "email": normalized}


@app.put("/api/admin/auth/password")
async def admin_change_password(body: AdminPasswordChangeRequest, request: Request,
                                _=Depends(verify_admin)):
    method = getattr(request.state, "admin_auth_method", "")
    if method != "session":
        _audit_event(
            request,
            event_type="admin.password_change",
            status="error",
            message="Password change denied for non-session auth",
        )
        raise HTTPException(
            status_code=403,
            detail="Only main admin password session can change admin password."
        )

    if not verify_admin_password(body.current_password):
        _audit_event(
            request,
            event_type="admin.password_change",
            status="error",
            message="Current password incorrect",
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len((body.new_password or "").strip()) < 8:
        _audit_event(
            request,
            event_type="admin.password_change",
            status="error",
            message="New password too short",
        )
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    change_admin_password(body.new_password.strip())
    delete_all_admin_sessions()
    session = create_admin_session()
    _audit_event(
        request,
        event_type="admin.password_change",
        status="success",
    )
    return session


@app.get("/api/admin/config")
async def get_config(request: Request, _=Depends(verify_admin)):
    config = get_llm_config()
    # Mask API key for display
    if config.get("api_key"):
        key = config["api_key"]
        if len(key) > 8:
            config["api_key_masked"] = key[:4] + "****" + key[-4:]
        else:
            config["api_key_masked"] = "****"
    else:
        config["api_key_masked"] = ""
    return config


@app.put("/api/admin/config")
async def put_config(config: LLMConfigUpdate, request: Request,
                     _=Depends(verify_admin)):
    previous = get_llm_config()
    updated = update_llm_config(
        provider_type=config.provider_type,
        provider_url=config.provider_url,
        api_key=config.api_key,
        model_name=config.model_name,
        api_version=config.api_version,
        include_video_transcripts_in_rag=config.include_video_transcripts_in_rag,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    was_enabled = bool(previous.get("include_video_transcripts_in_rag"))
    now_enabled = bool(updated.get("include_video_transcripts_in_rag"))
    if not was_enabled and now_enabled:
        auto_index_video_transcripts()
    _audit_event(
        request,
        event_type="admin.llm_config_update",
        status="success",
        target_type="llm-config",
        target_id="1",
        metadata={
            "provider_type": config.provider_type,
            "provider_url": config.provider_url,
            "model_name": config.model_name,
            "include_video_transcripts_in_rag": bool(config.include_video_transcripts_in_rag),
        },
    )
    return updated


@app.post("/api/admin/test-connection")
async def admin_test_connection(request: Request, _=Depends(verify_admin)):
    result = await test_llm_connection()
    _audit_event(
        request,
        event_type="admin.llm_test_connection",
        status="success" if result.get("success") else "error",
        target_type="llm-config",
        target_id="1",
        message=result.get("error", ""),
        metadata={"model": result.get("model", "")},
    )
    return result


@app.get("/api/admin/audit-logs")
async def get_admin_audit_logs(request: Request, limit: int = 200, offset: int = 0,
                               event_type: str = "", actor_email: str = "", status: str = "",
                               _=Depends(verify_admin)):
    items = list_audit_logs(
        limit=limit,
        offset=offset,
        event_type=event_type,
        actor_email=actor_email,
        status=status,
    )
    return {
        "items": items,
        "limit": min(max(int(limit or 200), 1), 1000),
        "offset": max(int(offset or 0), 0),
    }


@app.get("/api/admin/users/activity")
async def get_admin_users_activity(request: Request, limit: int = 300, q: str = "",
                                   _=Depends(verify_admin)):
    items = list_user_activity(limit=limit, email_query=q)
    return {
        "items": items,
        "limit": min(max(int(limit or 300), 1), 2000),
        "query": (q or "").strip().lower(),
    }


# --- Admin Document Routes ---

@app.get("/api/admin/documents")
async def get_documents(request: Request, _=Depends(verify_admin)):
    return _with_access_metadata(list_documents(), "document")


@app.post("/api/admin/documents/upload")
async def upload_documents(request: Request, files: list[UploadFile] = File(...),
                           _=Depends(verify_admin)):
    results = []
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": "Only PDF files are supported"
            })
            continue

        filepath = os.path.join(DOCUMENTS_DIR, file.filename)

        # Save file
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        # Index it
        try:
            chunks = index_pdf(filepath, file.filename)
            results.append({
                "filename": file.filename,
                "status": "indexed",
                "chunks": chunks
            })
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": str(e)
            })

    _audit_event(
        request,
        event_type="admin.documents_upload",
        status="success",
        target_type="document",
        metadata={
            "files_total": len(results),
            "uploaded": len([r for r in results if r.get("status") == "indexed"]),
            "failed": len([r for r in results if r.get("status") == "error"]),
        },
    )
    return results


@app.delete("/api/admin/documents/{doc_id}")
async def delete_doc(doc_id: int, request: Request, _=Depends(verify_admin)):
    doc = get_document(doc_id)
    if not doc:
        _audit_event(
            request,
            event_type="admin.document_delete",
            status="error",
            target_type="document",
            target_id=doc_id,
            message="Document not found",
        )
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove embeddings
    remove_document_embeddings(doc_id, doc["filename"])

    # Remove file from disk
    filepath = os.path.join(DOCUMENTS_DIR, doc["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    # Remove from DB
    delete_document(doc_id)
    _audit_event(
        request,
        event_type="admin.document_delete",
        status="success",
        target_type="document",
        target_id=doc_id,
        metadata={"filename": doc["filename"]},
    )
    return {"status": "deleted", "filename": doc["filename"]}


@app.post("/api/admin/documents/reindex")
async def reindex(request: Request, _=Depends(verify_admin)):
    results = reindex_all_documents()
    _audit_event(
        request,
        event_type="admin.documents_reindex",
        status="success",
        target_type="document",
        metadata={"count": len(results)},
    )
    return {"status": "completed", "documents": results}


@app.put("/api/admin/documents/{doc_id}/link")
async def update_doc_link(doc_id: int, body: DocumentLinkUpdate,
                          request: Request, _=Depends(verify_admin)):
    doc = get_document(doc_id)
    if not doc:
        _audit_event(
            request,
            event_type="admin.document_update_link",
            status="error",
            target_type="document",
            target_id=doc_id,
            message="Document not found",
        )
        raise HTTPException(status_code=404, detail="Document not found")
    updated = update_document_link(doc_id, body.link)
    _audit_event(
        request,
        event_type="admin.document_update_link",
        status="success",
        target_type="document",
        target_id=doc_id,
        metadata={"link": body.link},
    )
    return updated


@app.put("/api/admin/documents/{doc_id}/access")
async def update_doc_access(doc_id: int, body: ContentAccessUpdate,
                            request: Request, _=Depends(verify_admin)):
    doc = get_document(doc_id)
    if not doc:
        _audit_event(
            request,
            event_type="admin.document_update_access",
            status="error",
            target_type="document",
            target_id=doc_id,
            message="Document not found",
        )
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        emails = set_content_access_emails("document", doc_id, body.emails)
    except ValueError as exc:
        _audit_event(
            request,
            event_type="admin.document_update_access",
            status="error",
            target_type="document",
            target_id=doc_id,
            message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_event(
        request,
        event_type="admin.document_update_access",
        status="success",
        target_type="document",
        target_id=doc_id,
        metadata={"emails": emails},
    )
    return {
        "entity_type": "document",
        "entity_id": doc_id,
        "access_emails": emails,
        "is_restricted": bool(emails),
    }


# --- Admin Video Links Routes ---

@app.get("/api/admin/video-links")
async def get_video_links(request: Request, _=Depends(verify_admin)):
    return _with_access_metadata(list_video_links(), "video")


@app.post("/api/admin/video-links")
async def create_video_link(link: VideoLinkCreate, request: Request,
                            _=Depends(verify_admin)):
    entry = add_video_link(title=link.title, url=link.url,
                           description=link.description,
                           transcript=_normalize_transcript_text(link.transcript))
    _sync_video_transcript_index(entry)
    _audit_event(
        request,
        event_type="admin.video_add",
        status="success",
        target_type="video",
        target_id=entry.get("id", ""),
        metadata={"title": entry.get("title", ""), "url": entry.get("url", "")},
    )
    return entry


@app.post("/api/admin/video-links/upload")
async def upload_video(request: Request, file: UploadFile = File(...),
                       transcript_file: UploadFile | None = File(None),
                       transcript_text: str = Form(""),
                       _=Depends(verify_admin)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported format. Allowed: {', '.join(VIDEO_EXTENSIONS)}")
    if transcript_file and transcript_text.strip():
        raise HTTPException(status_code=400,
                            detail="Provide either transcript file or transcript text, not both.")

    os.makedirs(VIDEOS_DIR, exist_ok=True)
    filepath = os.path.join(VIDEOS_DIR, file.filename)
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    transcript = _normalize_transcript_text(transcript_text)
    if transcript_file:
        transcript = await _read_transcript_upload(transcript_file)

    # Auto-create a video link entry pointing to the served file
    title = os.path.splitext(file.filename)[0].replace("-", " ").replace("_", " ")
    video_url = f"/api/videos/{file.filename}"
    entry = add_video_link(title=title, url=video_url, description="Uploaded video",
                           transcript=transcript)
    _sync_video_transcript_index(entry)
    _audit_event(
        request,
        event_type="admin.video_upload",
        status="success",
        target_type="video",
        target_id=entry.get("id", ""),
        metadata={"title": entry.get("title", ""), "url": entry.get("url", "")},
    )
    return entry


@app.delete("/api/admin/video-links/{link_id}")
async def remove_video_link(link_id: int, request: Request,
                            _=Depends(verify_admin)):
    # Check if it's an uploaded video and clean up the file
    links = list_video_links()
    link = next((l for l in links if l["id"] == link_id), None)
    if link and link["url"].startswith("/api/videos/"):
        filename = link["url"].split("/api/videos/", 1)[1]
        filepath = os.path.join(VIDEOS_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    if link:
        remove_video_transcript_embeddings(link_id)

    if not delete_video_link(link_id):
        _audit_event(
            request,
            event_type="admin.video_delete",
            status="error",
            target_type="video",
            target_id=link_id,
            message="Video link not found",
        )
        raise HTTPException(status_code=404, detail="Video link not found")
    _audit_event(
        request,
        event_type="admin.video_delete",
        status="success",
        target_type="video",
        target_id=link_id,
        metadata={"title": (link or {}).get("title", "")},
    )
    return {"status": "deleted"}


@app.put("/api/admin/video-links/{link_id}/transcript")
async def update_video_transcript(link_id: int, request: Request,
                                  transcript_file: UploadFile | None = File(None),
                                  transcript_text: str = Form(""),
                                  _=Depends(verify_admin)):
    if transcript_file and transcript_text.strip():
        raise HTTPException(status_code=400,
                            detail="Provide either transcript file or transcript text, not both.")

    transcript = _normalize_transcript_text(transcript_text)
    if transcript_file:
        transcript = await _read_transcript_upload(transcript_file)

    updated = update_video_link_transcript(link_id, transcript)
    if not updated:
        _audit_event(
            request,
            event_type="admin.video_update_transcript",
            status="error",
            target_type="video",
            target_id=link_id,
            message="Video link not found",
        )
        raise HTTPException(status_code=404, detail="Video link not found")
    _sync_video_transcript_index(updated)
    _audit_event(
        request,
        event_type="admin.video_update_transcript",
        status="success",
        target_type="video",
        target_id=link_id,
        metadata={"transcript_chars": len((transcript or "").strip())},
    )
    return updated


@app.post("/api/admin/video-links/{link_id}/generate-description")
async def generate_video_description(link_id: int, request: Request,
                                     _=Depends(verify_admin)):
    link = next((v for v in list_video_links() if v["id"] == link_id), None)
    if not link:
        _audit_event(
            request,
            event_type="admin.video_generate_description",
            status="error",
            target_type="video",
            target_id=link_id,
            message="Video link not found",
        )
        raise HTTPException(status_code=404, detail="Video link not found")

    transcript = (link.get("transcript") or "").strip()
    if not transcript:
        _audit_event(
            request,
            event_type="admin.video_generate_description",
            status="error",
            target_type="video",
            target_id=link_id,
            message="Transcript is empty",
        )
        raise HTTPException(status_code=400, detail="Transcript is empty. Save transcript first.")

    try:
        description = generate_description_from_transcript(
            transcript=transcript,
            content_type="video",
            title=link.get("title", ""),
        )
    except ValueError as e:
        _audit_event(
            request,
            event_type="admin.video_generate_description",
            status="error",
            target_type="video",
            target_id=link_id,
            message=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _audit_event(
            request,
            event_type="admin.video_generate_description",
            status="error",
            target_type="video",
            target_id=link_id,
            message=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Description generation failed: {str(e)}")

    updated = update_video_link_description(link_id, description)
    if not updated:
        _audit_event(
            request,
            event_type="admin.video_generate_description",
            status="error",
            target_type="video",
            target_id=link_id,
            message="Video link not found after generation",
        )
        raise HTTPException(status_code=404, detail="Video link not found")
    _audit_event(
        request,
        event_type="admin.video_generate_description",
        status="success",
        target_type="video",
        target_id=link_id,
    )
    return updated


@app.put("/api/admin/video-links/{link_id}/access")
async def update_video_access(link_id: int, body: ContentAccessUpdate,
                              request: Request, _=Depends(verify_admin)):
    link = next((v for v in list_video_links() if v["id"] == link_id), None)
    if not link:
        _audit_event(
            request,
            event_type="admin.video_update_access",
            status="error",
            target_type="video",
            target_id=link_id,
            message="Video link not found",
        )
        raise HTTPException(status_code=404, detail="Video link not found")
    try:
        emails = set_content_access_emails("video", link_id, body.emails)
    except ValueError as exc:
        _audit_event(
            request,
            event_type="admin.video_update_access",
            status="error",
            target_type="video",
            target_id=link_id,
            message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_event(
        request,
        event_type="admin.video_update_access",
        status="success",
        target_type="video",
        target_id=link_id,
        metadata={"emails": emails},
    )
    return {
        "entity_type": "video",
        "entity_id": link_id,
        "access_emails": emails,
        "is_restricted": bool(emails),
    }


# --- Serve Uploaded Videos (public, no auth) ---

@app.get("/api/videos/{filename}")
async def serve_video(filename: str, request: Request):
    link = next((v for v in list_video_links() if v.get("url") == f"/api/videos/{filename}"), None)
    if link:
        if not is_entity_visible_to_email("video", int(link["id"]), _chat_user_email(request)):
            _audit_event(
                request,
                event_type="media.video_access",
                status="error",
                target_type="video",
                target_id=link.get("id", ""),
                message="Access denied",
            )
            raise HTTPException(status_code=403, detail="Access denied for this video.")
    filepath = os.path.join(VIDEOS_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(filepath)


# --- Admin Image Routes ---

@app.get("/api/admin/images")
async def get_images(request: Request, _=Depends(verify_admin)):
    return _with_access_metadata(list_images(), "image")


@app.post("/api/admin/images/upload")
async def upload_images(request: Request, files: list[UploadFile] = File(...),
                        _=Depends(verify_admin)):
    import uuid
    results = []
    os.makedirs(IMAGES_DIR, exist_ok=True)

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": f"Unsupported format. Allowed: {', '.join(IMAGE_EXTENSIONS)}"
            })
            continue

        # Use a unique filename to avoid collisions
        unique_name = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(IMAGES_DIR, unique_name)

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        entry = add_image(filename=unique_name, original_name=file.filename)
        entry["url"] = f"/api/images/{unique_name}"
        results.append({**entry, "status": "uploaded"})

    _audit_event(
        request,
        event_type="admin.images_upload",
        status="success",
        target_type="image",
        metadata={
            "files_total": len(results),
            "uploaded": len([r for r in results if r.get("status") == "uploaded"]),
            "failed": len([r for r in results if r.get("status") == "error"]),
        },
    )
    return results


@app.delete("/api/admin/images/{image_id}")
async def remove_image(image_id: int, request: Request, _=Depends(verify_admin)):
    image = delete_image(image_id)
    if not image:
        _audit_event(
            request,
            event_type="admin.image_delete",
            status="error",
            target_type="image",
            target_id=image_id,
            message="Image not found",
        )
        raise HTTPException(status_code=404, detail="Image not found")

    filepath = os.path.join(IMAGES_DIR, image["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)
    _audit_event(
        request,
        event_type="admin.image_delete",
        status="success",
        target_type="image",
        target_id=image_id,
        metadata={"original_name": image.get("original_name", "")},
    )
    return {"status": "deleted", "filename": image["original_name"]}


@app.put("/api/admin/images/{image_id}/description")
async def update_img_description(image_id: int, body: ImageDescriptionUpdate,
                                  request: Request, _=Depends(verify_admin)):
    updated = update_image_description(image_id, body.description)
    if not updated:
        _audit_event(
            request,
            event_type="admin.image_update_description",
            status="error",
            target_type="image",
            target_id=image_id,
            message="Image not found",
        )
        raise HTTPException(status_code=404, detail="Image not found")
    _audit_event(
        request,
        event_type="admin.image_update_description",
        status="success",
        target_type="image",
        target_id=image_id,
    )
    return updated


@app.post("/api/admin/images/{image_id}/generate-description")
async def generate_img_description(image_id: int, request: Request, _=Depends(verify_admin)):
    image = next((img for img in list_images() if img["id"] == image_id), None)
    if not image:
        _audit_event(
            request,
            event_type="admin.image_generate_description",
            status="error",
            target_type="image",
            target_id=image_id,
            message="Image not found",
        )
        raise HTTPException(status_code=404, detail="Image not found")

    image_path = os.path.join(IMAGES_DIR, image["filename"])
    if not os.path.isfile(image_path):
        _audit_event(
            request,
            event_type="admin.image_generate_description",
            status="error",
            target_type="image",
            target_id=image_id,
            message="Image file not found",
        )
        raise HTTPException(status_code=404, detail="Image file not found")

    try:
        description = generate_description_from_image(
            image_path=image_path,
            title=image.get("original_name", "")
        )
    except ValueError as e:
        _audit_event(
            request,
            event_type="admin.image_generate_description",
            status="error",
            target_type="image",
            target_id=image_id,
            message=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _audit_event(
            request,
            event_type="admin.image_generate_description",
            status="error",
            target_type="image",
            target_id=image_id,
            message=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Description generation failed: {str(e)}")

    updated = update_image_description(image_id, description)
    if not updated:
        _audit_event(
            request,
            event_type="admin.image_generate_description",
            status="error",
            target_type="image",
            target_id=image_id,
            message="Image not found after generation",
        )
        raise HTTPException(status_code=404, detail="Image not found")
    _audit_event(
        request,
        event_type="admin.image_generate_description",
        status="success",
        target_type="image",
        target_id=image_id,
    )
    return updated


@app.put("/api/admin/images/{image_id}/access")
async def update_image_access(image_id: int, body: ContentAccessUpdate,
                              request: Request, _=Depends(verify_admin)):
    image = next((img for img in list_images() if img["id"] == image_id), None)
    if not image:
        _audit_event(
            request,
            event_type="admin.image_update_access",
            status="error",
            target_type="image",
            target_id=image_id,
            message="Image not found",
        )
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        emails = set_content_access_emails("image", image_id, body.emails)
    except ValueError as exc:
        _audit_event(
            request,
            event_type="admin.image_update_access",
            status="error",
            target_type="image",
            target_id=image_id,
            message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))
    _audit_event(
        request,
        event_type="admin.image_update_access",
        status="success",
        target_type="image",
        target_id=image_id,
        metadata={"emails": emails},
    )
    return {
        "entity_type": "image",
        "entity_id": image_id,
        "access_emails": emails,
        "is_restricted": bool(emails),
    }


# --- Serve Uploaded Images (public, no auth) ---

@app.get("/api/images/{filename}")
async def serve_image(filename: str, request: Request):
    image = next((img for img in list_images() if img.get("filename") == filename), None)
    if image:
        if not is_entity_visible_to_email("image", int(image["id"]), _chat_user_email(request)):
            _audit_event(
                request,
                event_type="media.image_access",
                status="error",
                target_type="image",
                target_id=image.get("id", ""),
                message="Access denied",
            )
            raise HTTPException(status_code=403, detail="Access denied for this image.")
    filepath = os.path.join(IMAGES_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(filepath)


# --- Serve Frontend Static Files ---

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIR):
    # Mount static assets under /assets (CSS, JS bundles)
    assets_dir = os.path.join(FRONTEND_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
