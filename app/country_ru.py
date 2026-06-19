from __future__ import annotations

import re

COUNTRY_RU_NAMES: dict[str, str] = {
    "al":"Албания","dz":"Алжир","ar":"Аргентина","am":"Армения","au":"Австралия",
    "at":"Австрия","az":"Азербайджан","bh":"Бахрейн","bd":"Бангладеш","by":"Беларусь",
    "be":"Бельгия","bo":"Боливия","ba":"Босния и Герцеговина","br":"Бразилия","bg":"Болгария",
    "kh":"Камбоджа","cm":"Камерун","ca":"Канада","cl":"Чили","cn":"Китай",
    "co":"Колумбия","cr":"Коста-Рика","hr":"Хорватия","cy":"Кипр","cz":"Чехия",
    "dk":"Дания","do":"Доминикана","ec":"Эквадор","eg":"Египет","ee":"Эстония",
    "fi":"Финляндия","fr":"Франция","ge":"Грузия","de":"Германия","gh":"Гана",
    "gr":"Греция","gt":"Гватемала","hk":"Гонконг","hu":"Венгрия","is":"Исландия",
    "in":"Индия","id":"Индонезия","ie":"Ирландия","il":"Израиль","it":"Италия",
    "jp":"Япония","jo":"Иордания","kz":"Казахстан","ke":"Кения","kr":"Южная Корея",
    "kw":"Кувейт","kg":"Кыргызстан","lv":"Латвия","lb":"Ливан","lt":"Литва",
    "lu":"Люксембург","my":"Малайзия","mt":"Мальта","mx":"Мексика","md":"Молдова",
    "mn":"Монголия","me":"Черногория","ma":"Марокко","np":"Непал","nl":"Нидерланды",
    "nz":"Новая Зеландия","ng":"Нигерия","mk":"Северная Македония","no":"Норвегия",
    "om":"Оман","pk":"Пакистан","pa":"Панама","py":"Парагвай","pe":"Перу",
    "ph":"Филиппины","pl":"Польша","pt":"Португалия","qa":"Катар","ro":"Румыния",
    "ru":"Россия","sa":"Саудовская Аравия","rs":"Сербия","sg":"Сингапур",
    "sk":"Словакия","si":"Словения","za":"ЮАР","es":"Испания","lk":"Шри-Ланка",
    "se":"Швеция","ch":"Швейцария","tw":"Тайвань","tj":"Таджикистан","th":"Таиланд",
    "tn":"Тунис","tr":"Турция","tm":"Туркменистан","ua":"Украина","ae":"ОАЭ",
    "gb":"Великобритания","us":"США","uy":"Уругвай","uz":"Узбекистан","ve":"Венесуэла",
    "vn":"Вьетнам",
}

COUNTRY_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "ru": ("russia", "россия", "рф"),
    "us": ("usa", "united states", "america", "сша", "америка"),
    "gb": ("uk", "united kingdom", "britain", "england", "великобритания", "англия"),
    "de": ("germany", "германия"),
    "nl": ("netherlands", "holland", "нидерланды", "голландия"),
    "fr": ("france", "франция"),
    "pl": ("poland", "польша"),
    "kz": ("kazakhstan", "казахстан"),
    "ua": ("ukraine", "украина"),
    "tr": ("turkey", "турция"),
    "ae": ("uae", "emirates", "оаэ", "эмираты"),
    "cn": ("china", "китай"),
    "jp": ("japan", "япония"),
    "kr": ("korea", "south korea", "корея", "южная корея"),
}


def country_flag(code: str) -> str:
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🌍"
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def country_ru_name(code: str, fallback: str | None = None) -> str:
    code = (code or "").strip().lower()
    return COUNTRY_RU_NAMES.get(code) or (fallback or code.upper())


def country_display(code: str, fallback: str | None = None) -> str:
    return f"{country_flag(code)} {country_ru_name(code, fallback)}".strip()


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def country_matches(code: str, name: str | None, query: str) -> bool:
    q = _norm(query)
    if not q:
        return True
    code = (code or "").lower()
    haystack = {
        code,
        _norm(code.upper()),
        _norm(name or ""),
        _norm(country_ru_name(code, name)),
        _norm(country_display(code, name)),
    }
    haystack.update(_norm(alias) for alias in COUNTRY_SEARCH_ALIASES.get(code, ()))
    return any(q in item for item in haystack if item)
