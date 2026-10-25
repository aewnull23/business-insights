import json
import hashlib
import uuid

from app.config import ANALYSIS_VERSION
from app.datasets import load_documents
from app.providers.llm import complete, llm_status
from app.services.analysis import build_analysis, origin_label
from app.services.profile import core_gaps, get_company
from app.services.quality import narrative_is_grounded
from app.services.ranking import rank_for
from app.services.retrieval import search_documents
from app.services.users import default_user, get_user
from app.sources.feed import collect_news
from app import audit


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class BriefingAgent:
    def briefing(self, company_id: str, user_id: str | None = None) -> dict:
        steps = []
        user = _resolve_user(company_id, user_id)

        def mark(title: str, summary: str, tool: str, news_id: str | None = None) -> None:
            steps.append({"title": title, "summary": summary})
            audit.record(tool, company_id=company_id, news_id=news_id, user_id=None if not user else user["id"])

        mark("Задача определена", "Нужны профиль компании, лента, роль пользователя и совпадение признаков.", "define_task")
        company = get_company(company_id)
        if not company:
            audit.record("load_profile", company_id=company_id, status="missing")
            raise NotFound(company_id)
        gaps = core_gaps(company)
        mark("Профиль загружен", _gap_summary(gaps), "load_profile")
        if user:
            mark(
                "Роль учтена",
                f"{user['role']}. Фокус ленты: {', '.join(user.get('focus_topics') or []) or 'без дополнительной надбавки'}.",
                "load_user",
            )
        news, dropped, _rss_error = collect_news()
        mark("Лента собрана", f"Материалов до удаления повторов: {len(news) + len(dropped)}.", "collect_news")
        mark("Повторы сняты", f"Убрано близких формулировок: {len(dropped)}.", "deduplicate")
        ranked = rank_for(company, news, user)
        if len(ranked) < 1:
            mark(
                "Оценка достаточности",
                "Значимых совпадений нет. Пустые поля не заполняются догадкой, сводка остается пустой.",
                "check_evidence",
            )
        mark("Релевантность посчитана", f"В сводку вошло материалов: {len(ranked)}.", "rank")
        payload = {
            "run_id": str(uuid.uuid4()),
            "company_id": company["id"],
            "company_name": company["name"],
            "user": None if not user else {"id": user["id"], "role": user["role"], "display_name": user["display_name"]},
            "notice": (
                "Порядок сводки — сумма весов правил с надбавкой роли. "
                "Места не разложены заранее по компаниям. Синтетические сюжеты не являются сообщениями СМИ."
            ),
            "profile_gaps": gaps,
            "duplicates": dropped,
            "omitted_count": len(news) - len(ranked),
            "items": [_card(row) for row in ranked],
            "mode": llm_status(),
            "plan": _plan("briefing"),
            "context": {"company_id": company_id, "user_id": user["id"] if user else None,
                        "profile_gaps": gaps, "selected_news_ids": [row["news"]["id"] for row in ranked]},
        }
        mark("Сводка сохранена", "Промежуточный след записан в локальную базу.", "save")
        payload["trace"] = steps
        from app.storage.store import get_store

        get_store().save_run(payload["run_id"], company_id, payload)
        return payload

    def analyze(self, company_id: str, news_id: str, user_id: str | None = None) -> dict:
        user = _resolve_user(company_id, user_id)
        company = get_company(company_id)
        news = _find_news(news_id)
        if not company or not news:
            raise NotFound(company_id if not company else news_id)
        return self._analyze_news(company, news, user)

    def preview(self, company_id: str, news: dict, user_id: str | None = None) -> dict:
        """Analyze submitted material without adding it to the feed or analysis cache."""
        from app.services.news_pipeline import prepare_item

        user = _resolve_user(company_id, user_id)
        company = get_company(company_id)
        if not company:
            raise NotFound(company_id)
        prepared = prepare_item({**news, "id": news.get("id") or "preview-" + uuid.uuid4().hex,
                                 "origin": "user_supplied", "facts": []})
        return self._analyze_news(company, prepared, user, persist=False)

    def _analyze_news(self, company: dict, news: dict, user: dict | None, *, persist: bool = True) -> dict:
        from app.storage.store import get_store

        company_id, news_id = company["id"], news["id"]
        store = get_store()
        library = list(load_documents())
        mode = llm_status()
        version = _version(user, company, news, library, mode)
        cached = store.get_analysis(company_id, news_id, version) if persist else None
        if cached:
            audit.record("load_analysis", company_id=company_id, news_id=news_id, status="cache")
            return cached

        steps = []

        def mark(title: str, summary: str, tool: str) -> None:
            steps.append({"title": title, "summary": summary})
            audit.record(tool, company_id=company_id, news_id=news_id, user_id=None if not user else user["id"])

        mark("Задача определена", "Нужен разбор одного сюжета для выбранной компании и роли.", "define_task")
        mark("Профиль загружен", _gap_summary(core_gaps(company)), "load_profile")
        mark("Материал найден", origin_label(news), "collect_news")
        documents = search_documents(news, library)
        bank_hits = sum(1 for item in documents if item.get("is_bank_research"))
        attempts = [{"strategy": "topics", "document_ids": [item["id"] for item in documents], "bank_hits": bank_hits}]
        mark(
            "Документы отобраны",
            f"Фрагментов библиотеки: {len(documents)}, из них аналитика банка: {bank_hits}.",
            "retrieve_documents",
        )
        if not bank_hits:
            expanded = search_documents(news, library, strategy="lexical")
            attempts.append({"strategy": "lexical", "document_ids": [item["id"] for item in expanded],
                             "bank_hits": sum(bool(item.get("is_bank_research")) for item in expanded)})
            seen = {item["id"] for item in documents}
            documents.extend(item for item in expanded if item["id"] not in seen)
            mark("Поиск уточнен", f"Поиск по тексту выдержек вместо меток тем: найдено фрагментов {len(expanded)}. Нерелевантные материалы не подставляются.", "revise_search")
        view = build_analysis(company, news, documents, user)
        mark("Черновик собран", f"Сработало правил: {len(view['relevance']['reasons'])}.", "draft_analysis")
        if view["quality"]["revised"]:
            mark("Проверка полноты", "Черновику не хватало оговорки или источник был размечен слишком сильно.", "quality_check")
            mark("Результат скорректирован", "; ".join(view["quality"]["fixes"]), "revise")
        elif view["quality"]["passed"]:
            mark("Проверка полноты", "Оговорки и источники на месте, правка не понадобилась.", "quality_check")
        if not view["quality"]["passed"]:
            mark("Требуется проверка", "Не все проверки качества пройдены: " + ", ".join(view["quality"]["issues"]), "quality_failed")
        note, accepted = _maybe_model(view) if view["quality"]["passed"] else ("Модель не вызвана: разбор требует проверки.", False)
        mark("Формулировка", note, "narrate" if accepted else "narrate_skipped")
        view["plan"] = _plan("analysis")
        view["context"] = {
            "company_id": company_id, "news_id": news_id, "user_id": user["id"] if user else None,
            "profile_gaps": core_gaps(company), "retrieval_attempts": attempts,
            "document_ids": [item["id"] for item in documents],
            "source_ids": [item["id"] for item in view["sources"]],
            "fingerprint": version,
        }
        view["transient"] = not persist
        mark("Результат сохранен" if persist else "Предпросмотр готов",
             "Разбор и след записаны локально." if persist else "Материал не добавлен в ленту и кеш разборов.",
             "save" if persist else "preview_complete")
        view["trace"] = steps
        if persist:
            store.save_analysis(company_id, news_id, version, view)
        return view

    def ask(self, company_id: str, news_id: str, question: str, user_id: str | None = None) -> dict:
        from app.services.followup import answer_question

        company = get_company(company_id)
        news = _find_news(news_id)
        if not company or not news:
            audit.record("ask", company_id=company_id, news_id=news_id, status="missing")
            raise NotFound(company_id if not company else news_id)
        analysis = self.analyze(company_id, news_id, user_id)
        answer = answer_question(company, news, analysis, question)
        audit.record("ask", company_id=company_id, news_id=news_id, status=answer["kind"])
        from app.storage.store import get_store

        get_store().save_question(company_id, news_id, question, answer)
        return answer


