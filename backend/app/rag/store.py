import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import faiss
import numpy as np
from numpy.typing import NDArray

from app.rag.errors import IndexCompatibilityError
from app.rag.models import ChunkRecord, ExtractedSection, IndexMetadata, SourceRecord


@dataclass
class SnapshotState:
    sources: dict[str, SourceRecord]
    contents: dict[str, tuple[ExtractedSection, ...]]
    chunks: list[ChunkRecord]
    vectors: NDArray[np.float32]
    index: faiss.Index
    metadata: IndexMetadata | None


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.snapshots_dir = root / "snapshots"
        self.current_link = root / "current"

    def _empty(self, dimension: int) -> SnapshotState:
        return SnapshotState(
            sources={},
            contents={},
            chunks=[],
            vectors=np.empty((0, dimension), dtype=np.float32),
            index=faiss.IndexFlatIP(dimension),
            metadata=None,
        )

    def _active_snapshot(self) -> Path | None:
        if not self.current_link.exists() and not self.current_link.is_symlink():
            return None
        return self.current_link.resolve(strict=True)

    def active_snapshot_id(self) -> str | None:
        snapshot = self._active_snapshot()
        return snapshot.name if snapshot is not None else None

    def _read_source_data(
        self, snapshot: Path
    ) -> tuple[
        dict[str, SourceRecord],
        dict[str, tuple[ExtractedSection, ...]],
        IndexMetadata,
    ]:
        metadata = IndexMetadata.model_validate_json((snapshot / "index-meta.json").read_text())
        source_items = json.loads((snapshot / "sources.json").read_text())
        sources = {item["source_id"]: SourceRecord.model_validate(item) for item in source_items}
        contents: dict[str, tuple[ExtractedSection, ...]] = {}
        for source in sources.values():
            raw_sections = json.loads((snapshot / source.content_file).read_text())
            contents[source.source_id] = tuple(
                ExtractedSection(location=item["location"], text=item["text"])
                for item in raw_sections
            )
        return sources, contents, metadata

    def load_source_data(
        self,
    ) -> tuple[
        dict[str, SourceRecord],
        dict[str, tuple[ExtractedSection, ...]],
        IndexMetadata | None,
    ]:
        snapshot = self._active_snapshot()
        if snapshot is None:
            return {}, {}, None
        return self._read_source_data(snapshot)

    def load(self, *, dimension: int) -> SnapshotState:
        snapshot = self._active_snapshot()
        if snapshot is None:
            return self._empty(dimension)
        sources, contents, metadata = self._read_source_data(snapshot)
        if metadata.dimension != dimension:
            raise IndexCompatibilityError(
                f"Index dimension {metadata.dimension} does not match model dimension {dimension}"
            )
        chunks = [
            ChunkRecord.model_validate_json(line)
            for line in (snapshot / "chunks.jsonl").read_text().splitlines()
            if line
        ]
        vectors = np.asarray(
            np.load(snapshot / "vectors.npy", allow_pickle=False), dtype=np.float32
        )
        if vectors.shape != (len(chunks), dimension):
            raise IndexCompatibilityError("Persisted vectors do not match chunk metadata")
        if not np.isfinite(vectors).all():
            raise IndexCompatibilityError("Persisted vectors contain non-finite values")
        index = faiss.read_index(str(snapshot / "index.faiss"))
        if (
            index.ntotal != len(chunks)
            or index.d != dimension
            or index.metric_type != faiss.METRIC_INNER_PRODUCT
        ):
            raise IndexCompatibilityError("FAISS index does not match persisted vectors")
        return SnapshotState(
            sources=sources,
            contents=contents,
            chunks=chunks,
            vectors=vectors,
            index=index,
            metadata=metadata,
        )

    def activate(
        self,
        *,
        sources: dict[str, SourceRecord],
        contents: dict[str, tuple[ExtractedSection, ...]],
        chunks: list[ChunkRecord],
        vectors: NDArray[np.float32],
        model_id: str,
        model_revision: str,
        dimension: int,
        chunk_tokens: int,
        chunk_overlap: int,
        chunking_version: str,
    ) -> IndexMetadata:
        if set(sources) != set(contents):
            raise ValueError("Source metadata and canonical content do not match")
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_id = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:10]}"
        temporary = self.snapshots_dir / f".tmp-{snapshot_id}"
        final = self.snapshots_dir / snapshot_id
        temporary.mkdir(mode=0o750)
        try:
            content_dir = temporary / "contents"
            content_dir.mkdir(mode=0o750)
            for source_id, sections in contents.items():
                record = sources[source_id]
                payload = [
                    {"location": section.location, "text": section.text} for section in sections
                ]
                destination = temporary / record.content_file
                destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            ordered_sources = sorted(sources.values(), key=lambda item: item.source_id)
            (temporary / "sources.json").write_text(
                json.dumps(
                    [item.model_dump(mode="json") for item in ordered_sources],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (temporary / "chunks.jsonl").write_text(
                "".join(f"{chunk.model_dump_json()}\n" for chunk in chunks),
                encoding="utf-8",
            )
            normalized_vectors = np.asarray(vectors, dtype=np.float32)
            if normalized_vectors.shape != (len(chunks), dimension):
                raise ValueError("Vector shape does not match chunks")
            np.save(temporary / "vectors.npy", normalized_vectors, allow_pickle=False)
            index = faiss.IndexFlatIP(dimension)
            if len(normalized_vectors):
                index.add(normalized_vectors)
            faiss.write_index(index, str(temporary / "index.faiss"))
            metadata = IndexMetadata(
                snapshot_id=snapshot_id,
                created_at=datetime.now(UTC),
                model_id=model_id,
                model_revision=model_revision,
                dimension=dimension,
                chunk_tokens=chunk_tokens,
                chunk_overlap=chunk_overlap,
                chunking_version=chunking_version,
                source_count=len(sources),
                chunk_count=len(chunks),
            )
            (temporary / "index-meta.json").write_text(
                metadata.model_dump_json(indent=2),
                encoding="utf-8",
            )
            if faiss.read_index(str(temporary / "index.faiss")).ntotal != len(chunks):
                raise ValueError("Generated FAISS index failed validation")
            os.replace(temporary, final)
            next_link = self.root / ".current-next"
            next_link.unlink(missing_ok=True)
            next_link.symlink_to(Path("snapshots") / snapshot_id)
            os.replace(next_link, self.current_link)
            return metadata
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
