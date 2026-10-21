"""Нативная реклама продуктов банка в сводке. Это не аналитика ЦМИ."""

CREDIT = ("кредитная линия", "овердрафт", "кредит")


def suggest_products(company: dict, news: dict) -> list[dict]:
    have = set(company.get("bank_products") or [])
    topics = set(news.get("topics") or [])
    items = []
    if "key_rate" in topics and have.intersection(CREDIT):
        items.append(
            {
                "product": "Фиксация ставки по кредитной линии",
                "text": "Компания уже пользуется кредитным продуктом. При паузе в цикле снижения ставки можно отдельно обсудить фиксацию или пересмотр графика. Это предложение продукта, а не вывод исследования банка.",
            }
        )
    if "fx_cny" in topics and ("ВЭД" in have or "расчетный счет" in have):
        items.append(
            {
                "product": "Валютный контроль и конверсия",
                "text": "В профиле есть валютные платежи. Сервис ВЭД может закрыть сверку курса и поручений. Это не прогноз курса.",
            }
        )
    if "acquiring" in topics and "эквайринг" in have:
        items.append(
            {
                "product": "Эквайринг",
                "text": "Компания уже использует эквайринг. Разбор комиссии имеет смысл только после сравнения действующего тарифа с предложением банка.",
            }
        )
    if "leasing" in topics and "лизинг" in have:
        items.append(
            {
                "product": "Лизинг техники",
                "text": "В продуктах есть лизинг. Новые ставки из сюжета относятся к новым сделкам, а не к действующему графику.",
            }
        )
    if "grain_export" in topics and "гарантии" in have:
        items.append(
            {
                "product": "Банковские гарантии для экспорта",
                "text": "При ужесточении квоты могут понадобиться гарантии по уже заключенным контрактам. Это гипотеза продукта, а не оценка квоты компании.",
            }
        )
    result = []
    for item in items:
        result.append(
            {
                "text": item["text"],
                "title": item["product"],
                "kind": "product",
                "note": "Нативное предложение продукта банка. Не является аналитикой Центра макроэкономических исследований.",
                "basis": [f"profile:{company['id']}", f"news:{news['id']}"],
            }
        )
    return result