def _resolve_user(company_id: str, user_id: str | None) -> dict | None:
    if user_id:
        user = get_user(user_id)
        if not user:
            raise NotFound(user_id)
        if user["company_id"] != company_id:
            raise Forbidden(user_id)
        return user
    return default_user(company_id)


def _version(user: dict | None, company: dict, news: dict, documents: list[dict], mode: dict) -> str:
    packet = {"pipeline": "evidence-v3", "user": user, "company": company, "news": news,
              "documents": documents, "mode": mode.get("mode"), "model": mode.get("model")}
    digest = hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"{ANALYSIS_VERSION}:{digest}"


def _plan(task: str) -> list[dict]:
    steps = [
        {"tool": "load_profile", "purpose": "Проверить заполненные поля компании и роль пользователя"},
        {"tool": "collect_news", "purpose": "Получить материал и отделить сведения источника от подтвержденных фактов"},
    ]
    if task == "briefing":
        return steps + [{"tool": "deduplicate", "purpose": "Снять повторяющиеся сюжеты"},
                        {"tool": "rank", "purpose": "Отобрать новости по профилю и роли"}]
    return steps + [
        {"tool": "retrieve_documents", "purpose": "Найти выдержки банка по темам события"},
        {"tool": "revise_search", "purpose": "Повторить поиск по тексту, если банк не найден", "condition": "no_bank_hits"},
        {"tool": "draft_analysis", "purpose": "Связать выводы с профилем, событием и документами"},
        {"tool": "quality_check", "purpose": "Проверить происхождение, оговорки и исправить недостатки"},
    ]


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
