"""
Error Parser — розбір CSV-файлів з помилками від Google Ads.

Google Ads Editor експортує CSV з результатами завантаження.
Формат: кожен рядок — це рядок кампанії (Campaign / Ad group / Keyword / Ad),
з колонкою "Results" або "Comment" або "Error" де міститься опис помилки.

Парсер знаходить відхилені рядки і витягує:
- Keywords (з рядків "Keyword") → тип "keyword"
- Headlines (з рядків "Responsive search ad") → тип "headline"
- Descriptions (з рядків "Responsive search ad") → тип "description"

Самонавчальна логіка:
  Відхилене keyword → автоматично додається в Banned таблицю
  Відхилений headline → аналізується причина → патерни додаються в систему
"""

import csv
import os
import re
from typing import NamedTuple


class ParsedError(NamedTuple):
    """Одна розпізнана помилка з файлу."""
    type: str          # "keyword" | "headline" | "description" | "campaign" | "ad_group"
    value: str         # текст помилкового елемента
    reason: str        # причина / текст помилки з Google Ads
    original_error: str  # повний оригінальний текст помилки
    row_type: str      # "Keyword", "Responsive search ad", etc.


class ParseResult(NamedTuple):
    """Результат парсингу всього файлу."""
    errors: list          # list[ParsedError]
    total_rows: int       # всього рядків у файлі
    error_rows: int       # рядків з помилками
    success_rows: int     # успішних рядків
    filename: str         # ім'я файлу
    keywords: list        # list[ParsedError] — тільки keywords
    headlines: list       # list[ParsedError] — тільки headlines
    descriptions: list    # list[ParsedError] — тільки descriptions
    other_errors: list    # list[ParsedError] — інші помилки


# ─── Колонки, де може бути помилка ───
ERROR_COLUMNS = [
    "Results", "Result", "Comment", "Error", "Error Details",
    "Validation Error", "Status", "Policy",
    # Google Ads Editor export columns
    "result", "results", "comment", "error",
]

# ─── Слова, що вказують на помилку ───
ERROR_INDICATORS = [
    "error", "rejected", "disapproved", "policy violation",
    "not eligible", "violation", "invalid", "too long",
    "restricted", "trademark", "misleading", "unacceptable",
    "failed", "couldn't", "couldn't create", "not allowed",
    "limit exceeded", "character limit", "exceeds",
]

# ─── Слова, що вказують на успіх (ігноруємо ці рядки) ───
SUCCESS_INDICATORS = [
    "successfully", "success", "created", "added", "updated",
    "approved", "eligible", "active", "enabled",
]


