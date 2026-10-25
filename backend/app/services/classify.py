import re


TOPIC_KEYWORDS = (
    ("metal_prices", ("сталь", "металлург", "прокат")),
    ("fx_cny", ("юан",)),
    ("auto_production", ("автомобил",)),
    ("tax_admin", ("отчетн", "отчётност")),
    ("regional_logistics", ("грузовик",)),
    ("group_treasury", ("поручитель", "внутригруп")),
    ("labor_it", ("ит-специал", "айти")),
    ("it_demand", ("внедрен", "программн")),
    ("retail_demand", ("розниц",)),
    ("acquiring", ("эквайринг",)),
    ("grain_export", ("зерн", "квот")),
    ("weather", ("влаг", "засух")),
    ("fuel", ("дизел", "топлив")),
    ("leasing", ("лизинг",)),
    ("sports", ("матч", "команда")),
)


def classify_topics(text: str, existing: list[str] | None = None) -> list[str]:
    if existing:
        return list(existing)
    lowered = (text or "").lower().replace("ё", "е")
    found = [topic for topic, keys in TOPIC_KEYWORDS if any(key in lowered for key in keys)]
    if re.search(r'цен[^.!?]{0,35}стали', lowered) and 'metal_prices' not in found:
        found.append('metal_prices')
    if re.search(r'ключев\w* ставк|(?:банк росси|цб рф)[^.!?]{0,80}ставк', lowered) and 'key_rate' not in found:
        found.append('key_rate')
    return found or ["unclassified"]
