import json
import uuid

from app.config import ANALYSIS_VERSION
from app.datasets import load_documents
from app.providers.llm import complete, llm_status
from app.services.analysis import build_analysis, origin_label
from app.services.profile import core_gaps, get_company
from app.services.quality import narrative_is_grounded
from app.services.ranking import rank_news
from app.services.retrieval import search_documents
from app.sources.feed import collect_news
from app import audit


class NotFound(Exception):
    pass


class BriefingAgent:
    def briefing(self, company_id: str) -> dict:
        steps = []

        def mark(title: str, summary: str, tool: str, news_id: str | None = None) -> None:
            steps.append({"title": title, "summary": summary})
            audit.record(tool, company_id=company_id, news_id=news_id)

        mark("Задача определена", "Нужны профиль компании, лента и совпадение признаков.", "define_task")
        company = get_company(company_id)
        if not company:
            audit.record("load_profile", company_id=company_id, status="missing")
            raise NotFound(company_id)
        gaps = core_gaps(company)
        mark("Профиль загружен", _gap_summary(gaps), "load_profile")
        news, dropped, _rss_error = collect_news()
        mark("Лента собрана", f"Материалов до удаления повторов: {len(news) + len(dropped)}.", "collect_news")
        mark("Повторы сняты", f"Убрано близких формулировок: {len(dropped)}.", "deduplicate")
        ranked = rank_news(company, news)
        if len(ranked) < 1:
            mark(
                "Повторный отбор",
                "Значимых совпадений нет. Пустые поля не заполняются догадкой, сводка остается пустой.",
                "revise_search",
            )
        mark("Релевантность посчитана", f"В сводку вошло материалов: {len(ranked)}.", "rank")
        payload = {
            "run_id": str(uuid.uuid4()),
            "company_id": company["id"],
            "company_name": company["name"],
            "notice": (
                "Порядок сводки — сумма весов сработавших правил. "
                "Места не разложены заранее по компаниям. Демонстрационные сюжеты не являются сообщениями СМИ."
            ),
            "profile_gaps": gaps,
            "duplicates": dropped,
            "omitted_count": len(news) - len(ranked),
            "items": [_card(row) for row in ranked],
            "mode": llm_status(),
        }
        mark("Сводка сохранена", "Промежуточный след записан в локальную базу.", "save")
        payload["trace"] = steps
        from app.storage.store import get_store

        get_store().save_run(payload["run_id"], company_id, payload)
        return payload

    def analyze(self, company_id: str, news_id: str) -> dict:
        from app.storage.store import get_store

        store = get_store()
        cached = store.get_analysis(company_id, news_id, ANALYSIS_VERSION)
        if cached:
            audit.record("load_analysis", company_id=company_id, news_id=news_id, status="cache")
            return cached

        steps = []

        def mark(title: str, summary: str, tool: str) -> None:
            steps.append({"title": title, "summary": summary})
            audit.record(tool, company_id=company_id, news_id=news_id)

        mark("Задача определена", "Нужен разбор одного сюжета для выбранной компании.", "define_task")
        company = get_company(company_id)
        if not company:
            audit.record("load_profile", company_id=company_id, news_id=news_id, status="missing")
            raise NotFound(company_id)
        mark("Профиль загружен", _gap_summary(core_gaps(company)), "load_profile")
        news = _find_news(news_id)
        if not news:
            audit.record("collect_news", company_id=company_id, news_id=news_id, status="missing")
            raise NotFound(news_id)
        mark("Материал найден", origin_label(news), "collect_news")
        documents = search_documents(news, list(load_documents()))
        mark(
            "Документы отобраны",
            f"Фрагментов библиотеки: {len(documents)}. Аналитика банка помечается только если у документа есть соответствующий признак.",
            "retrieve_documents",
        )
        view = build_analysis(company, news, documents)
        mark("Черновик собран", f"Сработало правил: {len(view['relevance']['reasons'])}.", "draft_analysis")
        if view["quality"]["revised"]:
            mark("Проверка полноты", "Черновику не хватало оговорки или источник был размечен слишком сильно.", "quality_check")
            mark("Результат скорректирован", "; ".join(view["quality"]["fixes"]), "revise")
        else:
            mark("Проверка полноты", "Оговорки и источники на месте, правка не понадобилась.", "quality_check")
        note, accepted = _maybe_model(view)
        mark("Формулировка", note, "narrate" if accepted else "narrate_skipped")
        mark("Результат сохранен", "Разбор и след записаны локально.", "save")
        view["trace"] = steps
        store.save_analysis(company_id, news_id, ANALYSIS_VERSION, view)
        return view

    def ask(self, company_id: str, news_id: str, question: str) -> dict:
        from app.services.followup import answer_question

        company = get_company(company_id)
        news = _find_news(news_id)
        if not company or not news:
            audit.record("ask", company_id=company_id, news_id=news_id, status="missing")
            raise NotFound(company_id if not company else news_id)
        analysis = self.analyze(company_id, news_id)
        answer = answer_question(company, news, analysis, question)
        audit.record("ask", company_id=company_id, news_id=news_id, status=answer["kind"])
        from app.storage.store import get_store

        get_store().save_question(company_id, news_id, question, answer)
        return answer


def _find_news(news_id: str) -> dict | None:
    news, _, _ = collect_news()
    return next((item for item in news if item["id"] == news_id), None)


def _gap_summary(gaps: list[str]) -> str:
    if not gaps:
        return "Обязательные поля профиля заполнены."
    return "В профиле нет: " + ", ".join(gaps) + "."


def _card(row: dict) -> dict:
    news = row["news"]
    return {
        "id": news["id"],
        "title": news["title"],
        "published_at": news["published_at"],
        "category": news.get("category"),
        "source_name": news.get("source_name"),
        "origin": news.get("origin"),
        "origin_label": origin_label(news),
        "relevance": {"score": row["score"], "level": row["level"], "reasons": row["reasons"]},
        "short_impact": row["short"],
    }


def _maybe_model(view: dict) -> tuple[str, bool]:
    status = llm_status()
    if status["mode"] != "live":
        return "Модель не вызывалась. " + status["note"], False
    packet = json.dumps(
        {"sections": view["sections"], "bank_found": view["bank_found"]},
        ensure_ascii=False,
    )
    text = complete(
        [
            {
                "role": "system",
                "content": (
                    "Перепиши разбор по-русски в двух коротких абзацах для руководителя. "
                    "Не добавляй чисел, имен и фактов, которых нет во входе. "
                    "Не утверждай позицию Альфа-Банка, если bank_found равен false. "
                    "Не пиши, что последствие гарантировано. Верни только текст."
                ),
            },
            {"role": "user", "content": packet[:12000]},
        ]
    )
    if text and narrative_is_grounded(text, packet, view["bank_found"]):
        view["generation"] = {
            "mode": "llm",
            "model": status["model"],
            "narrative": text.strip(),
            "note": f"Формулировку переписала модель {status['model']}. Числа и упоминание банка проверены по входному разбору.",
        }
        return "Формулировка модели прошла проверку.", True
    return "Ответ модели отклонен проверкой или не получен. Показан разбор правил.", False
