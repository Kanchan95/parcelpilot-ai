"""
Tool A — Document Search (RAG)

Retrieves relevant chunks from the vector store and re-ranks them by a combined
score of semantic relevance × source authority weight. Detects and surfaces
conflicts when two chunks on the same topic disagree across authority levels.
"""

from dataclasses import dataclass, field
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

import config

# Lazy-loaded singletons — initialised on first call to search().
_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None
_embed_fn: SentenceTransformerEmbeddingFunction | None = None


def _get_collection() -> chromadb.Collection:
    global _client, _collection, _embed_fn
    if _collection is None:
        _embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        _collection = _client.get_collection(
            name=config.COLLECTION_NAME,
            embedding_function=_embed_fn,
        )
    return _collection


@dataclass
class DocumentChunk:
    chunk_id: str
    content: str
    display_name: str
    source_type: str
    authority_level: int
    is_deprecated: bool
    account_scope: str
    relevance_score: float
    weighted_score: float


@dataclass
class SearchResult:
    chunks: list[DocumentChunk] = field(default_factory=list)
    conflicts_detected: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "results": [
                {
                    "source": c.display_name,
                    "source_type": c.source_type,
                    "is_deprecated": c.is_deprecated,
                    "authority_level": c.authority_level,
                    "content": c.content,
                    "relevance_score": round(c.relevance_score, 3),
                }
                for c in self.chunks
            ],
            "conflicts": self.conflicts_detected,
            "total_results": len(self.chunks),
        }


def _build_where_filter(account_id: str) -> dict:
    """
    Returns a ChromaDB $or filter that retrieves:
      - All globally-scoped documents (policies, SOPs)
      - Only the specific customer agreement for this account (if any)
    Internal agents (account_id == "INTERNAL") get everything.
    """
    if account_id == "INTERNAL":
        return {}  # no filter — internal agents see all documents
    return {
        "$or": [
            {"account_scope": {"$eq": "global"}},
            {"account_scope": {"$eq": account_id}},
        ]
    }


def _detect_conflicts(chunks: list[DocumentChunk]) -> list[dict]:
    """
    Detects when a current and deprecated source appear together on the same topic.
    Returns a list of conflict descriptions.
    """
    conflicts = []
    current = [c for c in chunks if not c.is_deprecated]
    deprecated = [c for c in chunks if c.is_deprecated]
    if current and deprecated:
        conflicts.append({
            "type": "version_conflict",
            "message": (
                f"Found content from both current and deprecated sources. "
                f"Trusting: {current[0].display_name}. "
                f"Deprecated source (lower authority): {deprecated[0].display_name}."
            ),
            "trusted_source": current[0].display_name,
            "deprecated_source": deprecated[0].display_name,
        })
    # Detect agreement overriding general policy
    agreements = [c for c in chunks if c.source_type == "customer_agreement"]
    policies = [c for c in chunks if c.source_type in ("current_policy", "deprecated_policy")]
    if agreements and policies:
        conflicts.append({
            "type": "agreement_override",
            "message": (
                f"Customer-specific agreement ({agreements[0].display_name}) takes precedence "
                f"over general policy ({policies[0].display_name}) for this account."
            ),
            "trusted_source": agreements[0].display_name,
            "overridden_source": policies[0].display_name,
        })
    return conflicts


def search(query: str, account_id: str) -> dict:
    """
    Main entry point called by the orchestrator (Tool A).

    1. Queries ChromaDB for top-K candidates scoped to the account.
    2. Re-ranks by (cosine_similarity × authority_weight).
    3. Detects conflicts between high- and low-authority sources.
    4. Returns a structured dict the LLM can reason over.
    """
    collection = _get_collection()
    where = _build_where_filter(account_id)

    query_params: dict = {
        "query_texts": [query],
        "n_results": config.TOP_K_RETRIEVAL,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        query_params["where"] = where

    results = collection.query(**query_params)

    if not results["ids"] or not results["ids"][0]:
        return SearchResult().to_dict()

    chunks: list[DocumentChunk] = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        relevance = 1.0 - distance  # cosine distance → similarity
        weight = config.AUTHORITY_WEIGHTS.get(meta["source_type"], 1.0)
        chunks.append(
            DocumentChunk(
                chunk_id=meta.get("source_name", ""),
                content=doc,
                display_name=meta["display_name"],
                source_type=meta["source_type"],
                authority_level=int(meta["authority_level"]),
                is_deprecated=(meta["is_deprecated"] == "true"),
                account_scope=meta["account_scope"],
                relevance_score=relevance,
                weighted_score=relevance * weight,
            )
        )

    # Sort by weighted score descending
    chunks.sort(key=lambda c: c.weighted_score, reverse=True)
    top_chunks = chunks[: config.TOP_K_RERANKED]

    conflicts = _detect_conflicts(top_chunks)
    return SearchResult(chunks=top_chunks, conflicts_detected=conflicts).to_dict()
