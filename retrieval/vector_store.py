"""
retrieval/vector_store.py
-------------------------
FAISS-based vector store for policy wording and IRDAI regulatory clause retrieval.

This module implements the core similarity-search infrastructure for the
cashless pre-authorisation pipeline. It enables the agent to retrieve the
most relevant policy clauses, benefit tables, and IRDAI regulatory excerpts
given a natural-language query derived from the pre-auth request.

Architecture Role:
    Sits at Stage 3 of the pipeline (Retrieval). Consumes chunked and embedded
    policy documents from `retrieval/embedder.py` and exposes a search interface
    used by the orchestration graph's `retrieve_clauses` node.

Guardrail Compliance:
    - Guardrail #2 (Grounded output): Every retrieved clause carries full source
      provenance (source_file, section, circular_date) so downstream nodes can
      produce verifiable citations.
    - Guardrail #6 (Cite the live text): Metadata includes the IRDAI circular
      number and gazette date when applicable.

Metrics:
    - Retrieval quality (Recall@k): The `evaluate_recall_at_k()` method measures
      whether the governing clause is actually retrieved in the top-k results.

Usage:
    from retrieval.vector_store import VectorStore, RetrievedClause

    # Build a new index from document chunks
    store = VectorStore(index_dir="retrieval/faiss_index")
    store.build_index(chunks)
    store.save()

    # Load and search
    store = VectorStore(index_dir="retrieval/faiss_index")
    store.load()
    results = store.search("room rent sub-limit for individual plan", top_k=5)
"""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ChunkMetadata:
    """Metadata attached to each document chunk for source provenance.

    Every chunk in the vector store carries this metadata so that downstream
    citation verification (Guardrail #2) can trace any clause reference back
    to its exact source document, section, and regulatory date (Guardrail #6).

    Attributes:
        source_file: Relative path to the source document.
        section: Section heading or identifier within the document.
        chunk_id: Unique identifier for this chunk within the corpus.
        document_type: Category of document — "policy_wording", "benefit_table",
                       or "irdai_circular".
        circular_date: Gazette/publication date for IRDAI documents (Guardrail #6).
                       Format: "DD-Mon-YYYY" (e.g., "29-May-2024").
        circular_number: IRDAI circular reference number, if applicable.
        policy_type: Insurance plan type this document pertains to, if applicable.
    """

    source_file: str
    section: str = ""
    chunk_id: str = ""
    document_type: str = "policy_wording"
    circular_date: str = ""
    circular_number: str = ""
    policy_type: str = ""


