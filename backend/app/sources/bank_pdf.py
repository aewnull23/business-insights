"""Deterministic, page-addressable ingestion of local bank research PDFs.

Run from backend: python -m app.sources.bank_pdf --output data/bank_documents.json
Scans accept an optional <filename>.ocr.json sidecar generated from the same PDF:
{"source_sha256": "...", "engine": "...", "pages": [{"page": 1, "text": "..."}]}.
A missing text layer is reported explicitly and is never replaced by a summary.
"""

import argparse
import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from pypdf import PdfReader

from app.config import DATA_DIR

LOGGER = logging.getLogger(__name__)
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_OCR_BYTES = 16 * 1024 * 1024
MAX_PAGES = 200
CHUNK_CHARS = 1800

# The existing catalog IDs remain stable for links and stored analyses.
CATALOG_IDS = {
    "ALFA-Macro_Insights-Policy_Rate_11Sep.pdf": "bank-key-rate",
    "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021.pdf": "bank-commodities",
    "ALFA-consumption.pdf": "bank-consumption",
    "ALFA-7M26.pdf": "bank-labor",
    "ALFA-macro_stat1H26.pdf": "bank-gdp",
    "Inflation_tracker_02.pdf": "bank-inflation",
    "Бонд_Бриф_14092026.pdf": "bank-bonds",
    "Gold_digest_August26.pdf": "bank-gold",
    "FI_Strategy_3Q26_22072026.pdf": "bank-tactical-q3",
}


def _clean_text(text: str) -> str:
    # Normalize whitespace only; retain source wording and numerical values.
    return "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()


def _chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    chunks = []
    remaining = _clean_text(text)
    while remaining:
        if len(remaining) <= size:
            chunks.append(remaining)
            break
        boundary = max(remaining.rfind("\n", size // 2, size), remaining.rfind(". ", size // 2, size))
        if boundary < 0:
            boundary = remaining.rfind(" ", size // 2, size)
        if boundary < 0:
            boundary = size
        elif remaining[boundary] == ".":
            boundary += 1
        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    return chunks


def _ocr_pages(path: Path, digest: str, page_count: int) -> dict[int, str]:
    sidecar = path.with_name(path.name + ".ocr.json")
    if not sidecar.exists():
        return {}
    if sidecar.stat().st_size > MAX_OCR_BYTES:
        raise ValueError("OCR sidecar exceeds size limit")
    payload = json.loads(sidecar.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("source_sha256") != digest:
        raise ValueError("OCR sidecar does not match the PDF SHA256")
    records = payload.get("pages")
    if not isinstance(records, list) or len(records) > page_count:
        raise ValueError("Invalid OCR page list")
    pages = {}
    for row in records:
        page = row.get("page") if isinstance(row, dict) else None
        text = row.get("text") if isinstance(row, dict) else None
        if type(page) is not int or not 1 <= page <= page_count or page in pages or not isinstance(text, str):
            raise ValueError("Invalid OCR page or text")
        pages[page] = _clean_text(text)
    return pages


def _catalog(directory: Path) -> dict:
    path = directory.parent / "documents.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return {item["id"]: item for item in payload}


def _topics(text: str) -> list[str]:
    patterns = {
        "key_rate": r"ключев\w* ставк|инфляц|policy rate",
        "metal_prices": r"металлург|сталь|прокат|steel|цен[^.\n]{0,35}стали",
        "retail_demand": r"потреблен|рознич|consumption",
        "labor_it": r"безработиц|заработн|рынок труда",
        "group_treasury": r"облигац|ликвидност|bond",
    }
    return [topic for topic, pattern in patterns.items() if re.search(pattern, text, re.IGNORECASE)]


def _publication_date(text: str) -> str | None:
    months = {name: index for index, name in enumerate(
        ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
         'августа', 'сентября', 'октября', 'ноября', 'декабря'), 1)}
    # A standalone date on the cover is metadata; dates inside prose are events.
    match = re.search(r'^\s*(\d{1,2})\s+(' + '|'.join(months) + r')\s+(20\d{2})(?:\s*г(?:ода|\.)?)?\s*$', text, re.M | re.I)
    if match:
        try:
            return date(int(match[3]), months[match[2].lower()], int(match[1])).isoformat()
        except ValueError:
            pass
    return None


def ingest_bank_pdfs(directory: Path = DATA_DIR / "bank_pdfs") -> list[dict]:
    directory = Path(directory)
    catalog = _catalog(directory)
    documents = []
    for path in sorted(directory.glob("*.pdf"), key=lambda item: item.name.casefold()):
        document_id = CATALOG_IDS.get(path.name) or "bank-pdf-" + hashlib.sha256(path.name.encode()).hexdigest()[:16]
        metadata = catalog.get(document_id) or {}
        base = {
            "id": document_id,
            "document_id": document_id,
            "title": metadata.get("title") or path.stem,
            "origin": "case_packet",
            "is_bank_research": True,
            "source_url": "/bank-pdfs/" + quote(path.name),
            "source_file": path.name,
            "topics": metadata.get("topics") or [],
            "text": "",
        }
        try:
            if path.stat().st_size > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds size limit")
            base["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF cannot be indexed")
            page_count = len(reader.pages)
            base["page_count"] = page_count
            if page_count > MAX_PAGES:
                raise ValueError("PDF exceeds page limit")
            sidecar_error = None
            try:
                ocr = _ocr_pages(path, base["source_sha256"], page_count)
            except (ValueError, TypeError, OSError) as exc:
                ocr = {}
                sidecar_error = str(exc)
                LOGGER.warning("Ignored OCR for %s: %s", path.name, exc)
            extracted = []
            for page_number, page in enumerate(reader.pages, 1):
                text = _clean_text(page.extract_text() or "")
                status = "text_layer"
                if not text:
                    text = ocr.get(page_number, "")
                    status = "ocr"
                if text:
                    extracted.append((page_number, text, status))
            base["extracted_pages"] = len(extracted)
            base["published_at"] = _publication_date(extracted[0][1]) if extracted and extracted[0][0] == 1 else None
            if not extracted:
                documents.append({
                    **base,
                    "extraction_status": "ocr_required",
                    "ingestion_message": "Текст PDF недоступен: требуется OCR. Материал не используется как позиция банка."
                    + (" OCR-файл отклонен: " + sidecar_error if sidecar_error else ""),
                })
                continue
            first = True
            for page_number, text, status in extracted:
                for part, chunk in enumerate(_chunks(text), 1):
                    documents.append({
                        **base,
                        "id": document_id if first else f"{document_id}-p{page_number}-{part}",
                        "source_url": base["source_url"] + f"#page={page_number}",
                        "page_start": page_number,
                        "page_end": page_number,
                        "text": chunk,
                        "topics": list(dict.fromkeys(base["topics"] + _topics(chunk))),
                        "extraction_status": status,
                    })
                    first = False
        except Exception as exc:
            LOGGER.warning("Could not import %s: %s", path.name, exc)
            documents.append({
                **base,
                "extraction_status": "extraction_error",
                "ingestion_message": f"Не удалось извлечь PDF ({type(exc).__name__}). Материал не используется как позиция банка.",
            })
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DATA_DIR / "bank_pdfs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = ingest_bank_pdfs(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(documents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    usable = sum(bool(item["text"]) for item in documents)
    print(f"Imported {usable} text chunks; {len(documents) - usable} PDFs require attention.")


if __name__ == "__main__":
    main()
