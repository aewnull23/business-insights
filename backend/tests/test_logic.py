from app.datasets import FID_COLUMNS, PAY_COLUMNS, UID_COLUMNS, load_documents, load_fid_rows, load_pay_rows, load_uid_rows
from app.providers.llm import llm_status, model_allowed
from app.services.analysis import build_analysis
from app.services.followup import answer_question
from app.services.impact import evaluate, score_of
from app.services.news_pipeline import prepare_item
from app.services.profile import excluded_companies, get_company, list_public, profile_view
from app.services.quality import check, narrative_is_grounded, repair
from app.services.ranking import rank_for, rank_news
from app.services.retrieval import search_documents
from app.services.users import get_user
from app.sources.feed import collect_news, parse_rss

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example</title>
<item>
  <title>Ключевая ставка в ленте</title>
  <pubDate>Thu, 16 Oct 2026 08:00:00 GMT</pubDate>
  <link>https://example.com/rate</link>
  <description>Банк России обсуждает ключевую ставку на ближайшем заседании.</description>
</item>
</channel></rss>
"""


def _news(news_id):
    items, _, _ = collect_news()
    return next(item for item in items if item["id"] == news_id)


def _ids(company_id, user=None):
    company = get_company(company_id)
    items, _, _ = collect_news()
    ranked = rank_for(company, items, user) if user else rank_news(company, items)
    return [row["news"]["id"] for row in ranked]


def _text(view):
    parts = []
    for section in view["sections"]:
        if section.get("empty"):
            parts.append(section["empty"])
        for item in section["items"]:
            parts.append(item["text"])
    return "\n".join(parts)


def _view(company_id, news_id, user=None):
    company = get_company(company_id)
    news = _news(news_id)
    documents = search_documents(news, list(load_documents()))
    return build_analysis(company, news, documents, user)


def _blank():
    return {
        "fired_rule_ids": [],
        "source_facts": [],
        "confirmed_facts": [],
        "attributes": [],
        "why": [],
        "consequences": [],
        "risks": [],
        "opportunities": [],
        "actions": [],
        "unknowns": [],
        "documents": [],
        "bank": {"found": False, "message": "не найден", "items": []},
    }


def test_case_csv_schema():
    assert load_uid_rows()
    assert set(load_uid_rows()[0]) == set(UID_COLUMNS)
    assert set(load_fid_rows()[0]) == set(FID_COLUMNS)
    assert set(load_pay_rows()[0]) == set(PAY_COLUMNS)
    assert all(item["is_bank_research"] for item in load_documents())


def test_large_business_threshold():
    workspace = {item["id"] for item in list_public()}
    assert "u_200890" in workspace
    assert "u_1595" in workspace
    assert "u_3263" in workspace
    assert "u_44792" in workspace
    assert "u_67" not in workspace
    assert "u_177693" not in workspace
    assert len(excluded_companies()) <= 12
    metal = get_company("u_200890")
    shop = get_company("u_1595")
    small = get_company("u_67")
    agro = get_company("u_177693")
    assert metal["revenue_rub"] > 15_000_000_000
    assert shop["revenue_rub"] > 15_000_000_000
    assert small["revenue_rub"] < 15_000_000_000
    assert agro["revenue_rub"] < 15_000_000_000
    assert metal["industry"] == "Торговля металлами"
    assert shop["industry"] == "Розничная торговля"


def test_duplicate_news_removed():
    items, dropped, _ = collect_news()
    assert "n-metal-dup" not in {item["id"] for item in items}
    assert {"dropped_id": "n-metal-dup", "kept_id": "n-metal"} in dropped


def test_ranking_depends_on_company():
    metal = _ids("u_200890")
    shop = _ids("u_1595")
    agro = _ids("u_177693")
    soft = _ids("u_44792")
    logistics = _ids("u_3263")
    small = _ids("u_67")

    assert metal[0] == "n-metal"
    assert shop[0] == "n-retail"
    assert agro[0] == "n-grain"
    assert soft[0] == "n-labor"
    assert logistics[0] == "n-fuel"
    assert "n-group" in small

    assert "n-metal" not in shop
    assert "n-retail" not in metal
    assert "n-sport" not in metal
    assert "n-sport" not in shop
    assert "n-tax" in metal and "n-tax" in shop and "n-tax" in soft
    assert "n-tax" not in agro
    assert "n-tax" not in small

    story = _news("n-metal")
    assert score_of(evaluate(get_company("u_200890"), story)) > score_of(evaluate(get_company("u_1595"), story))


def test_role_changes_ranking_for_same_company():
    ceo = _ids("u_200890", get_user("kama-ceo"))
    treasury = _ids("u_200890", get_user("kama-treasury"))
    accountant = _ids("u_200890", get_user("kama-accountant"))
    shop_treasury = _ids("u_1595", get_user("shop-treasury"))
    assert ceo[0] == "n-metal"
    assert treasury[0] == "n-group"
    assert accountant[0] == "n-tax"
    assert shop_treasury[0] == "n-rate"


def test_sparse_profile_does_not_invent_revenue():
    company = get_company("u_67")
    view = profile_view(company)
    assert "платежи" in view["core_gaps"]
    assert "банковские продукты" in view["core_gaps"]
    revenue = next(row for row in view["rows"] if row["label"] == "Выручка")
    assert revenue["value"] == "0,1 млн ₽"
    assert company["revenue_rub"] == 136493
    text = _text(_view("u_67", "n-group"))
    assert "59,6" not in text
    assert "18,5" not in text


def test_kama_metal_separates_facts_bank_and_inference():
    view = _view("u_200890", "n-metal")
    confirmed = next(section for section in view["sections"] if section["id"] == "confirmed")
    source = next(section for section in view["sections"] if section["id"] == "source_facts")
    bank = next(section for section in view["sections"] if section["id"] == "bank")
    products = next(section for section in view["sections"] if section["id"] == "products")
    assert confirmed["items"] == []
    assert source["items"]
    assert all(item["kind"] == "source" for item in source["items"])
    assert view["bank_found"] is True
    assert bank["items"]
    assert any("стал" in item["text"].lower() or "металл" in item["text"].lower() or "товар" in item["text"].lower() for item in bank["items"])
    assert "59,6" in _text(view)
    assert view["quality"]["revised"] is False
    assert products["id"] == "products"


def test_rate_uses_bank_interpretation_and_debt_gap():
    rate = _view("u_1595", "n-rate")
    assert rate["quality"]["revised"] is True
    assert any("структуре долга" in item["text"] for item in next(section for section in rate["sections"] if section["id"] == "unknowns")["items"])
    bank = next(section for section in rate["sections"] if section["id"] == "bank")
    assert rate["bank_found"] is True
    assert any("14%" in item["text"] or "14,0%" in item["text"] for item in bank["items"])
    products = next(section for section in rate["sections"] if section["id"] == "products")
    assert products["items"]
    fuel_docs = next(section for section in _view("u_3263", "n-fuel")["sections"] if section["id"] == "documents")
    assert fuel_docs["items"] == []


def test_quality_repairs_unsourced_certainty_and_false_confirmation():
    draft = _blank()
    draft["consequences"] = [{"text": "Выручка упадет.", "kind": "ai", "basis": []}]
    draft["risks"] = [{"text": "Это гарантированно обрушит маржу.", "kind": "ai", "basis": ["rule:x"]}]
    draft["confirmed_facts"] = [{"text": "Учебная цифра.", "kind": "confirmed", "origin": "demonstration", "basis": ["fact:1"]}]
    issues = check(draft)
    assert "unsourced_claim" in issues
    assert "certainty_language" in issues
    assert "demo_marked_confirmed" in issues
    fixed = repair(draft, issues)
    assert fixed["consequences"] == []
    assert "гарантированно" not in fixed["risks"][0]["text"]
    assert fixed["confirmed_facts"] == []
    assert fixed["source_facts"][0]["kind"] == "source"
    assert narrative_is_grounded("Эффект составит 77 млрд", "выручка 18,5 млрд", False) is False
    assert narrative_is_grounded("Выручка 18,5 млрд уже есть в профиле", "выручка 18,5 млрд", False) is True


def test_followup_does_not_invent_missing_facts():
    company = get_company("u_200890")
    news = _news("n-metal")
    view = _view("u_200890", "n-metal")
    owner = answer_question(company, news, view, "Кто бенефициар компании?")
    assert owner["kind"] == "profile"
    assert "обезличен" in owner["answer"].lower()
    persons = company.get("related_persons") or []
    if persons:
        assert persons[0]["synthetic_f"] in owner["answer"]
    revenue = answer_question(company, news, view, "Какая выручка у компании?")
    assert "59,6" in revenue["answer"]
    assert revenue["kind"] == "profile"
    alfa = answer_question(company, news, view, "Что говорит аналитика Альфа-Банка?")
    assert alfa["kind"] == "bank"
    facts = answer_question(company, news, view, "Что здесь является фактом?")
    assert "Подтвержденных внешней проверкой фактов нет" in facts["answer"]
    soft = get_company("u_44792")
    soft_view = _view("u_44792", "n-labor")
    credit = answer_question(soft, _news("n-labor"), soft_view, "Как это влияет на кредитную линию?")
    assert "нет кредитной линии" in credit["answer"]
    small = answer_question(get_company("u_67"), _news("n-group"), _view("u_67", "n-group"), "Какая выручка у компании?")
    assert "0,1 млн" in small["answer"]
    assert "59,6" not in small["answer"]


def test_rss_items_stay_unverified():
    parsed = parse_rss(RSS)
    prepared = prepare_item(parsed[0])
    assert prepared["origin"] == "rss"
    assert "key_rate" in prepared["topics"]
    assert prepared["facts"]
    assert all(fact["verification"] == "unverified" for fact in prepared["facts"])
    assert prepared["published_at"] == "2026-10-16"


def test_llm_allowlist_blocks_unknown_models():
    assert model_allowed("Gemma 4 26B A4B") is True
    assert model_allowed("gpt-4o") is False
    assert llm_status()["mode"] == "demo"
