"""
retrieval/__init__.py
---------------------
Public API for the clause retrieval subsystem.

Provides the primary interface for downstream pipeline stages (rules engine,
orchestration, audit) to retrieve policy wordings, benefit tables, and IRDAI
regulatory clauses relevant to a given pre-authorisation request.

Architecture Role:
    This module sits between Member 1's extraction output (PreAuthRequest) and
    Member 2's rules engine. It converts the structured claim data into a
    semantic search query and returns the top-k most relevant policy/regulatory
    clauses with full source provenance for citation (Guardrail #2).

Usage:
    from retrieval import retrieve_clauses, RetrievedClause
    clauses = retrieve_clauses(pre_auth_request, top_k=5)
"""

from __future__ import annotations

from typing import Optional

from retrieval.vector_store import RetrievedClause, VectorStore

# Module-level singletons
_store: Optional[VectorStore] = None
_embedder = None


def get_embedder():
    """Get or create the singleton Embedder instance."""
    global _embedder
    if _embedder is None:
        from retrieval.embedder import Embedder
        _embedder = Embedder()
    return _embedder


def get_store(index_dir: str = "retrieval/faiss_index") -> VectorStore:
    """Get or create the singleton VectorStore instance.

    Args:
        index_dir: Directory where the FAISS index and metadata are persisted.

    Returns:
        The loaded VectorStore instance.
    """
    global _store
    if _store is None:
        _store = VectorStore(index_dir=index_dir)
        _store.load()
    return _store


def retrieve_clauses(
    query: str,
    top_k: int = 5,
    index_dir: str = "retrieval/faiss_index",
) -> list[RetrievedClause]:
    """Retrieve the top-k most relevant policy/regulatory clauses for a query.

    This is the primary public API consumed by the orchestration graph's
    `retrieve_clauses` node. It builds a composite semantic search query
    from the claim data and returns cited clauses.

    Args:
        query: Natural language query string (typically composed from
               diagnosis + procedure + plan type + policy terms).
        top_k: Number of top results to return.
        index_dir: Path to the persisted FAISS index directory.

    Returns:
        List of RetrievedClause objects, each containing the clause text,
        source provenance, and similarity score.
    """
    store = get_store(index_dir=index_dir)
    embedder = get_embedder()
    return store.search(query_text=query, top_k=top_k, embed_fn=embedder.embed_text)


__all__ = [
    "retrieve_clauses",
    "get_store",
    "get_embedder",
    "RetrievedClause",
    "VectorStore",
]
