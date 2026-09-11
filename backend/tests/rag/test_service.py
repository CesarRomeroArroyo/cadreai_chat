from dataclasses import replace
from pathlib import Path

import pytest

from app.rag.errors import IndexCompatibilityError, IngestionError
from app.rag.models import IngestionStatus
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotStore
from tests.rag.fakes import FakeEmbedder


def make_service(tmp_path: Path) -> tuple[KnowledgeService, FakeEmbedder]:
    embedder = FakeEmbedder()
    return (
        KnowledgeService(
            store=SnapshotStore(tmp_path / "index"),
            embedder=embedder,
            chunk_tokens=4,
            chunk_overlap=1,
        ),
        embedder,
    )


def test_upsert_is_idempotent_and_replaces_changed_chunks(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    initial = service.prepare_file(
        filename="services.txt",
        content_type="text/plain",
        data=b"strategy engineering agents leadership security",
    )

    first = service.upsert([initial])
    unchanged = service.upsert([initial])
    updated_source = service.prepare_file(
        filename="services.txt",
        content_type="text/plain",
        data=b"maturity assessment workflow automation",
    )
    updated = service.upsert([updated_source])
    state = service.store.load(dimension=service.embedder.dimension)

    assert first[0].status == IngestionStatus.INDEXED
    assert unchanged[0].status == IngestionStatus.UNCHANGED
    assert updated[0].status == IngestionStatus.UPDATED
    assert len(state.sources) == 1
    assert all("leadership" not in chunk.text for chunk in state.chunks)
    assert any("maturity" in chunk.text for chunk in state.chunks)


def test_duplicate_content_is_not_indexed_twice(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    first = service.prepare_file(
        filename="one.txt", content_type="text/plain", data=b"same approved content"
    )
    duplicate = service.prepare_file(
        filename="two.txt", content_type="text/plain", data=b"same approved content"
    )

    results = service.upsert([first, duplicate])

    assert [result.status for result in results] == [
        IngestionStatus.INDEXED,
        IngestionStatus.DUPLICATE,
    ]
    assert len(service.list_sources()) == 1


def test_rejects_duplicate_or_invalid_source_ids_in_batch(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    source = service.prepare_file(
        filename="valid.txt", content_type="text/plain", data=b"approved content"
    )

    with pytest.raises(IngestionError, match="duplicate source IDs"):
        service.upsert([source, source])
    with pytest.raises(IngestionError, match="Source IDs"):
        service.upsert([replace(source, source_id="../../unsafe")])

    assert service.list_sources() == []


def test_remove_deletes_source_chunks_and_rebuilds_index(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    source = service.prepare_file(
        filename="remove.txt", content_type="text/plain", data=b"remove this source"
    )
    result = service.upsert([source])[0]

    assert result.source_id is not None
    assert service.remove(result.source_id) is True
    state = service.store.load(dimension=service.embedder.dimension)
    assert state.sources == {}
    assert state.chunks == []
    assert state.vectors.shape == (0, service.embedder.dimension)
    assert service.remove(result.source_id) is False


def test_rebuild_regenerates_vectors_from_persisted_content(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    source = service.prepare_file(
        filename="rebuild.md",
        content_type="text/markdown",
        data=b"# Assessment\nAI maturity assessment details",
    )
    service.upsert([source])

    rebuilt_chunks = service.rebuild()
    state = service.store.load(dimension=service.embedder.dimension)

    assert rebuilt_chunks == len(state.chunks)
    assert rebuilt_chunks > 0


def test_embedding_failure_leaves_active_snapshot_unchanged(tmp_path: Path) -> None:
    service, embedder = make_service(tmp_path)
    initial = service.prepare_file(
        filename="stable.txt", content_type="text/plain", data=b"stable content"
    )
    service.upsert([initial])
    original_snapshot = service.store.current_link.resolve()
    embedder.fail_encoding = True
    changed = service.prepare_file(
        filename="stable.txt", content_type="text/plain", data=b"changed content"
    )

    with pytest.raises(RuntimeError, match="forced embedding failure"):
        service.upsert([changed])

    assert service.store.current_link.resolve() == original_snapshot
    assert (
        service.list_sources()[0].content_hash
        == service.store.load(dimension=embedder.dimension).sources[initial.source_id].content_hash
    )


def test_rejects_index_from_different_model_revision(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    source = service.prepare_file(
        filename="model.txt", content_type="text/plain", data=b"model compatibility"
    )
    service.upsert([source])
    incompatible = FakeEmbedder()
    incompatible.model_revision = "different-revision"
    other_service = KnowledgeService(
        store=service.store,
        embedder=incompatible,
        chunk_tokens=4,
        chunk_overlap=1,
    )

    with pytest.raises(IndexCompatibilityError, match="metadata"):
        other_service.list_sources()

    assert other_service.rebuild() > 0
    assert len(other_service.list_sources()) == 1
