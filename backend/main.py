import os
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from config import (
    init_db, get_llm_config, update_llm_config,
    list_documents, delete_document, get_document, update_document_link,
    list_video_links, add_video_link, delete_video_link,
)
from embeddings import (
    auto_index_documents, index_pdf, remove_document_embeddings,
    reindex_all_documents, DOCUMENTS_DIR
)
from chat import chat_stream, test_llm_connection

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
VIDEOS_DIR = os.path.join(os.path.dirname(__file__), "..", "videos")
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    print("Database initialized")
    print("Auto-indexing documents...")
    count = auto_index_documents()
    print(f"Auto-indexed {count} new document(s)")
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
    password = request.headers.get("X-Admin-Password", "")
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")


# --- Pydantic Models ---

class LLMConfigUpdate(BaseModel):
    provider_type: str = "openai"
    provider_url: str
    api_key: str
    model_name: str
    api_version: str = ""
    temperature: float = 0.7
    max_tokens: int = 1024


class ChatRequest(BaseModel):
    question: str


class VideoLinkCreate(BaseModel):
    title: str
    url: str
    description: str = ""


class DocumentLinkUpdate(BaseModel):
    link: str = ""


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
    updated = update_llm_config(
        provider_type=config.provider_type,
        provider_url=config.provider_url,
        api_key=config.api_key,
        model_name=config.model_name,
        api_version=config.api_version,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
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
    return add_video_link(title=link.title, url=link.url,
                          description=link.description)


@app.post("/api/admin/video-links/upload")
async def upload_video(request: Request, file: UploadFile = File(...),
                       _=Depends(verify_admin)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported format. Allowed: {', '.join(VIDEO_EXTENSIONS)}")

    os.makedirs(VIDEOS_DIR, exist_ok=True)
    filepath = os.path.join(VIDEOS_DIR, file.filename)
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    # Auto-create a video link entry pointing to the served file
    title = os.path.splitext(file.filename)[0].replace("-", " ").replace("_", " ")
    video_url = f"/api/videos/{file.filename}"
    entry = add_video_link(title=title, url=video_url, description="Uploaded video")
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

    if not delete_video_link(link_id):
        raise HTTPException(status_code=404, detail="Video link not found")
    return {"status": "deleted"}


# --- Serve Uploaded Videos (public, no auth) ---

@app.get("/api/videos/{filename}")
async def serve_video(filename: str):
    filepath = os.path.join(VIDEOS_DIR, filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Video not found")
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
