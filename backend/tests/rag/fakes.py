import hashlib
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray


class FakeEmbedder:
    model_id = "fake-embedder"
    model_revision = "test-revision"
    dimension = 4

    def __init__(self) -> None:
        self._tokens: dict[str, int] = {}
        self._words: dict[int, str] = {}
        self.fail_encoding = False

    def tokenize(self, text: str) -> list[int]:
        result = []
        for word in text.split():
            token_id = self._tokens.setdefault(word, len(self._tokens) + 1)
            self._words[token_id] = word
            result.append(token_id)
        return result

    def decode(self, token_ids: Sequence[int]) -> str:
        return " ".join(self._words[token_id] for token_id in token_ids)

    def encode_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        if self.fail_encoding:
            raise RuntimeError("forced embedding failure")
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vector = np.asarray([digest[index] + 1 for index in range(4)], dtype=np.float32)
            vectors.append(vector / np.linalg.norm(vector))
        if not vectors:
            return np.empty((0, self.dimension), dtype=np.float32)
        return np.asarray(vectors, dtype=np.float32)

    def encode_query(self, text: str) -> NDArray[np.float32]:
        return self.encode_documents([text])[0]