@dataclass
class DocumentChunk:
    """A single chunk of text from a policy/regulatory document, ready for embedding.

    Attributes:
        text: The chunk text content.
        metadata: Source provenance metadata.
        embedding: Pre-computed embedding vector (set by the embedder).
    """

    text: str
    metadata: ChunkMetadata
    embedding: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class RetrievedClause:
    """A single clause retrieved from the vector store in response to a query.

    This is the primary output type consumed by the rules engine and LLM
    reasoning node. Each clause carries full provenance for citation
    verification (Guardrail #2).

    Attributes:
        chunk_text: The retrieved clause/chunk text.
        source_file: Origin document path for citation.
        section: Section within the document.
        document_type: Category — "policy_wording", "benefit_table", "irdai_circular".
        circular_date: IRDAI gazette date for regulatory documents (Guardrail #6).
        circular_number: IRDAI circular reference number.
        similarity_score: Cosine similarity score (0.0–1.0) from the FAISS search.
        chunk_id: Unique identifier for traceability.
    """

    chunk_text: str
    source_file: str
    section: str = ""
    document_type: str = "policy_wording"
    circular_date: str = ""
    circular_number: str = ""
    similarity_score: float = 0.0
    chunk_id: str = ""

    @property
    def clause_id(self) -> str:
        """Alias for chunk_id."""
        return self.chunk_id

    @property
    def text(self) -> str:
        """Alias for chunk_text."""
        return self.chunk_text

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary representation."""
        return {
            "chunk_id": self.chunk_id,
            "clause_id": self.chunk_id,
            "chunk_text": self.chunk_text,
            "text": self.chunk_text,
            "source_file": self.source_file,
            "section": self.section,
            "document_type": self.document_type,
            "circular_date": self.circular_date,
            "circular_number": self.circular_number,
            "similarity_score": self.similarity_score,
        }


# ============================================================================
# FAISS Vector Store
# ============================================================================


class VectorStore:
    """FAISS-backed vector store for semantic search over policy/regulatory documents.

    This class manages the lifecycle of a FAISS index:
    - **Build**: Accepts pre-embedded document chunks, constructs a FAISS index.
    - **Save/Load**: Persists and restores the index + metadata to/from disk.
    - **Search**: Performs similarity search and returns RetrievedClause objects.
    - **Evaluate**: Measures Recall@k against a labelled query set.

    Design Decisions:
        - Uses FAISS IndexFlatIP (inner product on L2-normalized vectors) for
          cosine similarity. This is exact search — appropriate for our corpus
          size (~hundreds of chunks). For production scale, switch to IndexIVFFlat.
        - Metadata is stored separately in a JSON file alongside the FAISS index
          binary, since FAISS does not natively support metadata storage.

    Args:
        index_dir: Directory path for persisting the FAISS index and metadata.
        embedding_dim: Dimensionality of the embedding vectors. Defaults to 384
                       (matching sentence-transformers/all-MiniLM-L6-v2).
    """

    def __init__(
        self,
        index_dir: str = "retrieval/faiss_index",
        embedding_dim: int = 384,
    ) -> None:
        self.index_dir = index_dir
        self.embedding_dim = embedding_dim

        # These are populated by build_index() or load().
        self._index = None  # FAISS index object
        self._chunks: list[DocumentChunk] = []  # Parallel list of chunks with metadata
        self._is_ready = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build_index(self, chunks: list[DocumentChunk]) -> None:
        """Build a FAISS index from a list of pre-embedded document chunks.

        Each chunk must have its `embedding` field populated (via the embedder
        module). Embeddings are L2-normalized before indexing so that inner
        product search yields cosine similarity scores.

        Args:
            chunks: List of DocumentChunk objects with pre-computed embeddings.

        Raises:
            ImportError: If faiss-cpu is not installed.
            ValueError: If any chunk is missing an embedding or has the wrong
                        dimensionality.
        """
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss-cpu is required for the vector store. "
                "Install it with: pip install faiss-cpu>=1.7.4"
            )

        if not chunks:
            raise ValueError("Cannot build index from an empty chunk list.")

        # Validate embeddings
        for i, chunk in enumerate(chunks):
            if chunk.embedding is None:
                raise ValueError(
                    f"Chunk {i} (chunk_id={chunk.metadata.chunk_id}) is missing "
                    f"an embedding. Run the embedder first."
                )
            if chunk.embedding.shape[0] != self.embedding_dim:
                raise ValueError(
                    f"Chunk {i} has embedding dim {chunk.embedding.shape[0]}, "
                    f"expected {self.embedding_dim}."
                )

        # Stack embeddings into a single matrix
        embeddings = np.vstack(
            [chunk.embedding.astype(np.float32) for chunk in chunks]
        )

        # L2-normalize for cosine similarity via inner product
        faiss.normalize_L2(embeddings)

        # Build a flat inner-product index (exact search, suitable for <10k chunks)
        index = faiss.IndexFlatIP(self.embedding_dim)
        index.add(embeddings)

        self._index = index
        self._chunks = list(chunks)
        self._is_ready = True

        logger.info(
            "Built FAISS index with %d chunks (dim=%d).",
            len(chunks),
            self.embedding_dim,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist the FAISS index and chunk metadata to disk.

        Creates two files in `index_dir`:
        - `index.faiss`: The binary FAISS index.
        - `metadata.json`: Serialized chunk metadata (text + provenance).

        Raises:
            RuntimeError: If the index has not been built yet.
        """
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss-cpu is required. Install with: pip install faiss-cpu>=1.7.4"
            )

        if not self._is_ready or self._index is None:
            raise RuntimeError(
                "No index to save. Call build_index() first."
            )

        os.makedirs(self.index_dir, exist_ok=True)

        # Save FAISS index binary
        index_path = os.path.join(self.index_dir, "index.faiss")
        faiss.write_index(self._index, index_path)

        # Save chunk metadata as JSON (FAISS doesn't store metadata natively)
        metadata_path = os.path.join(self.index_dir, "metadata.json")
        serializable = []
        for chunk in self._chunks:
            serializable.append(
                {
                    "text": chunk.text,
                    "metadata": asdict(chunk.metadata),
                }
            )

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

        logger.info(
            "Saved FAISS index (%d vectors) to %s", len(self._chunks), self.index_dir
        )

    def load(self) -> None:
        """Load a previously persisted FAISS index and metadata from disk.

        Raises:
            FileNotFoundError: If the index files do not exist.
            ImportError: If faiss-cpu is not installed.
        """
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss-cpu is required. Install with: pip install faiss-cpu>=1.7.4"
            )

        index_path = os.path.join(self.index_dir, "index.faiss")
        metadata_path = os.path.join(self.index_dir, "metadata.json")

        if not os.path.exists(index_path):
            raise FileNotFoundError(
                f"FAISS index not found at {index_path}. "
                "Run build_index() and save() first."
            )

        if not os.path.exists(metadata_path):
            raise FileNotFoundError(
                f"Metadata file not found at {metadata_path}. "
                "Run build_index() and save() first."
            )

        # Load FAISS index
        self._index = faiss.read_index(index_path)

        # Load chunk metadata
        with open(metadata_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        self._chunks = []
        for entry in raw_data:
            meta = ChunkMetadata(**entry["metadata"])
            self._chunks.append(
                DocumentChunk(text=entry["text"], metadata=meta)
            )

        self._is_ready = True
        self.embedding_dim = self._index.d

        logger.info(
            "Loaded FAISS index with %d vectors (dim=%d) from %s",
            self._index.ntotal,
            self.embedding_dim,
            self.index_dir,
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        query_embedding: Optional[np.ndarray] = None,
        embed_fn=None,
    ) -> list[RetrievedClause]:
        """Search the index for the most relevant clauses.

        Accepts either a pre-computed query embedding or a text query with an
        embedding function. Returns the top-k most similar clauses with full
        source provenance metadata.

        Args:
            query_text: The natural-language query string (used for logging
                        if query_embedding is provided directly).
            top_k: Number of top results to return.
            query_embedding: Pre-computed query embedding vector. If None,
                             `embed_fn` must be provided to compute it.
            embed_fn: Callable that takes a string and returns a numpy array
                      embedding. Used when query_embedding is not provided.

        Returns:
            List of RetrievedClause objects sorted by descending similarity.

        Raises:
            RuntimeError: If the index is not loaded/built.
            ValueError: If neither query_embedding nor embed_fn is provided.
        """
        if not self._is_ready or self._index is None:
            raise RuntimeError(
                "Vector store is not ready. Call build_index() or load() first."
            )

        # Compute embedding if not provided
        if query_embedding is None:
            if embed_fn is None:
                raise ValueError(
                    "Either `query_embedding` or `embed_fn` must be provided. "
                    "Pass an embedding function from retrieval/embedder.py."
                )
            query_embedding = embed_fn(query_text)

        # Ensure correct shape and type
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        query_embedding = query_embedding.astype(np.float32)

        # L2-normalize for cosine similarity
        try:
            import faiss

            faiss.normalize_L2(query_embedding)
        except ImportError:
            # Fallback: manual L2 normalization
            norm = np.linalg.norm(query_embedding, axis=1, keepdims=True)
            query_embedding = query_embedding / (norm + 1e-9)

        # Clamp top_k to index size
        actual_k = min(top_k, self._index.ntotal)

        # Search
        scores, indices = self._index.search(query_embedding, actual_k)

        # Build results
        results: list[RetrievedClause] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                # FAISS returns -1 for missing results when k > ntotal
                continue

            chunk = self._chunks[idx]
            results.append(
                RetrievedClause(
                    chunk_text=chunk.text,
                    source_file=chunk.metadata.source_file,
                    section=chunk.metadata.section,
                    document_type=chunk.metadata.document_type,
                    circular_date=chunk.metadata.circular_date,
                    circular_number=chunk.metadata.circular_number,
                    similarity_score=float(score),
                    chunk_id=chunk.metadata.chunk_id,
                )
            )

        logger.debug(
            "Search for '%s' returned %d results (top score=%.4f).",
            query_text[:80],
            len(results),
            results[0].similarity_score if results else 0.0,
        )

        return results

    # ------------------------------------------------------------------
    # Evaluation (Metrics: Retrieval quality — Recall@k)
    # ------------------------------------------------------------------

    def evaluate_recall_at_k(
        self,
        labelled_queries: list[dict],
        embed_fn,
        k: int = 5,
    ) -> dict:
        """Evaluate Recall@k on a labelled query set.

        Each query in the labelled set must have:
        - "query": str — the search query
        - "expected_chunk_ids": list[str] — chunk IDs that should appear in results

        This directly measures the "Retrieval quality" dimension from the
        evaluation rubric: "Was the governing clause actually retrieved?"

        Args:
            labelled_queries: List of dicts with "query" and "expected_chunk_ids".
            embed_fn: Embedding function (str → np.ndarray).
            k: Number of top results to consider.

        Returns:
            Dict with:
            - "recall_at_k": float — average recall across all queries
            - "per_query": list of per-query recall scores
            - "total_queries": int
            - "k": int
        """
        if not labelled_queries:
            return {"recall_at_k": 0.0, "per_query": [], "total_queries": 0, "k": k}

        per_query_recall = []

        for entry in labelled_queries:
            query_text = entry["query"]
            expected_ids = set(entry["expected_chunk_ids"])

            results = self.search(
                query_text=query_text,
                top_k=k,
                embed_fn=embed_fn,
            )

            retrieved_ids = {r.chunk_id for r in results}
            hits = len(expected_ids & retrieved_ids)
            recall = hits / len(expected_ids) if expected_ids else 1.0
            per_query_recall.append(recall)

        avg_recall = sum(per_query_recall) / len(per_query_recall)

        logger.info(
            "Recall@%d evaluation: %.4f (over %d queries)",
            k,
            avg_recall,
            len(labelled_queries),
        )

        return {
            "recall_at_k": avg_recall,
            "per_query": per_query_recall,
            "total_queries": len(labelled_queries),
            "k": k,
        }

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Whether the index is built/loaded and ready for search."""
        return self._is_ready

    @property
    def num_chunks(self) -> int:
        """Number of chunks in the index."""
        return len(self._chunks) if self._chunks else 0

    def __repr__(self) -> str:
        status = "ready" if self._is_ready else "not ready"
        return (
            f"VectorStore(index_dir='{self.index_dir}', "
            f"dim={self.embedding_dim}, "
            f"chunks={self.num_chunks}, "
            f"status={status})"
        )
