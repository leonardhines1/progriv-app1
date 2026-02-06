"""Конфігурація програми — константи та GitHub Gist."""

import os
import sys

# ─── GitHub Gist (пульт управління: URL + API key + model) ───
GIST_RAW_URL = "https://gist.githubusercontent.com/okremaosoba/46b3228958b2b0171b993f281426450a/raw/ads_config.json"

# ─── Fallback значення (якщо Gist недоступний і немає збережених) ───
FALLBACK_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbz8GurLgDgaevqszmzETaSjPUJZbpVAwnUmd8fhS30BF2JrAngyj14HL5W-sNRtUX20Mw/exec"
# Закодований ключ (reverse + base64). Використовуйте: python -m app.key_codec <KEY>
# НІКОЛИ не зберігайте plain ключ (AIzaSy...) в коді — Google заблокує його!
FALLBACK_GEMINI_KEY_ENC = ""
FALLBACK_GEMINI_MODEL = "gemini-2.5-flash"

# ─── Версія програми ───
APP_VERSION = "1.0.0"
APP_NAME = "Прогрів"
APP_BUNDLE_ID = "com.progriv.ads"

# ─── Надійна папка для settings (працює і в dev, і в .app) ───
def get_settings_dir() -> str:
    try:
        home = os.path.expanduser("~")
        if sys.platform == "darwin":
            d = os.path.join(home, "Library", "Application Support", APP_NAME)
        else:
            d = os.path.join(home, ".config", APP_NAME)
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SETTINGS_DIR = get_settings_dir()
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

# ─── Надійна кросплатформна папка для output ───
def get_default_output_folder() -> str:
    """
    Повертає надійний абсолютний шлях до папки output.
    macOS:   ~/Documents/ADS_Campaign_Output/
    Windows: %USERPROFILE%\\Documents\\ADS_Campaign_Output\\
    Linux:   ~/Documents/ADS_Campaign_Output/
    Fallback: <app_dir>/output/
    """
    try:
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents")
        # Якщо Documents існує — використовуємо
        if os.path.isdir(docs):
            output = os.path.join(docs, "ADS_Campaign_Output")
            os.makedirs(output, exist_ok=True)
            return output
        # Інакше — в home
        output = os.path.join(home, "ADS_Campaign_Output")
        os.makedirs(output, exist_ok=True)
        return output
    except Exception:
        # Абсолютний fallback — папка біля додатку
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output = os.path.join(app_dir, "output")
        os.makedirs(output, exist_ok=True)
        return output


DEFAULT_OUTPUT_FOLDER = get_default_output_folder()
