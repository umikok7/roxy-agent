from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models

from harness.rag.chunker import DocumentChunk
from harness.rag.config import RagConfig
from harness.rag.service import KnowledgeBaseService
from harness.rag.store import SearchResult


class FakeDenseEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            refund_score = 1.0 if ("退款" in text or "refund" in lowered) else 0.0
            shipping_score = 1.0 if ("发货" in text or "shipping" in lowered) else 0.0
            vectors.append([refund_score, shipping_score])
        return vectors


class FakeSparseEmbedder:
    def embed(self, texts: list[str]) -> list[models.SparseVector]:
        vectors: list[models.SparseVector] = []
        for text in texts:
            if "退款" in text:
                vectors.append(models.SparseVector(indices=[101], values=[2.0]))
            elif "发货" in text:
                vectors.append(models.SparseVector(indices=[202], values=[2.0]))
            else:
                vectors.append(models.SparseVector(indices=[999], values=[1.0]))
        return vectors


class FakeReranker:
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [10.0 if "7 天" in doc else 1.0 for doc in documents]


class RaisingReranker:
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        raise RuntimeError("rerank unavailable")


class FakeStore:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    def upsert(self, chunks, dense_vectors, sparse_vectors) -> int:
        return len(chunks)

    def search_hybrid(self, dense_query_vector, sparse_query_vector, **kwargs) -> list[SearchResult]:
        self.calls.append(
            {
                "dense_query_vector": dense_query_vector,
                "sparse_query_vector": sparse_query_vector,
                **kwargs,
            }
        )
        return list(self.results)


def test_knowledge_base_service_returns_expected_chunk(tmp_path: Path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "refund.md").write_text("# 退款政策\n用户在 7 天内可以申请退款。", encoding="utf-8")
    (knowledge_dir / "shipping.txt").write_text("发货时效为 48 小时内出库。", encoding="utf-8")

    config = RagConfig(
        qdrant_url=":memory:",
        collection_name="kb_test",
        knowledge_dir=knowledge_dir,
        dense_embedding_model="fake",
        sparse_embedding_model="fake",
        rerank_model="fake",
        chunk_size=200,
        chunk_overlap=20,
    )
    service = KnowledgeBaseService(
        config,
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        reranker=FakeReranker(),
        client=QdrantClient(":memory:"),
    )

    indexed = service.index_documents()
    results = service.search("退款多久到账", top_k=1)

    assert indexed == 2
    assert len(results) == 1
    assert results[0].chunk.source_path == "refund.md"
    assert "退款" in results[0].chunk.text
    assert results[0].rerank_score == 10.0


def test_knowledge_base_service_calls_hybrid_query_with_rrf():
    config = RagConfig(
        qdrant_url=":memory:",
        collection_name="kb_test",
        knowledge_dir=Path("docs/knowledge"),
        dense_embedding_model="fake",
        sparse_embedding_model="fake",
        rerank_model="fake",
    )
    fake_store = FakeStore(
        [
            SearchResult(
                chunk=DocumentChunk(
                    chunk_id="a",
                    source_path="refund.md",
                    title="退款政策",
                    text="支持 7 天退款",
                ),
                hybrid_score=0.7,
            )
        ]
    )
    service = KnowledgeBaseService(
        config,
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        reranker=FakeReranker(),
        store=fake_store,
    )

    results = service.search("退款政策", top_k=1)

    assert len(results) == 1
    assert fake_store.calls[0]["fusion"] == models.Fusion.RRF
    assert fake_store.calls[0]["dense_limit"] == config.hybrid_prefetch_limit_dense
    assert fake_store.calls[0]["sparse_limit"] == config.hybrid_prefetch_limit_sparse
    assert fake_store.calls[0]["limit"] == config.hybrid_candidate_limit


def test_knowledge_base_service_reranks_candidates():
    config = RagConfig(
        qdrant_url=":memory:",
        collection_name="kb_test",
        knowledge_dir=Path("docs/knowledge"),
        dense_embedding_model="fake",
        sparse_embedding_model="fake",
        rerank_model="fake",
    )
    fake_store = FakeStore(
        [
            SearchResult(
                chunk=DocumentChunk(
                    chunk_id="shipping",
                    source_path="shipping.txt",
                    title="发货说明",
                    text="发货时效为 48 小时内出库。",
                ),
                hybrid_score=0.99,
            ),
            SearchResult(
                chunk=DocumentChunk(
                    chunk_id="refund",
                    source_path="refund.md",
                    title="退款政策",
                    text="用户在 7 天内可以申请退款。",
                ),
                hybrid_score=0.50,
            ),
        ]
    )
    service = KnowledgeBaseService(
        config,
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        reranker=FakeReranker(),
        store=fake_store,
    )

    results = service.search("退款政策", top_k=2)

    assert [item.chunk.chunk_id for item in results] == ["refund", "shipping"]
    assert results[0].rerank_score == 10.0


def test_knowledge_base_service_falls_back_to_hybrid_when_rerank_fails():
    config = RagConfig(
        qdrant_url=":memory:",
        collection_name="kb_test",
        knowledge_dir=Path("docs/knowledge"),
        dense_embedding_model="fake",
        sparse_embedding_model="fake",
        rerank_model="fake",
    )
    original = [
        SearchResult(
            chunk=DocumentChunk(
                chunk_id="shipping",
                source_path="shipping.txt",
                title="发货说明",
                text="发货时效为 48 小时内出库。",
            ),
            hybrid_score=0.99,
        ),
        SearchResult(
            chunk=DocumentChunk(
                chunk_id="refund",
                source_path="refund.md",
                title="退款政策",
                text="用户在 7 天内可以申请退款。",
            ),
            hybrid_score=0.50,
        ),
    ]
    service = KnowledgeBaseService(
        config,
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
        reranker=RaisingReranker(),
        store=FakeStore(original),
    )

    results = service.search("退款政策", top_k=2)

    assert [item.chunk.chunk_id for item in results] == ["shipping", "refund"]
    assert all(item.rerank_score is None for item in results)
