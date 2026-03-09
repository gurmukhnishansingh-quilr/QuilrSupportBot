import json
import base64
import mimetypes
import os
from openai import OpenAI, AzureOpenAI
from config import (
    get_llm_config, list_video_links, get_document_links, list_images,
    list_documents, filter_items_by_access_email,
)
from embeddings import search_similar

VIDEO_TRANSCRIPT_SNIPPET_CHARS = 1200
VIDEO_TRANSCRIPT_TOTAL_CHARS = 4000
DESCRIPTION_TRANSCRIPT_CHARS = 12000
DESCRIPTION_MAX_CHARS = 220
IMAGE_DESCRIPTION_MAX_BYTES = 8 * 1024 * 1024
VISION_SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
SVG_MIME_TYPES = {"image/svg+xml", "image/svg"}
SVG_MAX_CHARS = 30000


def _get_client(config):
    """Return the appropriate OpenAI client based on provider_type."""
    if config.get("provider_type") == "azure":
        return AzureOpenAI(
            azure_endpoint=config["provider_url"],
            api_key=config.get("api_key") or "no-key",
            api_version=config.get("api_version") or "2024-12-01-preview",
        )
    return OpenAI(
        base_url=config["provider_url"],
        api_key=config.get("api_key") or "no-key",
    )

SYSTEM_PROMPT = """You are Quilly, a helpful support assistant for Quilr AI.
You answer questions about Quilr AI product installation, configuration, tenant setup, and troubleshooting.

Use ONLY the provided context to answer questions. If the context doesn't contain enough information to answer, say so honestly.

When answering:
- Be concise and helpful
- Reference specific steps or sections when relevant
- If a document has an associated link, mention it so the user can read the full document
- If the user asks about demos, tutorials, or video guides, share the relevant video links from the list below
- When an available image/screenshot is relevant to the topic being discussed, ALWAYS include it in your response using markdown image syntax: ![description](url). Do not wait for the user to explicitly ask for images — proactively show them whenever they help illustrate the answer.
- If the user asks something outside the provided documentation, let them know you can only help with Quilr AI topics covered in the documentation

Context from documentation:
{context}
{video_section}
{image_section}"""


def build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    """Build context string from retrieved chunks and return sources."""
    if not chunks:
        return "No relevant documentation found.", []

    doc_links = get_document_links()
    context_parts = []
    sources = []
    seen_filenames = set()

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        source_type = metadata.get("source_type")

        if source_type == "video_transcript":
            title = metadata.get("video_title") or "Video transcript"
            video_url = metadata.get("video_url") or ""
            filename = f"Video transcript: {title}"
            header = f"[From: {filename}]"
            if video_url:
                header += f" (Video: {video_url})"
        else:
            filename = metadata.get("filename") or "Unknown document"
            header = f"[From: {filename}]"
            link = doc_links.get(filename)
            if link:
                header += f" (Full document: {link})"

        context_parts.append(f"{header}\n{chunk['text']}")
        if filename not in seen_filenames:
            seen_filenames.add(filename)
            sources.append({
                "filename": filename,
                "chunk_id": chunk["id"],
                "source_type": source_type or "document",
                "relevance": 1 - (chunk["distance"] or 0)
            })

    return "\n\n---\n\n".join(context_parts), sources


def _build_transcript_snippet(transcript: str) -> str:
    compact = " ".join((transcript or "").split())
    if len(compact) <= VIDEO_TRANSCRIPT_SNIPPET_CHARS:
        return compact
    return compact[:VIDEO_TRANSCRIPT_SNIPPET_CHARS].rstrip() + "..."


def _trim_snippet_to_budget(snippet: str, remaining_chars: int) -> str:
    if remaining_chars <= 0:
        return ""
    if len(snippet) <= remaining_chars:
        return snippet
    if remaining_chars <= 3:
        return snippet[:remaining_chars]
    return snippet[:remaining_chars - 3].rstrip() + "..."


