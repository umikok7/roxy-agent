from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from harness.rag.chunker import DocumentChunk


@dataclass(slots=True)
class SearchResult:
    chunk: DocumentChunk
    hybrid_score: float
    rerank_score: float | None = None


class QdrantVectorStore:
    DENSE_VECTOR_NAME = "dense"
    SPARSE_VECTOR_NAME = "sparse"

    def __init__(self, client: QdrantClient, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    def collection_exists(self) -> bool:
        collections = self.client.get_collections().collections
        return self.collection_name in {item.name for item in collections}

    def recreate_collection(self, dense_vector_size: int) -> None:
        if self.collection_exists():
            self.client.delete_collection(collection_name=self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                self.DENSE_VECTOR_NAME: models.VectorParams(
                    size=dense_vector_size,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                self.SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )

    def upsert(
        self,
        chunks: list[DocumentChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[models.SparseVector],
    ) -> int:
        if not chunks:
            return 0
        if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
            raise ValueError("Chunk count must match dense and sparse vector counts.")

        self.recreate_collection(len(dense_vectors[0]))
        timestamp = datetime.now(UTC).isoformat()
        points = [
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, chunk.chunk_id)),
                vector={
                    self.DENSE_VECTOR_NAME: dense_vector,
                    self.SPARSE_VECTOR_NAME: sparse_vector,
                },
                payload={
                    "chunk_id": chunk.chunk_id,
                    "source_path": chunk.source_path,
                    "title": chunk.title,
                    "text": chunk.text,
                    "updated_at": timestamp,
                },
            )
            for chunk, dense_vector, sparse_vector in zip(chunks, dense_vectors, sparse_vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
        return len(points)

    def search_hybrid(
        self,
        dense_query_vector: list[float],
        sparse_query_vector: models.SparseVector,
        *,
        dense_limit: int,
        sparse_limit: int,
        limit: int,
        fusion: models.Fusion,
    ) -> list[SearchResult]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                models.Prefetch(
                    query=sparse_query_vector,
                    using=self.SPARSE_VECTOR_NAME,
                    limit=sparse_limit,
                ),
                models.Prefetch(
                    query=dense_query_vector,
                    using=self.DENSE_VECTOR_NAME,
                    limit=dense_limit,
                ),
            ],
            query=models.FusionQuery(fusion=fusion),
            limit=limit,
            with_payload=True,
        )
        results: list[SearchResult] = []
        for item in response.points:
            payload: dict[str, Any] = item.payload or {}
            results.append(
                SearchResult(
                    chunk=DocumentChunk(
                        chunk_id=str(payload.get("chunk_id", "")),
                        source_path=str(payload.get("source_path", "")),
                        title=str(payload.get("title", "")),
                        text=str(payload.get("text", "")),
                    ),
                    hybrid_score=float(item.score),
                )
            )
        return results
