from app.core.settings import Settings
from app.rag.embedding import SentenceTransformerEmbedder
from app.rag.retrieval import RetrievalService
from app.rag.service import KnowledgeService
from app.rag.store import SnapshotStore


def create_knowledge_service(settings: Settings) -> KnowledgeService:
    embedder = SentenceTransformerEmbedder(
        model_id=settings.embedding_model_id,
        model_revision=settings.embedding_model_revision,
        cache_dir=settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
        cpu_threads=settings.embedding_cpu_threads,
    )
    if embedder.dimension != settings.embedding_dimension:
        raise RuntimeError(
            f"Embedding dimension {embedder.dimension} does not match configured "
            f"dimension {settings.embedding_dimension}"
        )
    return KnowledgeService(
        store=SnapshotStore(settings.knowledge_index_dir),
        embedder=embedder,
        chunk_tokens=settings.chunk_tokens,
        chunk_overlap=settings.chunk_overlap,
    )


def create_retrieval_service(
    settings: Settings, knowledge_service: KnowledgeService
) -> RetrievalService:
    return RetrievalService(
        knowledge_service,
        top_k=settings.chat_retrieval_top_k,
        max_per_source=settings.chat_retrieval_max_per_source,
    )
