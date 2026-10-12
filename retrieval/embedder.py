"""
retrieval/embedder.py
---------------------
Document chunking and embedding generation for the policy/regulatory corpus.

This module converts raw policy wording documents, benefit tables, and IRDAI
circular excerpts into semantically meaningful chunks, then computes dense
vector embeddings suitable for FAISS indexing.

Architecture Role:
    Preprocessing layer between the raw corpus (retrieval/corpus/) and the
    FAISS vector store (retrieval/vector_store.py). Called during index build
    time, not at query time (query embedding is computed inline).

Embedding Model:
    Default: sentence-transformers/all-MiniLM-L6-v2 (384-dim, runs locally).
    Fallback: OpenAI text-embedding-3-small if API key is set.

Usage:
    from retrieval.embedder import Embedder

    embedder = Embedder()
    chunks = embedder.chunk_documents(corpus_dir="retrieval/corpus")
    chunks = embedder.embed_chunks(chunks)
    # → pass to VectorStore.build_index(chunks)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import numpy as np

from retrieval.vector_store import ChunkMetadata, DocumentChunk

logger = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 400  # tokens (approx)
DEFAULT_CHUNK_OVERLAP = 80  # tokens overlap between adjacent chunks
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384


class Embedder:
    """Document chunker and embedding generator for the retrieval pipeline.

    Handles two responsibilities:
    1. **Chunking**: Splits raw text documents into semantically coherent chunks
       of ~300–500 tokens with configurable overlap, preserving section metadata.
    2. **Embedding**: Computes dense vector embeddings for each chunk using
       sentence-transformers (local) or OpenAI embeddings API.

    Args:
        model_name: Name of the sentence-transformers model to load.
        embedding_dim: Expected dimensionality of output embeddings.
        chunk_size: Target chunk size in approximate token count.
        chunk_overlap: Number of overlapping tokens between adjacent chunks.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self.model_name = model_name
        self.embedding_dim = embedding_dim
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._model = None  # Lazy-loaded sentence-transformers model

    # ------------------------------------------------------------------
    # Model Loading
    # ------------------------------------------------------------------

    def _load_model(self):
        """Lazy-load the sentence-transformers model.

        Raises:
            ImportError: If sentence-transformers is not installed.
        """
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            logger.info("Loaded embedding model: %s", self.model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embedding generation. "
                "Install with: pip install sentence-transformers>=2.2.0"
            )

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_document(
        self,
        text: str,
        metadata: ChunkMetadata,
    ) -> list[DocumentChunk]:
        """Split a single document into overlapping chunks with metadata.

        Uses a simple sentence-boundary-aware sliding window approach:
        1. Split text into sentences.
        2. Group sentences into chunks of approximately `chunk_size` tokens.
        3. Overlap adjacent chunks by `chunk_overlap` tokens.

        Each chunk inherits the parent document's metadata (source_file, section,
        circular_date, etc.) and receives a unique chunk_id.

        Args:
            text: Raw document text.
            metadata: Source provenance metadata for the document.

        Returns:
            List of DocumentChunk objects (without embeddings yet).
        """
        if not text.strip():
            return []

        # Simple sentence splitting (handles period, question mark, newlines)
        sentences = re.split(r'(?<=[.!?])\s+|\n\n+', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[DocumentChunk] = []
        current_sentences: list[str] = []
        current_token_count = 0
        chunk_index = 0

        for sentence in sentences:
            # Approximate token count (words ≈ tokens for English)
            sentence_tokens = len(sentence.split())

            if current_token_count + sentence_tokens > self.chunk_size and current_sentences:
                # Emit current chunk
                chunk_text = " ".join(current_sentences)
                chunk_meta = ChunkMetadata(
                    source_file=metadata.source_file,
                    section=metadata.section,
                    chunk_id=f"{metadata.source_file}::chunk_{chunk_index:04d}",
                    document_type=metadata.document_type,
                    circular_date=metadata.circular_date,
                    circular_number=metadata.circular_number,
                    policy_type=metadata.policy_type,
                )
                chunks.append(DocumentChunk(text=chunk_text, metadata=chunk_meta))
                chunk_index += 1

                # Compute overlap: keep last N tokens worth of sentences
                overlap_tokens = 0
                overlap_start = len(current_sentences)
                for j in range(len(current_sentences) - 1, -1, -1):
                    overlap_tokens += len(current_sentences[j].split())
                    if overlap_tokens >= self.chunk_overlap:
                        overlap_start = j
                        break

                current_sentences = current_sentences[overlap_start:]
                current_token_count = sum(len(s.split()) for s in current_sentences)

            current_sentences.append(sentence)
            current_token_count += sentence_tokens

        # Emit final chunk
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunk_meta = ChunkMetadata(
                source_file=metadata.source_file,
                section=metadata.section,
                chunk_id=f"{metadata.source_file}::chunk_{chunk_index:04d}",
                document_type=metadata.document_type,
                circular_date=metadata.circular_date,
                circular_number=metadata.circular_number,
                policy_type=metadata.policy_type,
            )
            chunks.append(DocumentChunk(text=chunk_text, metadata=chunk_meta))

        logger.debug(
            "Chunked '%s' into %d chunks (avg ~%d tokens each).",
            metadata.source_file,
            len(chunks),
            self.chunk_size,
        )

        return chunks

    def chunk_documents(
        self, corpus_dir: str = "retrieval/corpus"
    ) -> list[DocumentChunk]:
        """Chunk all documents in the corpus directory tree.

        Walks the corpus directory, reads all .txt and .md files, determines
        document_type from the subdirectory name, and chunks each document.

        Args:
            corpus_dir: Path to the corpus root directory.

        Returns:
            List of all DocumentChunk objects across the corpus.
        """
        all_chunks: list[DocumentChunk] = []

        # Map subdirectory names to document types
        dir_type_map = {
            "policy_wordings": "policy_wording",
            "benefit_tables": "benefit_table",
            "irdai_circulars": "irdai_circular",
        }

        for root, _dirs, files in os.walk(corpus_dir):
            for filename in sorted(files):
                if not filename.endswith((".txt", ".md")):
                    continue

                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, corpus_dir)

                # Determine document type from parent directory
                parent_dir = os.path.basename(os.path.dirname(filepath))
                doc_type = dir_type_map.get(parent_dir, "policy_wording")

                with open(filepath, "r", encoding="utf-8") as f:
                    text = f.read()

                metadata = ChunkMetadata(
                    source_file=rel_path,
                    document_type=doc_type,
                )

                chunks = self.chunk_document(text, metadata)
                all_chunks.extend(chunks)

        logger.info(
            "Chunked %d documents into %d total chunks from %s.",
            sum(1 for _ in os.walk(corpus_dir) for f in _[2] if f.endswith((".txt", ".md"))),
            len(all_chunks),
            corpus_dir,
        )

        return all_chunks

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> np.ndarray:
        """Compute the embedding for a single text string.

        This is used for query-time embedding in the search pipeline.

        Args:
            text: Input text string.

        Returns:
            Embedding vector as a 1D numpy array of shape (embedding_dim,).
        """
        self._load_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def embed_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        """Compute embeddings for all chunks in-place.

        Batch-encodes all chunk texts for efficiency and sets the `embedding`
        field on each DocumentChunk.

        Args:
            chunks: List of DocumentChunk objects to embed.

        Returns:
            The same list of chunks with `embedding` fields populated.
        """
        if not chunks:
            return chunks

        self._load_model()

        texts = [chunk.text for chunk in chunks]
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=True,
            batch_size=32,
        )

        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb.astype(np.float32)

        logger.info("Embedded %d chunks (dim=%d).", len(chunks), self.embedding_dim)

        return chunks
