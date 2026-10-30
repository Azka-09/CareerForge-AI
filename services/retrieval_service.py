"""Vector index: FAISS when installed, otherwise numpy. Both are exact cosine search."""
import numpy as np
from utils.document_chunking import Chunk


def _norm(v: np.ndarray) -> np.ndarray:
    v = np.atleast_2d(np.asarray(v, dtype="float32"))
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(n == 0, 1, n)


class VectorIndex:
    def __init__(self):
        self.chunks: list[Chunk] = []
        self._vecs = None
        self._faiss = None

    def build(self, chunks: list[Chunk], vectors) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        self.chunks, self._vecs, self._faiss = list(chunks), _norm(vectors) if len(chunks) else None, None
        if self._vecs is not None:
            try:
                import faiss
                self._faiss = faiss.IndexFlatIP(self._vecs.shape[1])
                self._faiss.add(self._vecs)
            except Exception:  # faiss missing or failed: numpy fallback gives identical results
                self._faiss = None

    def _scores(self, q: np.ndarray) -> np.ndarray:
        if self._faiss is not None:
            d, i = self._faiss.search(q, len(self.chunks))
            s = np.full(len(self.chunks), -1.0, dtype="float32")
            s[i[0][i[0] >= 0]] = d[0][i[0] >= 0]
            return s
        return (self._vecs @ q[0]).astype("float32")

    def search(self, qvec, k: int, session_id: str, doc_names: set[str] | None = None,
               min_score: float = 0.0) -> list[tuple[Chunk, float]]:
        """Always filtered by session_id, so another session's chunks can never be returned."""
        if not self.chunks:
            return []
        s = self._scores(_norm(qvec))
        hits = [(c, float(s[i])) for i, c in enumerate(self.chunks)
                if c.session_id == session_id and (doc_names is None or c.doc_name in doc_names) and s[i] >= min_score]
        hits.sort(key=lambda x: -x[1])
        return hits[:k]
