"""
Reads every document in data/documents/ (supports .txt and .pdf),
chunks it, and stores chunks in ChromaDB with authority metadata.

Real data pack files expected:
  01_Support_Policy_v3_CURRENT.pdf
  02_Support_Policy_v2_DEPRECATED.pdf
  03_Cancellation_and_Service_Credit_SOP_v4.pdf
  04_Product_Operations_Guide_and_Known_Issues.pdf
  05_Northstar_Logistics_Enterprise_Agreement.pdf
  06_LumenWorks_Service_Agreement.pdf

Mock fallbacks (used when real PDFs are not present):
  policy_v2_current.txt, policy_v1_deprecated.txt, etc.

Run: python -m ingestion.document_ingester
"""

from pathlib import Path
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

import config

# ---------------------------------------------------------------------------
# Authority metadata keyed by filename stem (without extension).
# Covers both real data-pack filenames and our mock fallback filenames.
# ---------------------------------------------------------------------------
DOCUMENT_METADATA: dict[str, dict] = {
    # ── Real data-pack filenames ──────────────────────────────────────────
    "01_Support_Policy_v3_CURRENT": {
        "source_type": "current_policy",
        "authority_level": 70,
        "is_deprecated": False,
        "account_scope": "global",
        "display_name": "Support Policy v3 (Current)",
    },
    "02_Support_Policy_v2_DEPRECATED": {
        "source_type": "deprecated_policy",
        "authority_level": 20,
        "is_deprecated": True,
        "account_scope": "global",
        "display_name": "Support Policy v2 (Deprecated)",
    },
    "03_Cancellation_and_Service_Credit_SOP_v4": {
        "source_type": "current_sop",
        "authority_level": 65,
        "is_deprecated": False,
        "account_scope": "global",
        "display_name": "Cancellation & Service Credit SOP v4 (Current)",
    },
    "04_Product_Operations_Guide_and_Known_Issues": {
        "source_type": "product_guide",
        "authority_level": 60,
        "is_deprecated": False,
        "account_scope": "global",
        "display_name": "Product Operations Guide & Known Issues",
    },
    "05_Northstar_Logistics_Enterprise_Agreement": {
        "source_type": "customer_agreement",
        "authority_level": 100,
        "is_deprecated": False,
        "account_scope": "ACCT-001",           # must match real account_id for ChromaDB filter
        "display_name": "Northstar Logistics Enterprise Agreement",
    },
    "06_LumenWorks_Service_Agreement": {
        "source_type": "customer_agreement",
        "authority_level": 100,
        "is_deprecated": False,
        "account_scope": "ACCT-002",           # must match real account_id for ChromaDB filter
        "display_name": "LumenWorks Service Agreement",
    },

    # ── Mock fallback filenames (used when real PDFs are absent) ──────────
    "policy_v2_current": {
        "source_type": "current_policy",
        "authority_level": 70,
        "is_deprecated": False,
        "account_scope": "global",
        "display_name": "General Policy v2.0 (Current) [MOCK]",
    },
    "policy_v1_deprecated": {
        "source_type": "deprecated_policy",
        "authority_level": 20,
        "is_deprecated": True,
        "account_scope": "global",
        "display_name": "General Policy v1.0 (Deprecated) [MOCK]",
    },
    "sop_v3_current": {
        "source_type": "current_sop",
        "authority_level": 60,
        "is_deprecated": False,
        "account_scope": "global",
        "display_name": "Operations SOP v3.0 (Current) [MOCK]",
    },
    "sop_v1_deprecated": {
        "source_type": "deprecated_sop",
        "authority_level": 15,
        "is_deprecated": True,
        "account_scope": "global",
        "display_name": "Operations SOP v1.5 (Deprecated) [MOCK]",
    },
    "agreement_acme_corp": {
        "source_type": "customer_agreement",
        "authority_level": 100,
        "is_deprecated": False,
        "account_scope": "ACC-001",
        "display_name": "Acme Corp Service Agreement [MOCK]",
    },
    "agreement_globex_ltd": {
        "source_type": "customer_agreement",
        "authority_level": 100,
        "is_deprecated": False,
        "account_scope": "ACC-002",
        "display_name": "Globex Ltd Service Agreement [MOCK]",
    },
}

# Authority weights used by document_search.py for re-ranking.
# Also kept in config.py — duplicated here for single-file reference.
_AUTHORITY_WEIGHTS: dict[str, float] = {
    "customer_agreement": 3.0,
    "current_policy":     2.0,
    "current_sop":        1.8,
    "product_guide":      1.6,
    "deprecated_policy":  0.4,
    "deprecated_sop":     0.3,
}


def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_pdf(path: Path) -> str:
    """Extract all text from a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required to read PDF files. "
            "Install it: pip install pdfplumber"
        )
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".txt":
        return _read_txt(path)
    raise ValueError(f"Unsupported document format: {suffix}")


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """Word-level chunking with overlap."""
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return [c for c in chunks if len(c.split()) > 10]   # drop tiny trailing chunks


def _get_collection(reset: bool) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    embed_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    if reset:
        try:
            client.delete_collection(config.COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_documents(reset: bool = False) -> None:
    collection = _get_collection(reset)

    doc_files = sorted(
        f for f in config.DOCS_DIR.iterdir()
        if f.suffix.lower() in (".txt", ".pdf")
    )
    if not doc_files:
        raise FileNotFoundError(
            f"No documents found in {config.DOCS_DIR}\n"
            "Place the real data-pack PDFs there, or use the mock .txt files."
        )

    total_chunks = 0
    for doc_path in doc_files:
        stem = doc_path.stem
        meta_template = DOCUMENT_METADATA.get(stem)
        if meta_template is None:
            print(f"  [skip] {doc_path.name} — no metadata mapping (add to DOCUMENT_METADATA)")
            continue

        text = _read_document(doc_path)
        chunks = _chunk_text(text)

        ids, documents, metadatas = [], [], []
        for i, chunk in enumerate(chunks):
            ids.append(f"{stem}__chunk_{i}")
            documents.append(chunk)
            metadatas.append({
                "source_name":     stem,
                "display_name":    meta_template["display_name"],
                "source_type":     meta_template["source_type"],
                "authority_level": meta_template["authority_level"],
                "is_deprecated":   str(meta_template["is_deprecated"]).lower(),
                "account_scope":   meta_template["account_scope"],
                "chunk_index":     i,
            })

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        total_chunks += len(chunks)
        print(f"  [ok] {doc_path.name} → {len(chunks)} chunks "
              f"(authority: {meta_template['authority_level']})")

    print(f"\nIngestion complete — {total_chunks} chunks in '{config.COLLECTION_NAME}'.")
    _print_authority_weights()


def _print_authority_weights() -> None:
    print("\nAuthority weight reference:")
    for source_type, weight in sorted(_AUTHORITY_WEIGHTS.items(), key=lambda x: -x[1]):
        print(f"  {source_type:<25} {weight}×")


if __name__ == "__main__":
    print("Ingesting documents...")
    ingest_documents(reset=True)
