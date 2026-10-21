"""Правила сопоставления сюжета с профилем.

Вес правила — это вклад в релевантность в процентных пунктах.
Оценка новости равна сумме весов сработавших правил и не назначается компании заранее.
"""

from app.textutil import format_int, format_money, format_pct

CREDIT_PRODUCTS = ("кредитная линия", "овердрафт", "кредит")

RULES = [
    {"id": "metal_revenue", "title": "Цена стали и отрасль", "weight": 46, "topics_any": ["metal_prices"], "industries_any": ["Металлургия", "Торговля металлами"]},
    {"id": "metal_scrap", "title": "Сырьевой канал лома", "weight": 12, "topics_any": ["metal_prices"], "counterparty_keywords_any": ["лом"]},
    {"id": "cny_fx", "title": "Доля юаня в платежах", "weight": 34, "topics_any": ["fx_cny"], "fx_any": ["CNY"], "min_fx_share": 0.05},
    {"id": "cny_export", "title": "Экспорт при сюжете про юань", "weight": 10, "topics_any": ["fx_cny"], "fx_any": ["CNY"], "min_fx_share": 0.05, "min_export_share": 0.1},
    {"id": "auto_demand", "title": "Покупатель из автопрома", "weight": 33, "topics_any": ["auto_production"], "counterparty_keywords_any": ["авто"]},
    {"id": "debt_service", "title": "Стоимость долга", "weight": 32, "topics_any": ["key_rate"], "products_any": list(CREDIT_PRODUCTS)},
    {"id": "deposit_rate", "title": "Ставка и депозит", "weight": 12, "topics_any": ["key_rate"], "products_any": ["депозит"]},
    {"id": "regional_logistics", "title": "Регион отгрузки", "weight": 30, "topics_any": ["regional_logistics"], "region_overlap": True},
    {"id": "tax_admin", "title": "Отчетность крупной выручки", "weight": 28, "topics_any": ["tax_admin"], "min_revenue_rub": 10_000_000_000},
    {"id": "group_treasury", "title": "Контур группы компаний", "weight": 26, "topics_any": ["group_treasury"], "requires_group": True},
    {"id": "broad_labor", "title": "Фонд оплаты без разбивки ролей", "weight": 20, "topics_any": ["labor_it"], "min_employees": 1000, "exclude_industries_any": ["Информационные технологии"]},
    {"id": "it_labor", "title": "Найм в ИТ-компании", "weight": 44, "topics_any": ["labor_it"], "industries_any": ["Информационные технологии"]},
    {"id": "it_demand", "title": "Спрос на внедрение ПО", "weight": 36, "topics_any": ["it_demand"], "industries_any": ["Информационные технологии"]},
    {"id": "retail_demand", "title": "Оборот розницы", "weight": 44, "topics_any": ["retail_demand"], "industries_any": ["Розничная торговля"]},
    {"id": "acquiring_fees", "title": "Комиссия эквайринга", "weight": 40, "topics_any": ["acquiring"], "products_any": ["эквайринг"]},
    {"id": "grain_export", "title": "Экспортная квота зерна", "weight": 46, "topics_any": ["grain_export"], "industries_any": ["Сельское хозяйство"]},
    {"id": "drought", "title": "Погодный риск", "weight": 38, "topics_any": ["weather"], "any_of": [{"industries_any": ["Сельское хозяйство"]}, {"region_overlap": True}]},
    {"id": "fuel_cost", "title": "Топливо в перевозках", "weight": 46, "topics_any": ["fuel"], "industries_any": ["Транспорт и логистика"]},
    {"id": "leasing_rate", "title": "Ставка лизинга", "weight": 34, "topics_any": ["leasing"], "products_any": ["лизинг"]},
]


def _blob(news: dict) -> str:
    parts = [news.get("title") or "", news.get("summary") or ""]
    parts.extend(fact.get("text") or "" for fact in news.get("facts") or [])
    return " ".join(parts)


def _has(news: dict, snippet: str) -> bool:
    return snippet in _blob(news)


