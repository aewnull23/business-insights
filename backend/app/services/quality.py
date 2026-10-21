import copy
import re

from app.services.retrieval import BANK_ABSENT
from app.textutil import has_certainty, hedge

DEBT_UNKNOWN = (
    "В профиле нет данных о структуре долга и о том, какая часть обязательств "
    "привязана к ключевой ставке. Без этого процентные расходы не оцениваются."
)

NUMBER_RE = re.compile(r"\d+(?:[\s\u00a0]\d+)*(?:[,.]\d+)?%?")


def check(draft: dict) -> list[str]:
    issues = []
    if "debt_service" in draft["fired_rule_ids"] and not any("структуре долга" in item.lower() for item in draft["unknowns"]):
        issues.append("missing_debt_structure")
    for claim in _claims(draft):
        if claim["kind"] == "ai" and not claim.get("basis"):
            issues.append("unsourced_claim")
        if claim["kind"] == "confirmed" and claim.get("origin") != "verified_feed":
            issues.append("demo_marked_confirmed")
        if has_certainty(claim.get("text") or ""):
            issues.append("certainty_language")
    for text in draft["unknowns"]:
        if has_certainty(text):
            issues.append("certainty_language")
    if draft["bank"]["found"] and not draft["bank"]["items"]:
        issues.append("false_bank_claim")
    if not draft["bank"]["found"] and "не найден" not in draft["bank"]["message"].lower():
        issues.append("false_bank_claim")
    return list(dict.fromkeys(issues))


def repair(draft: dict, issues: list[str]) -> dict:
    fixed = copy.deepcopy(draft)
    fixes = []
    if "missing_debt_structure" in issues:
        fixed["unknowns"].append(DEBT_UNKNOWN)
        fixes.append("Добавлена оговорка: в профиле нет структуры долга.")
    if "certainty_language" in issues:
        for claim in _claims(fixed):
            claim["text"] = hedge(claim["text"])
        fixed["unknowns"] = [hedge(item) for item in fixed["unknowns"]]
        fixes.append("Сняты формулировки, которые звучали как установленный факт.")
    if "unsourced_claim" in issues:
        for key in ("consequences", "risks", "opportunities", "why"):
            kept = []
            for claim in fixed[key]:
                if claim["kind"] == "ai" and not claim.get("basis"):
                    fixed["unknowns"].append("Снято проверкой как вывод без источника: " + claim["text"])
                else:
                    kept.append(claim)
            fixed[key] = kept
        fixes.append("Выводы без источника убраны из утверждений.")
    if "demo_marked_confirmed" in issues:
        for claim in fixed["confirmed_facts"]:
            if claim.get("origin") != "verified_feed":
                claim["kind"] = "source"
                claim["verification"] = "demo_source"
                fixed["source_facts"].append(claim)
        fixed["confirmed_facts"] = [
            claim for claim in fixed["confirmed_facts"] if claim.get("origin") == "verified_feed"
        ]
        fixes.append("Демонстрационные сведения не оставлены в блоке подтвержденных фактов.")
    if "false_bank_claim" in issues:
        fixed["bank"] = {"found": False, "message": BANK_ABSENT, "items": []}
        fixes.append("Убрано неподтвержденное упоминание аналитики банка.")
    fixed["quality_fixes"] = fixes
    return fixed


def safe_fallback(draft: dict) -> dict:
    fixed = copy.deepcopy(draft)
    for key in ("consequences", "risks", "opportunities", "why"):
        fixed[key] = [claim for claim in fixed[key] if claim.get("basis")]
    if "не найден" not in fixed["bank"]["message"].lower() and not fixed["bank"]["items"]:
        fixed["bank"] = {"found": False, "message": BANK_ABSENT, "items": []}
    fixed["unknowns"].append("Часть формулировок снята проверкой качества, потому что к ним не было надежного источника.")
    return fixed


def narrative_is_grounded(narrative: str, source_text: str, bank_found: bool) -> bool:
    if not narrative:
        return False
    if not bank_found and "альфа-банк" in narrative.lower():
        return False
    compact_source = source_text.replace(" ", "").replace("\u00a0", "")
    for number in NUMBER_RE.findall(narrative):
        compact = number.replace(" ", "").replace("\u00a0", "")
        if compact not in compact_source and number not in source_text:
            return False
    return True


def _claims(draft: dict):
    for key in ("source_facts", "confirmed_facts", "attributes", "why", "consequences", "risks", "opportunities", "actions"):
        for claim in draft.get(key) or []:
            yield claim
