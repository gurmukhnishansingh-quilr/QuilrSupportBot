import os
import shutil
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from config import (
    init_db, get_llm_config, update_llm_config,
    list_documents, delete_document, get_document, update_document_link,
    list_video_links, add_video_link, delete_video_link, update_video_link_transcript,
    list_images, add_image, update_image_description, delete_image,
    verify_admin_password, create_admin_session, validate_admin_session,
    delete_admin_session, delete_all_admin_sessions, change_admin_password,
)
from embeddings import (
    auto_index_documents, index_pdf, remove_document_embeddings,
    reindex_all_documents, DOCUMENTS_DIR, auto_index_video_transcripts,
    index_video_transcript, remove_video_transcript_embeddings
)
from chat import chat_stream, test_llm_connection

VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "videos")
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov"}
TRANSCRIPT_EXTENSIONS = {".txt", ".srt", ".vtt", ".md"}
MAX_TRANSCRIPT_BYTES = 1_000_000
MAX_TRANSCRIPT_CHARS = 30_000
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "images")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


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
        return

    # Backward-compatible fallback for clients still sending plain password.
    password = request.headers.get("X-Admin-Password", "")
    if password and verify_admin_password(password):
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


class VideoLinkCreate(BaseModel):
    title: str
    url: str
    description: str = ""
    transcript: str = ""


class DocumentLinkUpdate(BaseModel):
    link: str = ""


class ImageDescriptionUpdate(BaseModel):
    description: str = ""


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


# --- Chat Routes ---

@app.post("/api/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        chat_stream(request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# --- Admin Config Routes ---

@app.post("/api/admin/auth/login")
async def admin_login(body: AdminLoginRequest):
    if not verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    return create_admin_session()


@app.get("/api/admin/auth/session")
async def admin_session_check(request: Request, _=Depends(verify_admin)):
    return {"authenticated": True}


@app.post("/api/admin/auth/logout")
async def admin_logout(request: Request, _=Depends(verify_admin)):
    session_token = request.headers.get("X-Admin-Session", "").strip()
    if session_token:
        delete_admin_session(session_token)
    return {"status": "logged_out"}


@app.put("/api/admin/auth/password")
async def admin_change_password(body: AdminPasswordChangeRequest, request: Request,
                                _=Depends(verify_admin)):
    if not verify_admin_password(body.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len((body.new_password or "").strip()) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    change_admin_password(body.new_password.strip())
    delete_all_admin_sessions()
    return create_admin_session()


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
    return updated


@app.post("/api/admin/test-connection")
async def admin_test_connection(request: Request, _=Depends(verify_admin)):
    result = await test_llm_connection()
    return result


# --- Admin Document Routes ---

@app.get("/api/admin/documents")
async def get_documents(request: Request, _=Depends(verify_admin)):
    return list_documents()


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

    return results


@app.delete("/api/admin/documents/{doc_id}")
async def delete_doc(doc_id: int, request: Request, _=Depends(verify_admin)):
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove embeddings
    remove_document_embeddings(doc_id, doc["filename"])

    # Remove file from disk
    filepath = os.path.join(DOCUMENTS_DIR, doc["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    # Remove from DB
    delete_document(doc_id)

    return {"status": "deleted", "filename": doc["filename"]}


@app.post("/api/admin/documents/reindex")
async def reindex(request: Request, _=Depends(verify_admin)):
    results = reindex_all_documents()
    return {"status": "completed", "documents": results}


@app.put("/api/admin/documents/{doc_id}/link")
async def update_doc_link(doc_id: int, body: DocumentLinkUpdate,
                          request: Request, _=Depends(verify_admin)):
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    updated = update_document_link(doc_id, body.link)
    return updated


# --- Admin Video Links Routes ---

@app.get("/api/admin/video-links")
async def get_video_links(request: Request, _=Depends(verify_admin)):
    return list_video_links()


@app.post("/api/admin/video-links")
async def create_video_link(link: VideoLinkCreate, request: Request,
                            _=Depends(verify_admin)):
    entry = add_video_link(title=link.title, url=link.url,
                           description=link.description,
                           transcript=_normalize_transcript_text(link.transcript))
    _sync_video_transcript_index(entry)
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
        raise HTTPException(status_code=404, detail="Video link not found")
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
        raise HTTPException(status_code=404, detail="Video link not found")
    _sync_video_transcript_index(updated)
    return updated


# --- Serve Uploaded Videos (public, no auth) ---

@app.get("/api/videos/{filename}")
async def serve_video(filename: str):
    filepath = os.path.join(VIDEOS_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(filepath)


# --- Admin Image Routes ---

@app.get("/api/admin/images")
async def get_images(request: Request, _=Depends(verify_admin)):
    return list_images()


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

    return results


@app.delete("/api/admin/images/{image_id}")
async def remove_image(image_id: int, request: Request, _=Depends(verify_admin)):
    image = delete_image(image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    filepath = os.path.join(IMAGES_DIR, image["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    return {"status": "deleted", "filename": image["original_name"]}


@app.put("/api/admin/images/{image_id}/description")
async def update_img_description(image_id: int, body: ImageDescriptionUpdate,
                                  request: Request, _=Depends(verify_admin)):
    updated = update_image_description(image_id, body.description)
    if not updated:
        raise HTTPException(status_code=404, detail="Image not found")
    return updated


# --- Serve Uploaded Images (public, no auth) ---

@app.get("/api/images/{filename}")
async def serve_image(filename: str):
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