def _missing(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _counterparty_blob(company: dict) -> str:
    parts = []
    for row in company.get("counterparties") or []:
        parts.append(str(row.get("name") or ""))
        parts.append(str(row.get("role") or ""))
    return " ".join(parts).lower()


def _find_counterparty(company: dict, keyword: str) -> dict | None:
    for row in company.get("counterparties") or []:
        if keyword in str(row.get("name") or "").lower():
            return row
    return None


def _products(company: dict, names: tuple[str, ...] | list[str]) -> list[str]:
    have = company.get("bank_products") or []
    return [item for item in have if item in names]


def _branch_ok(branch: dict, company: dict, news: dict) -> bool:
    if "industries_any" in branch and company.get("industry") not in branch["industries_any"]:
        return False
    if "products_any" in branch and not set(company.get("bank_products") or []).intersection(branch["products_any"]):
        return False
    if "counterparty_keywords_any" in branch:
        blob = _counterparty_blob(company)
        if not any(key in blob for key in branch["counterparty_keywords_any"]):
            return False
    if "fx_any" in branch:
        shares = ((company.get("payments") or {}).get("currency_share") or {})
        minimum = branch.get("min_fx_share", 0.05)
        if not any(float(shares.get(code) or 0) >= minimum for code in branch["fx_any"]):
            return False
    if "min_revenue_rub" in branch:
        revenue = company.get("revenue_rub")
        if revenue is None or revenue < branch["min_revenue_rub"]:
            return False
    if "min_employees" in branch:
        employees = company.get("employees")
        if employees is None or employees < branch["min_employees"]:
            return False
    if company.get("industry") in branch.get("exclude_industries_any", []):
        return False
    if branch.get("requires_group") and not company.get("group"):
        return False
    if branch.get("region_overlap"):
        regions = set(news.get("regions") or [])
        own = {company.get("region"), company.get("city")} - {None}
        if not regions or not regions.intersection(own):
            return False
    if "min_export_share" in branch:
        share = (company.get("payments") or {}).get("export_share_of_revenue")
        if share is None or share < branch["min_export_share"]:
            return False
    return True


def applies(rule: dict, company: dict, news: dict) -> bool:
    topics = set(news.get("topics") or [])
    if rule.get("topics_any") and not topics.intersection(rule["topics_any"]):
        return False
    if rule.get("any_of"):
        return any(_branch_ok(branch, company, news) for branch in rule["any_of"])
    return _branch_ok(rule, company, news)


def _gaps(company: dict, keys: list[str]) -> list[str]:
    texts = {
        "revenue_rub": "Выручка не указана, поэтому масштаб влияния на финансовый результат не оценивается.",
        "employees": "Численность не указана и в оценке не используется.",
        "region": "Регион не указан, региональный канал не учитывается.",
        "payments": "Сведения о платежах и валютной структуре отсутствуют.",
        "counterparties": "Контрагенты не указаны, канал спроса через покупателей не подтвержден профилем.",
        "bank_products": "Банковские продукты не указаны, кредитный и платежный контур не оценивается.",
    }
    result = []
    for key in keys:
        if _missing(company.get(key)):
            result.append(texts[key])
    return result


def _pack(reason, attributes, consequences, risks, opportunities, actions, unknowns) -> dict:
    return {
        "reason": reason,
        "attributes": [item for item in attributes if item],
        "consequences": [item for item in consequences if item],
        "risks": [item for item in risks if item],
        "opportunities": [item for item in opportunities if item],
        "actions": [item for item in actions if item],
        "unknowns": [item for item in unknowns if item],
    }


def _metal_revenue(company: dict, news: dict) -> dict:
    money = format_money(company.get("revenue_rub"))
    move = "6% из сюжета" if _has(news, "6%") else "рыночное движение"
    falling = (news.get("signals") or {}).get("metal_prices") == "down" or _has(news, "сниз")
    price_move = "Снижение цены стали" if falling else "Движение цены стали"
    attributes = [f"Отрасль профиля: {company.get('industry')}."]
    if company.get("okved"):
        title = f" — {company['okved_name']}" if company.get("okved_name") else ""
        attributes.append(f"ОКВЭД {company['okved']}{title}.")
    if money:
        attributes.append(f"Выручка в профиле: {money}. Доля, зависящая от спотовой цены, не выделена.")
    consequences = [
        f"{price_move} может затронуть реализацию, если часть продаж идет без фиксации цены. Наличие такой части из профиля не следует."
    ]
    if money:
        consequences.append(f"Выручка {money} показывает масштаб компании, но не долю цены в контрактах. Переносить {move} на эту сумму нельзя.")
    return _pack(
        "Отрасль компании — металлургия, сюжет о цене стали",
        attributes,
        consequences,
        ["Давление на выручку возможно только для незафиксированных продаж. Это гипотеза, а не следствие, доказанное источником."],
        [],
        ["Проверить долю спотовых и формульных контрактов. Этих данных в профиле нет."],
        [f"Доля контрактов с привязкой к спотовой цене не указана, поэтому {move} нельзя переносить на выручку компании."]
        + _gaps(company, ["revenue_rub", "employees", "region", "payments", "counterparties"]),
    )


def _metal_scrap(company: dict, news: dict) -> dict:
    row = _find_counterparty(company, "лом") or {}
    name = row.get("name") or "поставщик лома"
    share = format_pct(row.get("share_of_costs")) if row.get("share_of_costs") is not None else None
    share_text = f" Доля в затратах по профилю — {share}." if share else ""
    return _pack(
        f"В профиле есть поставщик лома: {name}",
        [f"Контрагент «{name}», роль: поставщик.{share_text}"],
        [f"У компании указан поставщик «{name}». Снижение цены стали не равно снижению цены лома: индекс лома в источнике не приведен."],
        ["Маржа может сжаться или расшириться. Направление по двум ценам из имеющихся данных не определяется."],
        ["Если цена лома снижается вместе с ценой стали, сырье может дешеветь. Это гипотеза: индекса лома в сюжете нет."],
        ["Сравнить закупочную цену лома и цену реализации. В профиле этой пары цен нет."],
        ["Цена лома и полная доля в себестоимости, кроме доли контрагента, не раскрыты."],
    )


def _cny_fx(company: dict, news: dict) -> dict:
    payments = company.get("payments") or {}
    cny = format_pct((payments.get("currency_share") or {}).get("CNY"))
    dependence = payments.get("import_dependence")
    attributes = [f"Доля CNY в платежах профиля: {cny}."]
    unknowns = ["Доля контрактов с фиксацией курса не указана. Доля валюты в платежах не равна открытой валютной позиции."]
    if dependence:
        attributes.append(f"В профиле качественно указана зависимость от импорта: {dependence}. Числовая доля импорта в закупках не задана.")
    else:
        unknowns.append("Назначение юаневых платежей в профиле не детализировано.")
    return _pack(
        f"В платежах есть юань, доля {cny}",
        attributes,
        [f"Волатильность юаня может менять рублевый эквивалент операций в этой валюте. На платежи в юанях приходится {cny} профиля."],
        ["Рублевая себестоимость может колебаться, если юаневые платежи связаны с закупками. Это чтение профиля, а не расчет эффекта."],
        [],
        ["Сверить валюту контрактов и наличие хеджирования. Хедж в данных не указан."],
        unknowns,
    )


def _cny_export(company: dict, news: dict) -> dict:
    export = format_pct((company.get("payments") or {}).get("export_share_of_revenue"))
    return _pack(
        f"Доля экспорта в выручке — {export}, сюжет при этом про юань",
        [f"Доля экспорта в выручке: {export}. Валюта экспортных контрактов в профиле не названа."],
        [f"Экспортная доля {export} показывает валютную подверженность, но не доказывает, что экспорт номинирован в юанях."],
        ["Связывать экспортную выручку с волатильностью юаня нельзя, пока валюта контрактов неизвестна."],
        [],
        ["Уточнить валюту экспортных контрактов отдельно от доли CNY в платежах."],
        ["Валюта экспортных контрактов не указана, поэтому связь экспорта с юанем не подтверждена."],
    )


def _auto_demand(company: dict, news: dict) -> dict:
    row = _find_counterparty(company, "авто") or {}
    name = row.get("name") or "покупатель из автопрома"
    share = format_pct(row.get("share_of_revenue")) if row.get("share_of_revenue") is not None else None
    move = "9%" if _has(news, "9%") else "изменение выпуска из сюжета"
    share_bit = f" В профиле на него приходится {share} выручки." if share else ""
    return _pack(
        f"Покупатель «{name}» связывает компанию с автопромом",
        [f"Контрагент «{name}», роль: покупатель.{share_bit}"],
        [f"Сюжет о выпуске автомобилей относится к отрасли покупателя «{name}».{share_bit} Это не означает такое же изменение выручки компании."],
        [f"Спрос со стороны этого покупателя может ослабнуть. Его план закупок в данных отсутствует. Переносить {move} на выручку компании нельзя."],
        [],
        [f"Проверить статус заказов контрагента «{name}». Портфеля заказов в профиле нет."],
        ["Нет портфеля заказов контрагента и доли его закупок, зависящей от выпуска легковых автомобилей."],
    )


def _debt_service(company: dict, news: dict) -> dict:
    products = ", ".join(_products(company, CREDIT_PRODUCTS))
    signal = (news.get("signals") or {}).get("key_rate") or "unknown"
    level = (news.get("signals") or {}).get("key_rate_level")
    level_note = ""
    if level and level in _blob(news):
        level_note = f" Уровень {level} взят из материала и не заменяет сверку с публикацией регулятора."
    if signal == "unchanged":
        consequence = f"В сюжете ставка не меняется. Для продуктов «{products}» это сохранение текущего ориентира, а не новое ценовое событие.{level_note}"
        risk = "Если ставка в договоре плавающая, уровень из сюжета продолжает относиться к процентным расходам. Тип ставки в договоре не указан."
        opportunity = "Пауза дает время сверить условия без срочного рефинансирования. Это окно для проверки, а не выгода само по себе."
    elif signal == "hike":
        consequence = f"Рост ставки в сюжете может удорожать «{products}», если договор привязан к индикатору или лимит скоро пересматривается.{level_note}"
        risk = "Процентные расходы могут вырасти только для плавающей части. Тип ставки в договоре не указан."
        opportunity = ""
    elif signal == "cut":
        consequence = f"Снижение ставки может удешевить «{products}» только при плавающей ставке или пересмотре договора.{level_note}"
        risk = "Для фиксированной ставки эффект из сюжета не следует. Тип ставки не указан."
        opportunity = "При плавающей ставке обслуживание может стать дешевле. Пока это только повод проверить договор."
    else:
        consequence = f"Сюжет относится к ключевой ставке и к продуктам «{products}», но направление изменения не извлечено.{level_note}"
        risk = "Нельзя сказать, дорожает или дешевеет фондирование."
        opportunity = ""
    return _pack(
        f"Подключены продукты: {products}",
        [f"Банковские продукты, из-за которых сработало правило: {products}."],
        [consequence],
        [risk],
        [opportunity],
        [f"Сверить тип ставки и дату пересмотра по продуктам: {products}."],
        ["Учебное или неполное описание ставки нельзя считать достаточным для оценки процентных расходов в рублях."],
    )


def _deposit_rate(company: dict, news: dict) -> dict:
    signal = (news.get("signals") or {}).get("key_rate") or "unknown"
    if signal == "unchanged":
        consequence = "Для депозита пауза в ставке сохраняет текущий ориентир размещения, если договор от нее зависит. Эта связь в профиле не указана."
    elif signal == "hike":
        consequence = "Рост ключевой ставки может повысить ориентир по новым депозитам. Действующая ставка компании в профиле не указана."
    elif signal == "cut":
        consequence = "Снижение ключевой ставки может понизить ориентир по новым депозитам. Действующая ставка в профиле не указана."
    else:
        consequence = "Сюжет про ставку может относиться к депозиту, но направление не извлечено."
    return _pack(
        "В продуктах есть депозит",
        ["Банковский продукт: депозит."],
        [consequence],
        [],
        ["Можно сверить ставку действующего депозита с новыми предложениями. Сравнения в данных нет, поэтому возможность не посчитана."],
        ["Проверить срок и ставку действующего депозита. Их нет в профиле."],
        ["Ставка и срок депозита компании не указаны."],
    )


def _regional(company: dict, news: dict) -> dict:
    place = company.get("region") or company.get("city") or "регион из сюжета"
    return _pack(
        f"Регион компании совпадает с сюжетом: {place}",
        [f"Регион: {company.get('region') or 'не указан'}. Город: {company.get('city') or 'не указан'}."],
        [f"Ограничения для грузовиков относятся к региону компании ({place}) и могут затронуть только те маршруты, которые под них попадают."],
        ["Срок отгрузки может сдвинуться лишь для затронутых маршрутов. Их доля неизвестна, поэтому риск не равен остановке продаж."],
        [],
        ["Сопоставить склады и маршруты с ограничениями из сюжета. Логистической схемы в профиле нет."],
        ["Логистическая схема и доля отгрузок через ограниченные маршруты в профиле отсутствуют."],
    )


def _tax_admin(company: dict, news: dict) -> dict:
    money = format_money(company.get("revenue_rub")) or "указанная в профиле"
    if _has(news, "10 млрд"):
        reason = f"Выручка {money} не ниже порога 10 млрд ₽ из сюжета"
        consequence = f"Выручка {money} попадает в порог, который сюжет называет для обсуждаемой отчетности. Сюжет не является нормативным актом, обязанность из него не наступила."
        attributes = [f"Выручка профиля: {money}. Порог в сюжете — от 10 млрд рублей."]
    else:
        reason = f"Выручка {money} достигает порога правила для сюжетов об отчетности крупного бизнеса"
        consequence = "Сюжет отнесен к теме отчетности крупного бизнеса. Точный порог из текста не извлечен, поэтому совпадение с выручкой условное."
        attributes = [f"Выручка профиля: {money}."]
    return _pack(
        reason,
        attributes,
        [consequence],
        ["Нагрузка на отчетность может вырасти, только если правило будет принято. В материале этого нет."],
        [],
        ["Сверить сюжет с действующими требованиями. Процессы не стоит менять только на его основании."],
        ["Нет текста нормы и даты, с которой обсуждаемое правило могло бы действовать."],
    )


def _group(company: dict, news: dict) -> dict:
    group = company.get("group") or {}
    name = group.get("name") or "группа"
    role = f" Роль: {group.get('role')}." if group.get("role") else ""
    return _pack(
        f"Компания входит в {name}",
        [f"Группа: {name}.{role} Сведения о внутригрупповых обязательствах отсутствуют."],
        [f"Компания указана в составе «{name}». Сюжет говорит о проверке поручительств вообще и не устанавливает, что они есть у этой группы."],
        ["Нельзя считать поручительства существующими или проблемными только из факта вхождения в группу."],
        [],
        ["Запросить у казначейства перечень поручительств. В профиле его нет."],
        ["Внутригрупповые обязательства в данных отсутствуют."],
    )


def _broad_labor(company: dict, news: dict) -> dict:
    employees = format_int(company.get("employees")) or "указанная численность"
    move = "12%" if _has(news, "12%") else "изменение зарплат из сюжета"
    return _pack(
        f"Численность {employees}: сюжет о зарплатах может задеть фонд оплаты точечно",
        [f"Сотрудники: {employees}. Доля ИТ-ролей не выделена."],
        [f"Численность {employees} делает тему найма заметной, но сюжет про ИТ-специалистов. Переносить {move} на весь фонд оплаты нельзя."],
        ["Точечный рост затрат на ИТ-найм возможен. Масштаб неизвестен, потому что роли в профиле не разложены."],
        [],
        ["Посмотреть долю открытых ИТ-вакансий. Этих данных в профиле нет."],
        ["Структура персонала по ролям отсутствует."],
    )


def _it_labor(company: dict, news: dict) -> dict:
    employees = format_int(company.get("employees"))
    staff = f" В профиле {employees} сотрудников." if employees else ""
    move = "12%" if _has(news, "12%") else "темп из сюжета"
    unknowns = ["Не выделена доля дефицитных ролей, поэтому рыночный темп нельзя переносить на фонд оплаты."]
    if not employees:
        unknowns.append("Численность не указана и не используется.")
    return _pack(
        "Отрасль компании — информационные технологии, сюжет о найме ИТ-специалистов",
        [f"Отрасль: информационные технологии.{staff}"],
        [f"Для ИТ-компании сюжет о зарплатах ближе к себестоимости, чем для других отраслей.{staff} Все равно {move} не переносится на расходы автоматически."],
        ["Давление на себестоимость возможно, если дефицитные роли составляют заметную часть штата. Эта доля неизвестна."],
        ["Если компания продает дефицитную экспертизу, ставки для заказчиков тоже могут пересматриваться. Прайс в профиле отсутствует, это гипотеза."],
        ["Сравнить открытые вакансии с ролями, о которых говорит сюжет."],
        unknowns,
    )


def _it_demand(company: dict, news: dict) -> dict:
    return _pack(
        "Отрасль — информационные технологии, сюжет о спросе на внедрение",
        ["Отрасль: информационные технологии. Доля проектной выручки не выделена."],
        ["Сдвиг внедрений у заказчиков может затронуть выручку, если компания продает такие проекты. Доля этой выручки в профиле не выделена."],
        ["Выручка может сдвинуться на следующий квартал. Портфель договоров этого не подтверждает и не опровергает."],
        [],
        ["Проверить пайплайн сделок на ближайший квартал. Его нет в профиле."],
        ["Нет портфеля контрактов и доли выручки от внедрения."],
    )


def _retail(company: dict, news: dict) -> dict:
    move = "1%" if _has(news, "1%") else "отраслевой темп"
    money = format_money(company.get("revenue_rub"))
    attributes = ["Отрасль: розничная торговля."]
    if money:
        attributes.append(f"Выручка профиля: {money}. Она не заменяет сопоставимые продажи сети.")
    return _pack(
        "Отрасль компании — продовольственная розница",
        attributes,
        [f"Замедление оборота продовольственной розницы относится к отрасли компании. Показатель {move} нельзя переносить на выручку сети."],
        ["Сопоставимые продажи могут замедлиться, если сеть похожа на среднюю по рынку. Это не установлено."],
        [],
        ["Сравнить собственные сопоставимые продажи с отраслевой цифрой. Такого показателя в профиле нет."],
        ["Нет сопоставимых продаж и структуры ассортимента."],
    )


def _acquiring(company: dict, news: dict) -> dict:
    return _pack(
        "Компания пользуется эквайрингом",
        ["Банковский продукт: эквайринг. Ставка комиссии компании в профиле не указана."],
        ["Обсуждение комиссии релевантно, потому что эквайринг есть в продуктах. Решение, которое меняло бы расходы, в сюжете не принято."],
        ["Расходы на комиссию могут измениться только после решения. В источнике его нет, поэтому изменения расходов как факта нет."],
        ["Если комиссию ограничат, затраты могут снизиться. Это условие в сюжете не выполнено."],
        ["Поднять фактическую ставку эквайринга и долю безналичного оборота. Этих цифр в профиле нет."],
        ["Ставка эквайринга и доля безналичного оборота не указаны."],
    )


def _grain(company: dict, news: dict) -> dict:
    payments = company.get("payments") or {}
    export = format_pct(payments.get("export_share_of_revenue"))
    usd = format_pct((payments.get("currency_share") or {}).get("USD"))
    attributes = ["Отрасль: сельское хозяйство."]
    if export:
        attributes.append(f"Доля экспорта в выручке: {export}.")
    if usd:
        attributes.append(f"В платежах есть USD: {usd}. Это не размер квоты и не валюта каждого контракта.")
    consequence = "Ужесточение квоты может ограничить экспортный канал."
    if export:
        consequence += f" Доля экспорта {export} показывает подверженность канала, но не объем квоты, поэтому сокращение выручки в процентах не выводится."
    unknowns = ["Размер собственной квоты не указан ни в сюжете, ни в профиле."]
    if not export:
        unknowns.append("Доля экспорта не указана, сила экспортного канала не оценивается.")
    return _pack(
        "Отрасль — сельское хозяйство, сюжет об экспортной квоте на зерно",
        attributes,
        [consequence],
        ["Часть экспортной выручки может стать менее доступной, если компания упирается в квоту. Упирается ли — неизвестно."],
        [],
        ["Сверить выделенную квоту и неисполненные экспортные контракты."],
        unknowns,
    )


def _drought(company: dict, news: dict) -> dict:
    region = company.get("region")
    industry = company.get("industry")
    reasons = []
    attributes = []
    if industry == "Сельское хозяйство":
        reasons.append("отрасль — сельское хозяйство")
        attributes.append("Отрасль: сельское хозяйство.")
    if region and region in set(news.get("regions") or []):
        reasons.append(f"регион {region} указан в сюжете")
        attributes.append(f"Регион компании: {region}.")
    if not reasons:
        reasons.append("совпадение признака сюжета")
    return _pack(
        "Совпадение с сюжетом о влаге: " + ", ".join(reasons),
        attributes or ["Совпадение с сюжетом о влаге есть, но детальных аграрных полей в профиле нет."],
        ["Нехватка влаги может затронуть урожай, если посевы компании находятся в зоне сюжета. Доля таких посевов в профиле не задана."],
        ["Снижение урожайности возможно, но источником не измерено. Сюжет не заменяет агрономическую оценку."],
        [],
        ["Запросить оценку по полям. Ее нет в профиле."],
        ["Структура посевных площадей отсутствует."],
    )


def _fuel(company: dict, news: dict) -> dict:
    move = "4%" if _has(news, "4%") else "изменение цены из сюжета"
    return _pack(
        "Отрасль — транспорт и логистика, сюжет о цене дизеля",
        ["Отрасль: транспорт и логистика. Доля топлива в себестоимости не указана."],
        [f"Рост цены дизеля может увеличить себестоимость перевозчика. Переносить {move} на себестоимость нельзя, пока неизвестна доля топлива."],
        ["Маржа рейсов может сжаться, если в контрактах нет топливной оговорки. Наличие оговорки неизвестно."],
        [],
        ["Проверить топливные оговорки в договорах с заказчиками."],
        ["Доля топлива в себестоимости не указана."],
    )


def _leasing(company: dict, news: dict) -> dict:
    return _pack(
        "В продуктах есть лизинг",
        ["Банковский продукт: лизинг. График платежей в профиле отсутствует."],
        ["Рост предлагаемых ставок лизинга может удорожать новый парк и пролонгации, если договор это предусматривает. На действующий фиксированный график сюжет сам по себе не указывает."],
        ["Платежи по новым договорам могут вырасти. Это не вывод о действующих платежах."],
        [],
        ["Разделить действующий портфель лизинга и планируемые сделки. Графика в профиле нет."],
        ["Нет графика лизинговых платежей и признака плавающей ставки в договорах лизинга."],
    )


BUILDERS = {
    "metal_revenue": _metal_revenue,
    "metal_scrap": _metal_scrap,
    "cny_fx": _cny_fx,
    "cny_export": _cny_export,
    "auto_demand": _auto_demand,
    "debt_service": _debt_service,
    "deposit_rate": _deposit_rate,
    "regional_logistics": _regional,
    "tax_admin": _tax_admin,
    "group_treasury": _group,
    "broad_labor": _broad_labor,
    "it_labor": _it_labor,
    "it_demand": _it_demand,
    "retail_demand": _retail,
    "acquiring_fees": _acquiring,
    "grain_export": _grain,
    "drought": _drought,
    "fuel_cost": _fuel,
    "leasing_rate": _leasing,
}


def evaluate(company: dict, news: dict) -> list[dict]:
    fired = []
    for rule in RULES:
        if not applies(rule, company, news):
            continue
        fired.append(
            {
                "id": rule["id"],
                "title": rule["title"],
                "weight": rule["weight"],
                "topics": list(rule.get("topics_any") or []),
                "effect": BUILDERS[rule["id"]](company, news),
            }
        )
    fired.sort(key=lambda item: item["weight"], reverse=True)
    return fired


def _boost_for(item: dict, boosts: dict[str, float] | None) -> float:
    if not boosts:
        return 1.0
    matched = [boosts[topic] for topic in item.get("topics") or [] if topic in boosts]
    if matched:
        return max(matched)
    return 0.7


def score_of(fired: list[dict], boosts: dict[str, float] | None = None) -> float:
    if not fired:
        return 0.0
    total = sum(item["weight"] * _boost_for(item, boosts) for item in fired)
    return round(min(97, total) / 100, 2)


def level_of(score: float) -> str:
    if score >= 0.40:
        return "высокая"
    if score >= 0.27:
        return "средняя"
    return "низкая"


def rank_news(company: dict, news_list: list[dict], boosts: dict[str, float] | None = None) -> list[dict]:
    ranked = []
    for news in news_list:
        fired = evaluate(company, news)
        score = score_of(fired, boosts)
        if score <= 0:
            continue
        short = ""
        for item in fired:
            if item["effect"]["consequences"]:
                short = item["effect"]["consequences"][0]
                break
        ranked.append(
            {
                "news": news,
                "score": score,
                "level": level_of(score),
                "fired": fired,
                "short": short,
                "reasons": [
                    {"rule_id": item["id"], "weight": round(item["weight"] / 100, 2), "text": item["effect"]["reason"]}
                    for item in fired
                ],
            }
        )
    ranked.sort(key=lambda row: (row["score"], row["news"].get("published_at") or ""), reverse=True)
    return ranked