def _detect_delimiter(filepath: str) -> str:
    """Визначає роздільник CSV (кома, крапка з комою, або таб)."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        sample = f.read(2048)

    # Підрахунок
    counts = {
        ',': sample.count(','),
        ';': sample.count(';'),
        '\t': sample.count('\t'),
    }

    # Якщо табів більше — це TSV
    if counts['\t'] > counts[','] and counts['\t'] > counts[';']:
        return '\t'
    if counts[';'] > counts[',']:
        return ';'
    return ','


def _normalize_header(header: str) -> str:
    """Нормалізує назву колонки для пошуку."""
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _find_error_column(headers: list) -> str | None:
    """Знаходить колонку з помилками серед заголовків."""
    normalized = {_normalize_header(h): h for h in headers}

    # Пріоритетний пошук
    priority = ["results", "result", "error", "error_details",
                 "comment", "validation_error", "policy", "status"]

    for key in priority:
        if key in normalized:
            return normalized[key]

    # Фоллбек: шукаємо будь-яку колонку зі словом error/result/comment
    for norm, orig in normalized.items():
        if any(w in norm for w in ["error", "result", "comment", "policy", "validation"]):
            return orig

    return None


def _is_error_row(error_text: str) -> bool:
    """Чи є цей текст помилкою (а не успіхом)."""
    text_lower = error_text.lower()

    # Якщо є явний індикатор успіху — не помилка
    for s in SUCCESS_INDICATORS:
        if s in text_lower and not any(e in text_lower for e in ["error", "rejected", "disapproved", "violation"]):
            return False

    # Якщо є індикатор помилки — це помилка
    for e in ERROR_INDICATORS:
        if e in text_lower:
            return True

    # Якщо текст не порожній і не схожий на успіх — вважаємо помилкою
    # (Google Ads зазвичай не пише нічого для успішних рядків)
    return len(text_lower.strip()) > 0


def _extract_reason(error_text: str) -> str:
    """Витягує чисту причину з тексту помилки."""
    text = error_text.strip()

    # Якщо є ":" — беремо частину після
    if ": " in text:
        parts = text.split(": ", 1)
        if len(parts[1]) > 10:
            text = parts[1]

    # Скорочуємо до 200 символів
    if len(text) > 200:
        text = text[:200] + "..."

    return text


def _extract_headline_errors(row: dict, error_text: str) -> list:
    """Витягує помилкові headlines з рядка Responsive search ad."""
    errors = []
    error_lower = error_text.lower()
    reason = _extract_reason(error_text)

    for i in range(1, 16):
        col = f"Headline {i}"
        val = (row.get(col) or "").strip()
        if not val:
            continue

        # Перевіряємо чи headline згаданий в помилці
        is_specific = val.lower() in error_lower or f"headline {i}" in error_lower

        # Якщо помилка загальна (policy violation) — додаємо всі headlines
        is_general = any(w in error_lower for w in [
            "policy", "trademark", "misleading", "restricted",
            "disapproved", "rejected"
        ])

        if is_specific or is_general:
            errors.append(ParsedError(
                type="headline",
                value=val,
                reason=reason,
                original_error=error_text,
                row_type="Responsive search ad"
            ))

    return errors


def _extract_description_errors(row: dict, error_text: str) -> list:
    """Витягує помилкові descriptions з рядка Responsive search ad."""
    errors = []
    error_lower = error_text.lower()
    reason = _extract_reason(error_text)

    for i in range(1, 5):
        col = f"Description {i}"
        val = (row.get(col) or "").strip()
        if not val:
            continue

        is_specific = val.lower() in error_lower or f"description {i}" in error_lower
        is_general = any(w in error_lower for w in [
            "policy", "trademark", "misleading", "restricted",
            "disapproved", "rejected"
        ])

        if is_specific or is_general:
            errors.append(ParsedError(
                type="description",
                value=val,
                reason=reason,
                original_error=error_text,
                row_type="Responsive search ad"
            ))

    return errors


def parse_error_csv(filepath: str) -> ParseResult:
    """
    Головна функція: розбирає CSV файл з помилками Google Ads.

    Підтримує формати:
    1. Google Ads Editor — export results (має колонку Results/Error)
    2. Bulk upload results — has Result/Comment column
    3. Наш власний формат CSV (з Row Type, Keyword, Headline тощо)

    Returns: ParseResult з повним аналізом
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Файл не знайдено: {filepath}")

    filename = os.path.basename(filepath)
    delimiter = _detect_delimiter(filepath)

    all_errors = []
    total_rows = 0
    error_rows = 0
    success_rows = 0

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        headers = reader.fieldnames or []

        # Знаходимо колонку з помилками
        error_col = _find_error_column(headers)

        # Якщо немає колонки помилок — це може бути наш CSV без помилок
        # Спробуємо інший підхід: шукаємо колонку "Row Type"
        has_row_type = any(_normalize_header(h) == "row_type" for h in headers)

        for row in reader:
            total_rows += 1

            # Текст помилки
            error_text = ""
            if error_col:
                error_text = (row.get(error_col) or "").strip()

            # Якщо немає колонки помилок і немає Row Type — пропускаємо
            if not error_text and not has_row_type:
                success_rows += 1
                continue

            # Якщо є текст помилки — перевіряємо
            if error_text and not _is_error_row(error_text):
                success_rows += 1
                continue

            if not error_text:
                success_rows += 1
                continue

            # ─── Розбір помилки за типом рядка ───
            error_rows += 1
            row_type = (row.get("Row Type") or row.get("row type") or
                        row.get("Type") or row.get("type") or "").strip()
            reason = _extract_reason(error_text)

            if row_type.lower() in ("keyword", "keywords"):
                kw = (row.get("Keyword") or row.get("keyword") or "").strip()
                if kw:
                    all_errors.append(ParsedError(
                        type="keyword",
                        value=kw,
                        reason=reason,
                        original_error=error_text,
                        row_type=row_type
                    ))

            elif row_type.lower() in ("responsive search ad", "ad", "text ad"):
                # Headlines
                all_errors.extend(_extract_headline_errors(row, error_text))
                # Descriptions
                all_errors.extend(_extract_description_errors(row, error_text))

                # Якщо не знайшли конкретні — додаємо загальну помилку оголошення
                if not _extract_headline_errors(row, error_text) and \
                   not _extract_description_errors(row, error_text):
                    all_errors.append(ParsedError(
                        type="ad",
                        value=f"[{row_type}] Ad error",
                        reason=reason,
                        original_error=error_text,
                        row_type=row_type
                    ))

            elif row_type.lower() in ("campaign",):
                all_errors.append(ParsedError(
                    type="campaign",
                    value=row.get("Campaign") or "Unknown campaign",
                    reason=reason,
                    original_error=error_text,
                    row_type=row_type
                ))

            elif row_type.lower() in ("ad group", "ad_group"):
                all_errors.append(ParsedError(
                    type="ad_group",
                    value=row.get("Ad group") or "Unknown ad group",
                    reason=reason,
                    original_error=error_text,
                    row_type=row_type
                ))

            else:
                # Невідомий тип — все одно зберігаємо
                # Спробуємо знайти keyword у будь-якій колонці
                kw = (row.get("Keyword") or row.get("keyword") or "").strip()
                if kw:
                    all_errors.append(ParsedError(
                        type="keyword",
                        value=kw,
                        reason=reason,
                        original_error=error_text,
                        row_type=row_type or "Unknown"
                    ))
                else:
                    all_errors.append(ParsedError(
                        type="other",
                        value=error_text[:100],
                        reason=reason,
                        original_error=error_text,
                        row_type=row_type or "Unknown"
                    ))

    # ─── Класифікація ───
    keywords = [e for e in all_errors if e.type == "keyword"]
    headlines = [e for e in all_errors if e.type == "headline"]
    descriptions = [e for e in all_errors if e.type == "description"]
    other_errors = [e for e in all_errors if e.type not in ("keyword", "headline", "description")]

    return ParseResult(
        errors=all_errors,
        total_rows=total_rows,
        error_rows=error_rows,
        success_rows=success_rows,
        filename=filename,
        keywords=keywords,
        headlines=headlines,
        descriptions=descriptions,
        other_errors=other_errors,
    )


