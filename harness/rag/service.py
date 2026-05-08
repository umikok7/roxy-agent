from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from qdrant_client import QdrantClient
from qdrant_client.http import models

from harness.rag.chunker import DocumentChunk, chunk_document
from harness.rag.config import RagConfig
from harness.rag.loader import load_documents
from harness.rag.store import QdrantVectorStore, SearchResult


class DenseEmbedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FastEmbedder:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return [list(vector) for vector in self._model.embed(list(texts))]


class SparseEmbedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[models.SparseVector]: ...


# BM25
class FastSparseEmbedder:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def embed(self, texts: Sequence[str]) -> list[models.SparseVector]:
        if self._model is None:
            from fastembed import SparseTextEmbedding

            self._model = SparseTextEmbedding(model_name=self._model_name)
        return [
            models.SparseVector(indices=item.indices.tolist(), values=item.values.tolist())
            for item in self._model.embed(list(texts))
        ]


class Reranker(Protocol):
    def rerank(self, query: str, documents: Sequence[str]) -> list[float]: ...

# rerank
class FastCrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self._model_name)
        return [float(score) for score in self._model.rerank(query, list(documents))]


class KnowledgeBaseService:
    def __init__(
        self,
        config: RagConfig,
        *,
        dense_embedder: DenseEmbedder | None = None,
        sparse_embedder: SparseEmbedder | None = None,
        reranker: Reranker | None = None,
        client: QdrantClient | None = None,
        store: QdrantVectorStore | None = None,
    ) -> None:
        self.config = config
        self.dense_embedder = dense_embedder or FastEmbedder(config.dense_embedding_model)
        self.sparse_embedder = sparse_embedder or FastSparseEmbedder(config.sparse_embedding_model)
        self.reranker = reranker or FastCrossEncoderReranker(config.rerank_model)
        if store is not None:
            self.store = store
        else:
            qdrant_client = client or QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
            self.store = QdrantVectorStore(qdrant_client, config.collection_name)

    def _resolve_fusion_strategy(self) -> models.Fusion:
        if self.config.fusion_strategy == "dbsf":
            return models.Fusion.DBSF
        return models.Fusion.RRF

    def _apply_rerank(self, query: str, results: list[SearchResult], *, top_k: int) -> list[SearchResult]:
        if not results or not self.config.rerank_enabled:
            return results[:top_k]

        candidate_limit = min(len(results), self.config.rerank_candidate_limit)
        candidates = results[:candidate_limit]
        try:
            scores = self.reranker.rerank(query, [item.chunk.text for item in candidates])
        except Exception:
            return results[:top_k]

        reranked = [
            replace(item, rerank_score=score)
            for item, score in zip(candidates, scores, strict=True)
        ]
        reranked.sort(
            key=lambda item: item.rerank_score if item.rerank_score is not None else float("-inf"),
            reverse=True,
        )
        return reranked[:top_k]

    def build_chunks(self) -> list[DocumentChunk]:
        documents = load_documents(self.config.knowledge_dir)
        chunks: list[DocumentChunk] = []
        for document in documents:
            chunks.extend(
                chunk_document(
                    document,
                    chunk_size=self.config.chunk_size,
                    chunk_overlap=self.config.chunk_overlap,
                )
            )
        return chunks

    def index_documents(self) -> int:
        chunks = self.build_chunks()
        if not chunks:
            return 0
        texts = [chunk.text for chunk in chunks]
        dense_vectors = self.dense_embedder.embed(texts)
        sparse_vectors = self.sparse_embedder.embed(texts)
        return self.store.upsert(chunks, dense_vectors, sparse_vectors)

    def search(self, query: str, *, top_k: int | None = None) -> list[SearchResult]:
        cleaned = query.strip()
        if not cleaned:
            return []

        final_top_k = top_k or self.config.top_k
        dense_query_vector = self.dense_embedder.embed([cleaned])[0]
        sparse_query_vector = self.sparse_embedder.embed([cleaned])[0]
        results = self.store.search_hybrid(
            dense_query_vector,
            sparse_query_vector,
            dense_limit=self.config.hybrid_prefetch_limit_dense,
            sparse_limit=self.config.hybrid_prefetch_limit_sparse,
            limit=self.config.hybrid_candidate_limit,
            fusion=self._resolve_fusion_strategy(),
        )
        return self._apply_rerank(cleaned, results, top_k=final_top_k)

    def render_search_results(self, query: str, *, top_k: int | None = None) -> str:
        results = self.search(query, top_k=top_k)
        if not results:
            return "No knowledge base matches found."

        lines = [f"Knowledge base results for: {query}"]
        for index, item in enumerate(results, start=1):
            snippet = item.chunk.text.replace("\n", " ").strip()
            rerank_score = "n/a" if item.rerank_score is None else f"{item.rerank_score:.4f}"
            lines.append(
                f"{index}. title={item.chunk.title} source={item.chunk.source_path} "
                f"hybrid_score={item.hybrid_score:.4f} rerank_score={rerank_score} text={snippet}"
            )
        return "\n".join(lines)
