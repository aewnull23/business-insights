import copy

import pytest

from app.services import agent as agent_module
from app.services import analysis as analysis_module
from app.services.agent import BriefingAgent, Forbidden, _version
from app.services.analysis import build_analysis
from app.services.profile import get_company
from app.services.quality import narrative_is_grounded
from app.services.retrieval import search_documents
from app.sources.feed import collect_news
from app.storage.store import get_store


def news_item():
    return {
        "id": "new-rate", "title": "Ключевая ставка и стоимость кредита",
        "published_at": "2026-10-22", "summary": "Стоимость кредита зависит от ключевой ставки.",
        "topics": ["key_rate"], "origin": "user_supplied", "facts": [],
    }


def bank_document(**overrides):
    return {
        "id": "research", "title": "Исследование денежной политики", "is_bank_research": True,
        "origin": "case_packet", "topics": ["key_rate"], "extraction_status": "ocr",
        "source_url": "/bank-pdfs/research.pdf#page=2", "source_file": "research.pdf",
        "page_start": 2, "page_end": 2,
        "text": "Ключевая ставка влияет на стоимость кредита. Условия пересмотра зависят от договора.",
        **overrides,
    }


def test_real_retrieval_retry_searches_text_without_topic_labels(monkeypatch):
    document = bank_document(topics=[])
    monkeypatch.setattr(agent_module, "load_documents", lambda: (document,))
    view = BriefingAgent().preview("u_1595", news_item(), "shop-treasury")
    attempts = view["context"]["retrieval_attempts"]
    assert attempts[0]["strategy"] == "topics" and not attempts[0]["document_ids"]
    assert attempts[1]["strategy"] == "lexical" and attempts[1]["document_ids"] == ["research"]
    assert view["bank_found"] is True
    assert any(step["title"] == "Поиск уточнен" for step in view["trace"])
    assert any(step.get("condition") == "no_bank_hits" for step in view["plan"])


def test_retry_does_not_substitute_unrelated_bank_document(monkeypatch):
    document = bank_document(topics=[], text="Итоги футбольного турнира. Команды сыграли решающий матч.")
    monkeypatch.setattr(agent_module, "load_documents", lambda: (document,))
    view = BriefingAgent().preview("u_1595", news_item(), "shop-treasury")
    assert view["bank_found"] is False
    assert len(view["context"]["retrieval_attempts"]) == 2
    assert not view["context"]["document_ids"]


def test_source_url_page_and_bank_context_survive_analysis():
    news = news_item()
    documents = search_documents(news, [bank_document()])
    view = build_analysis(get_company("u_1595"), news, documents)
    source = next(item for item in view["sources"] if item["id"] == "doc:research")
    assert source["url"] == "/bank-pdfs/research.pdf#page=2"
    assert source["page_start"] == 2
    actions = next(section for section in view["sections"] if section["id"] == "actions")["items"]
    bank_actions = [item for item in actions if "doc:research" in item["basis"]]
    assert bank_actions and bank_actions[0]["kind"] == "ai"
    assert bank_actions[0]["source_excerpt"] == bank_document()["text"]
    assert "profile:u_1595" in bank_actions[0]["basis"]
    assert "news:new-rate" in bank_actions[0]["basis"]
    assert "вывод AI" in bank_actions[0]["note"]


@pytest.mark.parametrize("status", ["ocr_required", "extraction_error", "metadata_only"])
def test_unreadable_pdf_is_not_bank_evidence(status):
    doc = bank_document(extraction_status=status)
    assert search_documents(news_item(), [doc]) == []
    assert search_documents(news_item(), [doc], strategy="lexical") == []


def test_quality_result_is_not_always_success(monkeypatch):
    monkeypatch.setattr(analysis_module, "check", lambda draft: ["unresolved_evidence"])
    view = build_analysis(get_company("u_1595"), news_item(), [])
    assert view["quality"]["passed"] is False
    assert view["quality"]["issues"] == ["unresolved_evidence"]


def test_preview_does_not_persist_feed_or_cached_analysis(monkeypatch):
    monkeypatch.setattr(agent_module, "load_documents", lambda: ())
    before_ids = {item["id"] for item in collect_news()[0]}
    view = BriefingAgent().preview("u_1595", news_item(), "shop-treasury")
    assert view["transient"] is True
    assert view["origin"] == "user_supplied"
    confirmed = next(section for section in view["sections"] if section["id"] == "confirmed")
    assert confirmed["items"] == []
    assert get_store().metrics()["analyses"] == 0
    assert get_store().metrics()["runs"] == 0
    assert {item["id"] for item in collect_news()[0]} == before_ids
    with pytest.raises(Forbidden):
        BriefingAgent().preview("u_1595", news_item(), "kama-ceo")