async def chat_stream(question: str, user_email: str = ""):
    """RAG pipeline: retrieve context, call LLM, yield streamed response."""
    config = get_llm_config()

    if not config.get("provider_url") or not config.get("model_name"):
        yield f"data: {json.dumps({'type': 'error', 'content': 'LLM not configured. Please set up the LLM provider in the Admin console.'})}\n\n"
        return

    # Resolve visible content for current user.
    visible_documents = filter_items_by_access_email("document", list_documents(), user_email)
    visible_videos = filter_items_by_access_email("video", list_video_links(), user_email)
    visible_images = filter_items_by_access_email("image", list_images(), user_email)
    allowed_doc_filenames = {doc.get("filename", "") for doc in visible_documents}
    allowed_video_ids = {int(v["id"]) for v in visible_videos if v.get("id") is not None}

    # Retrieve relevant chunks
    include_video_transcripts = bool(config.get("include_video_transcripts_in_rag"))
    chunks = search_similar(question, n_results=5,
                            include_video_transcripts=include_video_transcripts)
    filtered_chunks = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        source_type = metadata.get("source_type")
        if source_type == "video_transcript":
            try:
                video_id = int(metadata.get("video_id") or 0)
            except (TypeError, ValueError):
                continue
            if video_id not in allowed_video_ids:
                continue
            filtered_chunks.append(chunk)
            continue

        filename = (metadata.get("filename") or "").strip()
        if not filename or filename not in allowed_doc_filenames:
            continue
        filtered_chunks.append(chunk)

    context, sources = build_context(filtered_chunks)

    # Send sources first
    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    # Build video links section
    if visible_videos:
        video_lines = ["", "Available demo/tutorial videos:"]
        transcript_budget = VIDEO_TRANSCRIPT_TOTAL_CHARS
        for v in visible_videos:
            line = f"- {v['title']}: {v['url']}"
            if v.get("description"):
                line += f" — {v['description']}"
            video_lines.append(line)
            if v.get("transcript") and transcript_budget > 0:
                snippet = _build_transcript_snippet(v["transcript"])
                snippet = _trim_snippet_to_budget(snippet, transcript_budget)
                if snippet:
                    video_lines.append(f"  Transcript snippet: {snippet}")
                    transcript_budget -= len(snippet)
        video_section = "\n".join(video_lines)
    else:
        video_section = ""

    # Build image section
    images_with_desc = [img for img in visible_images if img.get("description")]
    if images_with_desc:
        image_lines = ["", "Available images/screenshots (use markdown ![alt](url) to display them):"]
        for img in images_with_desc:
            url = f"/api/images/{img['filename']}"
            line = f"- {img['description']} → use: ![{img['description']}]({url})"
            image_lines.append(line)
        image_section = "\n".join(image_lines)
    else:
        image_section = ""

    # Build messages
    system_message = SYSTEM_PROMPT.format(context=context,
                                          video_section=video_section,
                                          image_section=image_section)
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": question}
    ]

    # Call LLM
    try:
        client = _get_client(config)

        stream = client.chat.completions.create(
            model=config["model_name"],
            messages=messages,
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 1024),
            stream=True
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': f'LLM Error: {str(e)}'})}\n\n"


