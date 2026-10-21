TOPIC_KEYWORDS = (
    ("key_rate", ("ключев", "ставк")),
    ("metal_prices", ("стал", "металлург")),
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
    return found or ["unclassified"]
