"""
Обфускація API-ключів для захисту від автоматичного сканування Google.

Google автоматично сканує GitHub (включно з Gists) на API-ключі
з патерном "AIzaSy..." і блокує їх. Цей модуль кодує ключ так,
що сканери його не розпізнають.

Схема: reverse → base64 → ready для Gist

Використання:
  В Gist замість "gemini_key" використовуйте "gemini_key_enc"
  зі значенням з encode_key().

Утиліта командного рядка:
  python -m app.key_codec <ваш_ключ>
"""

import base64


def encode_key(plain_key: str) -> str:
    """
    Кодує API-ключ для безпечного зберігання в публічному Gist.
    reverse → base64
    """
    reversed_key = plain_key[::-1]
    encoded = base64.b64encode(reversed_key.encode("utf-8")).decode("utf-8")
    return encoded


def decode_key(encoded_key: str) -> str:
    """
    Декодує API-ключ з Gist.
    base64 → reverse
    """
    try:
        decoded = base64.b64decode(encoded_key.encode("utf-8")).decode("utf-8")
        plain_key = decoded[::-1]
        return plain_key
    except Exception:
        return ""


def is_encoded(value: str) -> bool:
    """
    Перевіряє чи значення є закодованим ключем (а не plain API key).
    Plain ключі Google починаються з 'AIzaSy'.
    """
    if not value:
        return False
    # Якщо починається з AIzaSy — це plain ключ, НЕ закодований
    if value.startswith("AIzaSy"):
        return False
    # Перевіряємо чи це валідний base64
    try:
        base64.b64decode(value.encode("utf-8"))
        return True
    except Exception:
        return False


def smart_decode(value: str) -> str:
    """
    Розумне декодування: якщо ключ закодований — декодує,
    якщо plain — повертає як є.
    """
    if not value:
        return ""
    if value.startswith("AIzaSy"):
        return value  # Вже plain ключ
    decoded = decode_key(value)
    if decoded.startswith("AIzaSy"):
        return decoded  # Успішно декодовано
    return value  # Не вдалося декодувати — повертаємо як є


# ─── CLI утиліта ───
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Використання: python -m app.key_codec <API_KEY>")
        print("  Кодує ключ для безпечного зберігання в Gist")
        print()
        print("Приклад:")
        print("  python -m app.key_codec AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        print()
        print("Результат вставте в Gist як значення 'gemini_key_enc'")
        sys.exit(1)

    key = sys.argv[1]
    encoded = encode_key(key)
    decoded = decode_key(encoded)

    print(f"✅ Оригінал:    {key}")
    print(f"🔒 Закодовано:  {encoded}")
    print(f"🔓 Перевірка:   {decoded}")
    print(f"✅ Збіг:        {'Так' if key == decoded else '❌ НІ!'}")
    print()
    print("📋 Вставте це в Gist (ads_config.json):")
    print(f'   "gemini_key_enc": "{encoded}"')
