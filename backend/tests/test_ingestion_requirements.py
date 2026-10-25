import hashlib
import json

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import datasets
from app.datasets import _counterparties, _flag, _number, _workers
from app.schemas import Company
from app.sources.bank_pdf import ingest_bank_pdfs
from app.sources.feed import MAX_FEED_BYTES, fetch_rss, parse_rss


def make_pdf(path, texts):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=600, height=800)
        if not text:
            continue
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 30 700 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = content
    writer.write(path)


@pytest.mark.parametrize("value", ["", "unknown", "nan", "NaN", "null", "-1", "2", "inf", "Infinity", "н/д"])
def test_unknown_flags_do_not_become_false(value):
    assert _flag(value) is None


@pytest.mark.parametrize(("value", "expected"), [("0", False), ("0,0", False), (" false ", False), ("нет", False), ("1.0", True), ("Да", True)])
def test_explicit_boolean_values(value, expected):
    assert _flag(value) is expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-inf", "unknown", ""])
def test_non_finite_numbers_are_unknown(value):
    assert _number(value) is None


def test_numbers_preserve_precision_and_localized_separator():
    assert _number("12\u00a0345,0") == 12345
    assert _number("9007199254740993") == 9007199254740993


def test_counterparty_shares_use_directional_payment_totals(monkeypatch):
    rows = [
        {"BENEFICIARY": "A", "PAYER": "B", "PAY_AMT": "200", "PAY_CNT": "1"},
        {"BENEFICIARY": "A", "PAYER": "C", "PAY_AMT": "300", "PAY_CNT": "2"},
        {"BENEFICIARY": "D", "PAYER": "A", "PAY_AMT": "70", "PAY_CNT": "1"},
        {"BENEFICIARY": "E", "PAYER": "A", "PAY_AMT": "30", "PAY_CNT": "1"},
    ]
    monkeypatch.setattr(datasets, "load_pay_index", lambda: {"A": rows})
    counterparties = {row["synthetic_u"]: row for row in _counterparties("A", 10000, {})}
    assert counterparties["B"]["share_of_incoming"] == .4
    assert counterparties["D"]["share_of_outgoing"] == .7
    assert all("share_of_costs" not in row and "share_of_revenue" not in row for row in counterparties.values())
    assert _counterparties("A", None, {}) == _counterparties("A", 10000, {})


def test_missing_payment_does_not_create_precise_share(monkeypatch):
    rows = [
        {"BENEFICIARY": "A", "PAYER": "B", "PAY_AMT": "200", "PAY_CNT": "1"},
        {"BENEFICIARY": "A", "PAYER": "C", "PAY_AMT": "NaN", "PAY_CNT": "2"},
    ]
    monkeypatch.setattr(datasets, "load_pay_index", lambda: {"A": rows})
    assert all("share_of_incoming" not in row for row in _counterparties("A", 10000, {}))


def test_market_share_is_explicitly_unknown():
    company = Company(id="A", name="A").model_dump()
    assert company["market_share"] is None
    assert company["market_share_status"] == "unknown"


def test_self_transfers_are_not_buyers_or_part_of_counterparty_share(monkeypatch):
    rows = [
        {"BENEFICIARY": "A", "PAYER": "A", "PAY_AMT": "9000", "PAY_CNT": "1"},
        {"BENEFICIARY": "A", "PAYER": "B", "PAY_AMT": "100", "PAY_CNT": "1"},
    ]
    monkeypatch.setattr(datasets, 'load_pay_index', lambda: {'A': rows})
    result = _counterparties('A', None, {})
    assert len(result) == 1
    assert result[0]['synthetic_u'] == 'B'
    assert result[0]['share_of_incoming'] == 1


def test_headcount_ranges_are_not_exact_numbers():
    assert _workers('Более 251') is None
    assert _workers('101-250') is None
    assert _workers('125') == 125


