"""PDF parser — extracts text + metadata from an AI textbook PDF.

Reads a PDF with PyMuPDF (fitz), returns a list of page dicts:
  [{page: int, text: str, has_tables: bool}]

Tables are flagged via `page.find_tables()` when available; flagged pages
get a `has_tables=True` marker so the chunker can keep table headers with
content rows. OCR is out of MVP scope — scanned-only pages come back
with empty text and are skipped by the chunker (caller should log a
warning; for your viva, note them as a limitations item).
"""
from __future__ import annotations

import os

import fitz  # PyMuPDF


def parse_pdf(path: str) -> list[dict]:
    """Parse a PDF into per-page text records."""
    doc = fitz.open(path)
    pages: list[dict] = []
    for page in doc:
        text = page.get_text("text").strip()
        if not text:
            continue  # likely a scanned page with no text layer; log + skip
        has_tables = False
        try:
            has_tables = len(page.find_tables().tables) > 0
        except Exception:
            has_tables = False
        pages.append({
            "page": page.number + 1,  # 1-based for citations
            "text": text,
            "has_tables": has_tables,
        })
    return pages


def parse_pdf_to_chunks(path: str) -> list[dict]:
    """Convenience: parse + chunk a single PDF."""
    from ingest.chunk import chunk_pages
    return chunk_pages(parse_pdf(path), source_name=os.path.basename(path))