def test_cache_recomputes_when_news_content_changes(monkeypatch):
    current = news_item()
    monkeypatch.setattr(agent_module, "_find_news", lambda news_id: current)
    monkeypatch.setattr(agent_module, "load_documents", lambda: ())
    agent = BriefingAgent()
    first = agent.analyze("u_1595", current["id"], "shop-treasury")
    assert agent.analyze("u_1595", current["id"], "shop-treasury") == first
    current["title"] = "Другие условия кредита при изменении ставки"
    second = agent.analyze("u_1595", current["id"], "shop-treasury")
    assert second["title"] == current["title"]
    assert first["context"]["fingerprint"] != second["context"]["fingerprint"]


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4])
def test_cache_fingerprint_includes_all_evidence_and_model(index):
    args = [{"id": "u", "role": "CEO"}, {"id": "c", "revenue_rub": 1}, news_item(),
            [bank_document()], {"mode": "demo", "model": None}]
    original = _version(*args)
    changed = copy.deepcopy(args)
    if index == 3:
        changed[index][0]["text"] += " Новый факт."
    else:
        changed[index]["role" if index == 0 else "revenue_rub" if index == 1 else "title" if index == 2 else "model"] = "changed"
    assert _version(*changed) != original


def test_model_guard_rejects_numeric_substrings_and_certainty():
    assert not narrative_is_grounded("Стоимость составит 14 млрд", "Стоимость 140 млрд", False)
    assert not narrative_is_grounded("Маржа гарантированно вырастет", "Маржа может вырасти", False)
    assert not narrative_is_grounded("Альфа Банк прогнозирует рост", "Рост возможен", False)
    assert narrative_is_grounded("Выручка 18,5 млрд", "Выручка 18.5 млрд", False)


def test_research_dates_do_not_masquerade_as_current_bank_view():
    old = bank_document(published_at='2021-04-15')
    future = bank_document(id='future', published_at='2027-01-01')
    docs = search_documents(news_item(), [old, future])
    assert len(docs) == 1 and docs[0]['historical']
    view = build_analysis(get_company('u_1595'), news_item(), docs)
    bank = next(section for section in view['sections'] if section['id'] == 'bank')
    assert 'Исторический' in bank['items'][0]['note']
    actions = next(section for section in view['sections'] if section['id'] == 'actions')['items']
    assert not any('doc:research' in action['basis'] for action in actions)


def test_us_rate_excerpt_is_not_russian_rate_evidence():
    doc = bank_document(text='Ставка ФРС не менялась. Ожидания следующего шага ФРС влияют на стоимость кредита в США.')
    assert search_documents(news_item(), [doc]) == []


def test_research_chunks_are_not_independent_sources():
    first = bank_document(id='p1', document_id='same-report')
    second = bank_document(id='p2', document_id='same-report')
    assert len(search_documents(news_item(), [first, second])) == 1


def test_legal_disclaimer_is_not_a_bank_market_assessment():
    doc = bank_document(text='Ключевая ставка и стоимость кредита. Только для информационных целей. Не является инвестиционной рекомендацией. Копирование запрещено.')
    assert search_documents(news_item(), [doc]) == []


def test_retail_company_does_not_invent_food_business():
    news = {'id': 'retail-new', 'title': 'Растет оборот розницы', 'summary': 'Оборот розничной торговли вырос.',
            'published_at': '2026-10-22', 'topics': ['retail_demand'], 'facts': []}
    company = get_company('u_1595')
    assert 'одеждой' in company['okved_name']
    view = build_analysis(company, news, [])
    assert 'продовольственная розница' not in str(view)


def test_new_rate_news_extracts_only_explicit_decisions_and_keeps_decimals():
    from app.services.news_pipeline import prepare_item
    news = news_item()
    news['title'] = 'Банк России снизил ключевую ставку'
    news['summary'] = 'Банк России снизил ключевую ставку до 13.5%. Новые условия вступают в силу завтра.'
    result = prepare_item(news)
    assert result['signals']['key_rate'] == 'cut'
    assert '13.5%' in result['facts'][0]['text']
    news['title'] = 'Прогноз изменения ставки'
    news['summary'] = 'Банк России может снизить ключевую ставку.'
    assert prepare_item(news)['signals']['key_rate'] == 'unknown'
