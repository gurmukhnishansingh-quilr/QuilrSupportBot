from __future__ import annotations

import os
import fitz  # PyMuPDF
import chromadb
from sentence_transformers import SentenceTransformer
from config import (
    add_document, get_document_by_filename, update_document_status,
    list_documents, get_document, list_video_links
)

DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "documents")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "data", "chroma")

# Globals initialized on first use
_model: SentenceTransformer | None = None
_chroma_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "quilly_docs"
CHUNK_SIZE = 500  # approximate tokens
CHUNK_OVERLAP = 50


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def get_collection() -> chromadb.Collection:
    global _chroma_client, _collection
    if _collection is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks by approximate word count (as token proxy)."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks


def index_pdf(pdf_path: str, filename: str | None = None) -> int:
    """Process a single PDF: extract text, chunk, embed, store in ChromaDB.
    Returns the number of chunks created."""
    if filename is None:
        filename = os.path.basename(pdf_path)

    # Record in DB
    doc_record = add_document(filename, chunk_count=0, status="processing")
    doc_id = doc_record["id"]

    try:
        text = extract_text_from_pdf(pdf_path)
        chunks = chunk_text(text)

        if not chunks:
            update_document_status(doc_id, "indexed", 0)
            return 0

        model = get_model()
        embeddings = model.encode(chunks).tolist()

        collection = get_collection()

        # Create IDs and metadata for each chunk
        ids = [f"{filename}__chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"filename": filename, "chunk_index": i, "doc_id": doc_id}
            for i in range(len(chunks))
        ]

        # Upsert in batches of 100
        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            end = start + batch_size
            collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=chunks[start:end],
                metadatas=metadatas[start:end]
            )

        update_document_status(doc_id, "indexed", len(chunks))
        return len(chunks)

    except Exception as e:
        update_document_status(doc_id, f"error: {str(e)[:200]}")
        raise


def remove_document_embeddings(doc_id: int, filename: str):
    """Remove all embeddings for a document from ChromaDB."""
    collection = get_collection()
    # Get all IDs for this document
    results = collection.get(where={"doc_id": doc_id})
    if results["ids"]:
        collection.delete(ids=results["ids"])


def remove_video_transcript_embeddings(video_id: int):
    """Remove all transcript embeddings for a video link from ChromaDB."""
    collection = get_collection()
    results = collection.get(where={"source_type": "video_transcript", "video_id": video_id})
    if results["ids"]:
        collection.delete(ids=results["ids"])


def index_video_transcript(video_link: dict) -> int:
    """Index transcript text for a video link and return chunk count."""
    video_id = int(video_link["id"])
    title = (video_link.get("title") or f"Video {video_id}").strip()
    url = (video_link.get("url") or "").strip()
    transcript = (video_link.get("transcript") or "").strip()

    # Keep index in sync when transcript is cleared/changed.
    remove_video_transcript_embeddings(video_id)

    if not transcript:
        return 0

    chunks = chunk_text(transcript)
    if not chunks:
        return 0

    model = get_model()
    embeddings = model.encode(chunks).tolist()
    collection = get_collection()

    ids = [f"video_{video_id}__transcript_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source_type": "video_transcript",
            "video_id": video_id,
            "video_title": title,
            "video_url": url,
            "filename": f"Video transcript: {title}",
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=chunks[start:end],
            metadatas=metadatas[start:end]
        )
    return len(chunks)


def auto_index_documents():
    """Index any PDFs in the documents directory that haven't been processed."""
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    pdf_files = [f for f in os.listdir(DOCUMENTS_DIR)
                 if f.lower().endswith(".pdf")]

    indexed_count = 0
    for pdf_file in pdf_files:
        existing = get_document_by_filename(pdf_file)
        if existing and existing["status"] == "indexed":
            continue

        pdf_path = os.path.join(DOCUMENTS_DIR, pdf_file)
        try:
            chunks = index_pdf(pdf_path, pdf_file)
            print(f"Indexed {pdf_file}: {chunks} chunks")
            indexed_count += 1
        except Exception as e:
            print(f"Error indexing {pdf_file}: {e}")

    return indexed_count


def auto_index_video_transcripts() -> int:
    """Index transcripts for all videos that have transcript content."""
    indexed = 0
    for video in list_video_links():
        transcript = (video.get("transcript") or "").strip()
        if not transcript:
            continue
        try:
            chunks = index_video_transcript(video)
            print(f"Indexed transcript for video {video['id']}: {chunks} chunks")
            indexed += 1
        except Exception as e:
            print(f"Error indexing transcript for video {video.get('id')}: {e}")
    return indexed


def reindex_all_documents():
    """Re-process all documents from scratch."""
    # Clear existing collection
    global _collection
    client = get_collection()
    if _chroma_client:
        try:
            _chroma_client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _collection = None

    # Re-scan all PDFs
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    pdf_files = [f for f in os.listdir(DOCUMENTS_DIR)
                 if f.lower().endswith(".pdf")]

    results = []
    for pdf_file in pdf_files:
        pdf_path = os.path.join(DOCUMENTS_DIR, pdf_file)
        try:
            chunks = index_pdf(pdf_path, pdf_file)
            results.append({"filename": pdf_file, "chunks": chunks,
                            "status": "indexed"})
        except Exception as e:
            results.append({"filename": pdf_file, "chunks": 0,
                            "status": f"error: {str(e)[:200]}"})

    return results


def search_similar(query: str, n_results: int = 5,
                   include_video_transcripts: bool = False) -> list[dict]:
    """Search for chunks similar to the query."""
    model = get_model()
    query_embedding = model.encode([query]).tolist()

    collection = get_collection()
    if collection.count() == 0:
        return []

    fetch_count = min(max(n_results * 6, 20), collection.count())
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=fetch_count
    )

    chunks = []
    for i in range(len(results["ids"][0])):
        metadata = results["metadatas"][0][i]
        source_type = metadata.get("source_type")
        if source_type == "video_transcript" and not include_video_transcripts:
            continue
        chunks.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": metadata,
            "distance": results["distances"][0][i] if results.get("distances") else None
        })
        if len(chunks) >= n_results:
            break

    return chunks