def test_pdf_import_has_exact_page_citations_and_stable_ids(tmp_path):
    directory = tmp_path / "bank_pdfs"
    directory.mkdir()
    path = directory / "ALFA-consumption.pdf"
    make_pdf(path, ["Source quotation from the first page.", "Second page source quotation."])
    (tmp_path / "documents.json").write_text(json.dumps([{
        "id": "bank-consumption", "title": "Consumption research", "topics": ["retail_demand"],
        "text": "Invented handwritten content must never be indexed.",
    }]), encoding="utf-8")
    result = ingest_bank_pdfs(directory)
    assert result == ingest_bank_pdfs(directory)
    assert result[0]["id"] == "bank-consumption"
    assert result[0]["text"] == "Source quotation from the first page."
    assert result[0]["title"] == "Consumption research"
    assert result[1]["source_url"].endswith("ALFA-consumption.pdf#page=2")
    assert result[1]["page_start"] == result[1]["page_end"] == 2
    assert result[1]["extraction_status"] == "text_layer"
    assert len({row["id"] for row in result}) == len(result)
    assert all("Invented" not in row["text"] for row in result)


def test_scan_requires_ocr_and_accepts_only_matching_sidecar(tmp_path):
    path = tmp_path / "scan.pdf"
    make_pdf(path, [None, None])
    empty = ingest_bank_pdfs(tmp_path)
    assert empty[0]["text"] == ""
    assert empty[0]["extraction_status"] == "ocr_required"
    sidecar = path.with_name(path.name + ".ocr.json")
    data = {"source_sha256": "wrong", "engine": "test", "pages": [{"page": 2, "text": "Read from page two."}]}
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    assert ingest_bank_pdfs(tmp_path)[0]["extraction_status"] == "ocr_required"
    data["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    result = ingest_bank_pdfs(tmp_path)
    assert result[0]["extraction_status"] == "ocr"
    assert result[0]["text"] == "Read from page two."
    assert result[0]["page_start"] == 2
    assert result[0]["extracted_pages"] == 1
    assert result[0]["page_count"] == 2


def test_invalid_pdf_is_reported_without_fake_research(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"not a PDF")
    result = ingest_bank_pdfs(tmp_path)
    assert result[0]["extraction_status"] == "extraction_error"
    assert result[0]["text"] == ""


def rss(entries):
    return "<rss><channel><title>Source</title>" + "".join(
        f"<item><title>{title}</title><link>https://example.com/{slug}</link><pubDate>2026-10-16</pubDate></item>"
        for title, slug in entries) + "</channel></rss>"


def test_news_ids_are_stable_when_reordered_and_do_not_collide_across_feeds():
    first = parse_rss(rss([("Article A", "a"), ("Article B", "b")]))
    reversed_items = parse_rss(rss([("Article B", "b"), ("Article A", "a")]))
    assert first[0]["id"] == reversed_items[1]["id"]
    assert first[1]["id"] == reversed_items[0]["id"]
    assert parse_rss(rss([("Article A", "a")]))[0]["id"] != parse_rss(rss([("Article B", "b")]))[0]["id"]
    assert len(parse_rss(rss([("Article A", "a"), ("Article A", "a")]))) == 1


def test_atom_dates_source_name_and_safe_links():
    payload = '''<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom source</title>
    <entry><title>Article</title><updated>2026-10-16T12:30:00Z</updated>
    <link rel="alternate" href="/article"/><summary>&lt;p&gt;Source &amp;amp; detail&lt;/p&gt;</summary></entry>
    <entry><title>Bad date</title><updated>2026-99-99</updated></entry>
    <entry><title>Unsafe link</title><published>2026-10-16</published><link href="javascript:alert(1)"/></entry></feed>'''
    result = parse_rss(payload, "https://example.com/feed")
    assert len(result) == 2
    assert result[0]["source_url"] == "https://example.com/article"
    assert result[0]["source_name"] == "Atom source"
    assert result[0]["summary"] == "Source & detail"
    assert result[1]["source_url"] is None


def test_feed_size_and_entity_limits():
    with pytest.raises(ValueError, match="size"):
        parse_rss(b"x" * (MAX_FEED_BYTES + 1))
    with pytest.raises(ValueError, match="entity"):
        parse_rss('<!DOCTYPE rss [<!ENTITY a "value">]><rss/>')


def test_fetch_rejects_overlong_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, length):
            assert length == MAX_FEED_BYTES + 1
            return b"x" * length
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="size"):
        fetch_rss("https://example.com/feed")
