import hashlib

from app.rag.embedding import Embedder
from app.rag.models import ChunkRecord, PreparedSource
from app.rag.text import normalize_text


def chunk_source(
    source: PreparedSource,
    *,
    embedder: Embedder,
    content_hash: str,
    chunk_tokens: int,
    chunk_overlap: int,
) -> list[ChunkRecord]:
    if chunk_tokens <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_tokens:
        raise ValueError("Chunk size and overlap are incompatible")

    chunks: list[ChunkRecord] = []
    stride = chunk_tokens - chunk_overlap
    for section in source.sections:
        token_ids = embedder.tokenize(section.text)
        for offset in range(0, len(token_ids), stride):
            window = token_ids[offset : offset + chunk_tokens]
            if not window:
                continue
            text = normalize_text(embedder.decode(window))
            if not text:
                continue
            ordinal = len(chunks)
            digest_input = "\0".join(
                (source.source_id, content_hash, section.location, str(ordinal), text)
            ).encode()
            chunk_id = hashlib.sha256(digest_input).hexdigest()[:24]
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    source_id=source.source_id,
                    source_title=source.title,
                    location=section.location,
                    text=text,
                    token_count=len(window),
                )
            )
            if offset + chunk_tokens >= len(token_ids):
                break
    return chunks
