import re

STOPWORDS = {
    "это", "как", "для", "что", "или", "при", "над", "под", "без", "про",
    "все", "его", "она", "они", "том", "так", "уже", "еще", "ещё", "нет",
    "да", "из", "на", "по", "не", "но", "от", "до", "за", "об", "ко", "со",
    "во", "их", "мы", "вы", "бы", "ли", "же", "то", "а", "и", "в", "к", "с",
    "у", "о", "компани", "событ", "сюжет",
}

CERTAINTY_RE = re.compile(
    r"гарантированн|неизбежно|обязательно привед|точно выраст|"
    r"точно упадет|точно упадёт|обязательно обруш",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def tokens(text: str) -> set[str]:
    parts = re.findall(r"[a-zа-я0-9]{3,}", normalize(text))
    return {stem(part) for part in parts if part not in STOPWORDS and stem(part) not in STOPWORDS}


def stem(token: str) -> str:
    return token[:5] if len(token) >= 5 else token


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def format_money(value: int | float | None) -> str | None:
    if value is None:
        return None
    billions = float(value) / 1_000_000_000
    if billions >= 1:
        text = f"{billions:.1f}".replace(".", ",")
        if text.endswith(",0"):
            text = text[:-2]
        return f"{text} млрд ₽"
    millions = float(value) / 1_000_000
    text = f"{millions:.1f}".replace(".", ",")
    if text.endswith(",0"):
        text = text[:-2]
    return f"{text} млн ₽"


def format_int(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{int(value):,}".replace(",", " ")


def format_pct(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{round(float(value) * 100)}%"


def has_certainty(text: str) -> bool:
    return bool(CERTAINTY_RE.search(text or ""))


def hedge(text: str) -> str:
    cleaned = CERTAINTY_RE.sub("может", text or "")
    if cleaned == text and text:
        return f"Это не установленный факт. {text}"
    return cleaned