async def test_llm_connection() -> dict:
    """Test if the LLM config works by sending a simple request."""
    config = get_llm_config()

    if not config.get("provider_url") or not config.get("model_name"):
        return {"success": False, "error": "LLM not configured"}

    try:
        client = _get_client(config)

        response = client.chat.completions.create(
            model=config["model_name"],
            messages=[{"role": "user", "content": "Say 'Connection successful' in exactly two words."}],
            max_tokens=20
        )

        return {
            "success": True,
            "response": response.choices[0].message.content,
            "model": config["model_name"]
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _normalize_generated_description(text: str) -> str:
    clean = " ".join((text or "").split()).strip()
    if clean.startswith('"') and clean.endswith('"'):
        clean = clean[1:-1].strip()
    if len(clean) > DESCRIPTION_MAX_CHARS:
        clean = clean[:DESCRIPTION_MAX_CHARS].rstrip()
    return clean


def generate_description_from_transcript(transcript: str, content_type: str,
                                         title: str = "") -> str:
    config = get_llm_config()
    if not config.get("provider_url") or not config.get("model_name"):
        raise ValueError("LLM is not configured. Configure provider URL and model first.")

    transcript_clean = " ".join((transcript or "").split()).strip()
    if not transcript_clean:
        raise ValueError("Transcript text is required to generate a description.")
    if len(transcript_clean) > DESCRIPTION_TRANSCRIPT_CHARS:
        transcript_clean = transcript_clean[:DESCRIPTION_TRANSCRIPT_CHARS].rstrip()

    prompt = (
        f"Content type: {content_type}\n"
        f"Title: {title or 'N/A'}\n\n"
        "Transcript:\n"
        f"{transcript_clean}\n\n"
        f"Generate one concise admin-friendly description (max {DESCRIPTION_MAX_CHARS} characters). "
        "Return only the description text."
    )

    client = _get_client(config)
    response = client.chat.completions.create(
        model=config["model_name"],
        messages=[
            {
                "role": "system",
                "content": "You write concise, factual descriptions for support content.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=120,
    )
    raw = response.choices[0].message.content if response.choices else ""
    description = _normalize_generated_description(raw or "")
    if not description:
        raise ValueError("Description generation returned empty output.")
    return description


def generate_description_from_image(image_path: str, title: str = "") -> str:
    config = get_llm_config()
    if not config.get("provider_url") or not config.get("model_name"):
        raise ValueError("LLM is not configured. Configure provider URL and model first.")
    if not os.path.isfile(image_path):
        raise ValueError("Image file not found.")

    file_size = os.path.getsize(image_path)
    if file_size > IMAGE_DESCRIPTION_MAX_BYTES:
        raise ValueError(f"Image is too large. Maximum supported size is {IMAGE_DESCRIPTION_MAX_BYTES} bytes.")

    mime_type = (mimetypes.guess_type(image_path)[0] or "").lower().strip()
    ext = os.path.splitext(image_path)[1].lower()
    if not mime_type and ext == ".svg":
        mime_type = "image/svg+xml"
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    if mime_type in SVG_MIME_TYPES or ext == ".svg":
        with open(image_path, "r", encoding="utf-8", errors="replace") as f:
            svg_text = f.read()
        compact_svg = " ".join(svg_text.split())
        if len(compact_svg) > SVG_MAX_CHARS:
            compact_svg = compact_svg[:SVG_MAX_CHARS].rstrip() + "..."

        svg_prompt = (
            f"Image title: {title or 'N/A'}\n"
            f"SVG markup snippet:\n{compact_svg}\n\n"
            f"Generate one concise admin-friendly description (max {DESCRIPTION_MAX_CHARS} characters) "
            "for what this SVG likely depicts in a support context. Return only the description text."
        )
        client = _get_client(config)
        response = client.chat.completions.create(
            model=config["model_name"],
            messages=[
                {
                    "role": "system",
                    "content": "You write concise, factual descriptions for support images/screenshots.",
                },
                {"role": "user", "content": svg_prompt},
            ],
            temperature=0.2,
            max_tokens=120,
        )
        raw = response.choices[0].message.content if response.choices else ""
        description = _normalize_generated_description(raw or "")
        if not description:
            raise ValueError("Description generation returned empty output.")
        return description

    if mime_type not in VISION_SUPPORTED_MIME_TYPES:
        raise ValueError(
            f"Unsupported image format for description generation ({ext or 'unknown'}). "
            "Use PNG, JPG/JPEG, WEBP, GIF, or SVG."
        )

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        f"Image title: {title or 'N/A'}\n"
        f"Generate one concise admin-friendly description (max {DESCRIPTION_MAX_CHARS} characters). "
        "Focus on what the screenshot/image shows so a support bot can decide when to share it. "
        "Return only the description text."
    )

    client = _get_client(config)
    try:
        response = client.chat.completions.create(
            model=config["model_name"],
            messages=[
                {
                    "role": "system",
                    "content": "You write concise, factual descriptions for support images/screenshots.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                                "detail": "auto",
                            },
                        },
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=120,
        )
    except Exception as e:
        msg = str(e)
        if "Invalid image data" in msg:
            raise ValueError(
                "Model rejected the image data. Ensure the image is a valid PNG/JPG/WEBP/GIF "
                "and use a vision-capable model (for example: gpt-4o or gpt-4.1)."
            )
        raise
    raw = response.choices[0].message.content if response.choices else ""
    description = _normalize_generated_description(raw or "")
    if not description:
        raise ValueError("Description generation returned empty output.")
    return description
