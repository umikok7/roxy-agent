from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models

from harness.rag.chunker import DocumentChunk
from harness.rag.store import QdrantVectorStore


def test_qdrant_vector_store_uses_named_dense_and_sparse_vectors():
    client = QdrantClient(":memory:")
    store = QdrantVectorStore(client, "internal_kb_test")
    chunks = [
        DocumentChunk(chunk_id="a", source_path="faq/a.txt", title="A", text="退款政策说明"),
        DocumentChunk(chunk_id="b", source_path="faq/b.txt", title="B", text="发货时效说明"),
    ]
    dense_vectors = [[1.0, 0.0], [0.0, 1.0]]
    sparse_vectors = [
        models.SparseVector(indices=[1], values=[1.0]),
        models.SparseVector(indices=[2], values=[1.0]),
    ]

    upserted = store.upsert(chunks, dense_vectors, sparse_vectors)
    info = client.get_collection("internal_kb_test")

    assert upserted == 2
    assert info.config.params.vectors[store.DENSE_VECTOR_NAME].size == 2
    assert info.config.params.sparse_vectors[store.SPARSE_VECTOR_NAME].modifier == models.Modifier.IDF


def test_qdrant_vector_store_hybrid_search_returns_expected_chunk():
    client = QdrantClient(":memory:")
    store = QdrantVectorStore(client, "internal_kb_test")
    chunks = [
        DocumentChunk(chunk_id="a", source_path="faq/a.txt", title="A", text="退款政策说明"),
        DocumentChunk(chunk_id="b", source_path="faq/b.txt", title="B", text="发货时效说明"),
    ]
    dense_vectors = [[1.0, 0.0], [0.0, 1.0]]
    sparse_vectors = [
        models.SparseVector(indices=[11], values=[1.0]),
        models.SparseVector(indices=[22], values=[1.0]),
    ]

    store.upsert(chunks, dense_vectors, sparse_vectors)
    results = store.search_hybrid(
        [0.98, 0.02],
        models.SparseVector(indices=[11], values=[1.0]),
        dense_limit=2,
        sparse_limit=2,
        limit=1,
        fusion=models.Fusion.RRF,
    )

    assert len(results) == 1
    assert results[0].chunk.chunk_id == "a"
    assert results[0].hybrid_score > 0
