import json
from openai import OpenAI, AzureOpenAI
from config import get_llm_config, list_video_links, get_document_links, list_images
from embeddings import search_similar

VIDEO_TRANSCRIPT_SNIPPET_CHARS = 1200
VIDEO_TRANSCRIPT_TOTAL_CHARS = 4000


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


async def chat_stream(question: str):
    """RAG pipeline: retrieve context, call LLM, yield streamed response."""
    config = get_llm_config()

    if not config.get("provider_url") or not config.get("model_name"):
        yield f"data: {json.dumps({'type': 'error', 'content': 'LLM not configured. Please set up the LLM provider in the Admin console.'})}\n\n"
        return

    # Retrieve relevant chunks
    include_video_transcripts = bool(config.get("include_video_transcripts_in_rag"))
    chunks = search_similar(question, n_results=5,
                            include_video_transcripts=include_video_transcripts)
    context, sources = build_context(chunks)

    # Send sources first
    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    # Build video links section
    videos = list_video_links()
    if videos:
        video_lines = ["", "Available demo/tutorial videos:"]
        transcript_budget = VIDEO_TRANSCRIPT_TOTAL_CHARS
        for v in videos:
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
    images = list_images()
    images_with_desc = [img for img in images if img.get("description")]
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
