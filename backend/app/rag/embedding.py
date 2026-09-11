from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class Embedder(Protocol):
    model_id: str
    model_revision: str
    dimension: int

    def tokenize(self, text: str) -> list[int]: ...

    def decode(self, token_ids: Sequence[int]) -> str: ...

    def encode_documents(self, texts: Sequence[str]) -> NDArray[np.float32]: ...


class SentenceTransformerEmbedder:
    def __init__(
        self,
        *,
        model_id: str,
        model_revision: str,
        cache_dir: Path,
        local_files_only: bool = False,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_id = model_id
        self.model_revision = model_revision
        self._model = SentenceTransformer(
            model_id,
            revision=model_revision,
            cache_folder=str(cache_dir),
            local_files_only=local_files_only,
            device="cpu",
        )
        self.dimension = self._model.get_embedding_dimension() or 0
        if self.dimension <= 0:
            raise RuntimeError("Embedding model did not report a valid dimension")

    def tokenize(self, text: str) -> list[int]:
        token_ids = self._model.tokenizer.encode(text, add_special_tokens=False)
        return [int(token_id) for token_id in token_ids]

    def decode(self, token_ids: Sequence[int]) -> str:
        return str(
            self._model.tokenizer.decode(
                list(token_ids),
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )
        ).strip()

    def encode_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        vectors = self._model.encode(
            list(texts),
            batch_size=16,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)
