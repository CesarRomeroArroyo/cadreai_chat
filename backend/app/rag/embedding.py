import os
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    model_id: str
    model_revision: str
    dimension: int

    def tokenize(self, text: str) -> list[int]: ...

    def decode(self, token_ids: Sequence[int]) -> str: ...

    def encode_documents(self, texts: Sequence[str]) -> NDArray[np.float32]: ...

    def encode_query(self, text: str) -> NDArray[np.float32]: ...


class SentenceTransformerEmbedder:
    def __init__(
        self,
        *,
        model_id: str,
        model_revision: str,
        cache_dir: Path,
        local_files_only: bool = False,
        cpu_threads: int = 1,
    ) -> None:
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(cpu_threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            if torch.get_num_interop_threads() != 1:
                raise RuntimeError("Torch interop thread configuration is incompatible") from None
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
        self._inference_lock = threading.Lock()
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
        with self._inference_lock:
            vectors = self._model.encode(
                list(texts),
                batch_size=16,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return np.asarray(vectors, dtype=np.float32)

    def encode_query(self, text: str) -> NDArray[np.float32]:
        vectors = self.encode_documents([f"{QUERY_PREFIX}{text.strip()}"])
        return vectors[0]