def errors_to_submission(parsed: ParseResult, action: str = "auto_ban") -> list:
    """
    Конвертує ParseResult у список dict-ів для відправки на Sheet.

    action:
        "auto_ban" — keywords одразу в Banned (обхід Pending)
        "pending"  — keywords в Pending Changes (на модерацію)

    Returns: [{"type": "keyword", "value": "...", "reason": "...",
               "original_error": "...", "action": "auto_ban"}, ...]
    """
    submissions = []
    seen = set()  # дедуплікація

    for error in parsed.errors:
        # Пропускаємо неактуальні типи для бану
        if error.type not in ("keyword", "headline", "description"):
            continue

        key = (error.type, error.value.lower())
        if key in seen:
            continue
        seen.add(key)

        submissions.append({
            "type": error.type,
            "value": error.value,
            "reason": f"Google Ads: {error.reason}",
            "original_error": error.original_error[:500],
            "action": action,
        })

    return submissions


def format_summary(parsed: ParseResult) -> str:
    """Форматує красивий текстовий звіт для GUI."""
    lines = [
        f"📄 Файл: {parsed.filename}",
        f"📊 Всього рядків: {parsed.total_rows}",
        f"✅ Успішних: {parsed.success_rows}",
        f"❌ З помилками: {parsed.error_rows}",
        "",
        f"🔑 Keywords з помилками: {len(parsed.keywords)}",
        f"📝 Headlines з помилками: {len(parsed.headlines)}",
        f"📄 Descriptions з помилками: {len(parsed.descriptions)}",
        f"⚠️ Інші помилки: {len(parsed.other_errors)}",
    ]

    if parsed.keywords:
        lines.append("\n── Відхилені Keywords ──")
        for kw in parsed.keywords[:20]:
            lines.append(f"  🚫 {kw.value}  ←  {kw.reason[:60]}")

    if parsed.headlines:
        lines.append("\n── Відхилені Headlines ──")
        for h in parsed.headlines[:10]:
            lines.append(f"  🚫 {h.value}  ←  {h.reason[:60]}")

    if parsed.descriptions:
        lines.append("\n── Відхилені Descriptions ──")
        for d in parsed.descriptions[:10]:
            lines.append(f"  🚫 {d.value[:50]}...  ←  {d.reason[:60]}")

    total_to_ban = len(parsed.keywords) + len(parsed.headlines) + len(parsed.descriptions)
    lines.append(f"\n🎯 Готово до відправки в Banned: {total_to_ban}")

    return "\n".join(lines)
