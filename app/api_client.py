"""
API Client — зв'язок з Google Sheet через Apps Script Web App
+ GitHub Gist для отримання актуального script_url.
"""

import requests
import json
import time

from app.constants import (
    GIST_RAW_URL, FALLBACK_SCRIPT_URL,
    FALLBACK_GEMINI_KEY_ENC, FALLBACK_GEMINI_MODEL
)
from app.key_codec import smart_decode


class GistResolver:
    """
    Центральний пульт управління через GitHub Gist.
    Отримує: script_url, gemini_key, gemini_model.
    """

    def __init__(self):
        self.gist_url = GIST_RAW_URL
        self.timeout = 10
        self._cached_config: dict = {}

    def fetch_config(self) -> dict:
        """
        Завантажує повний конфіг з Gist.
        Returns: {"script_url": ..., "gemini_key": ..., "gemini_model": ..., "_source": ...}
        """
        # 1. Спробувати Gist
        try:
            resp = requests.get(self.gist_url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            # Пріоритет: gemini_key_enc (закодований) → gemini_key (plain)
            raw_key = data.get("gemini_key_enc", "").strip()
            if not raw_key:
                raw_key = data.get("gemini_key", "").strip()
            gemini_key = smart_decode(raw_key)

            config = {
                "script_url": data.get("script_url", "").strip(),
                "gemini_key": gemini_key,
                "gemini_model": data.get("gemini_model", "").strip(),
                "_source": "gist"
            }
            if config["script_url"]:
                self._cached_config = config
                return config
        except Exception:
            pass

        # 2. Кешований конфіг (якщо Gist був доступний раніше)
        if self._cached_config.get("script_url"):
            return {**self._cached_config, "_source": "cached"}

        # 3. Fallback
        return {
            "script_url": FALLBACK_SCRIPT_URL,
            "gemini_key": smart_decode(FALLBACK_GEMINI_KEY_ENC),
            "gemini_model": FALLBACK_GEMINI_MODEL,
            "_source": "fallback"
        }

    def get_script_url(self, saved_url: str = "") -> tuple:
        """
        Зворотна сумісність: повертає (url, source).
        """
        config = self.fetch_config()
        url = config.get("script_url", "")
        source = config.get("_source", "fallback")
        if url:
            return url, source
        if saved_url:
            return saved_url, "saved"
        return FALLBACK_SCRIPT_URL, "fallback"


class SheetAPI:
    """Клієнт для Google Sheet API (Apps Script doGet/doPost)."""

    def __init__(self, script_url: str, timeout: int = 30):
        self.script_url = script_url.rstrip("/")
        self.timeout = timeout
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 60  # секунд

    # ─── GET запити ───

    def _get(self, action: str, params: dict = None) -> dict:
        """Виконує GET запит до Apps Script."""
        p = {"action": action}
        if params:
            p.update(params)
        try:
            resp = requests.get(self.script_url, params=p, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Timeout — сервер не відповідає"}
        except requests.exceptions.ConnectionError:
            return {"status": "error", "message": "Немає з'єднання з інтернетом"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _get_cached(self, action: str, params: dict = None) -> dict:
        """GET з кешуванням."""
        key = action + json.dumps(params or {}, sort_keys=True)
        now = time.time()
        if key in self._cache and now - self._cache_time.get(key, 0) < self._cache_ttl:
            return self._cache[key]
        result = self._get(action, params)
        if result.get("status") != "error":
            self._cache[key] = result
            self._cache_time[key] = now
        return result

    def clear_cache(self):
        """Очищає кеш."""
        self._cache.clear()
        self._cache_time.clear()

    # ─── POST запити ───

    def _post(self, data: dict) -> dict:
        """Виконує POST запит до Apps Script."""
        try:
            resp = requests.post(
                self.script_url,
                json=data,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Timeout — сервер не відповідає"}
        except requests.exceptions.ConnectionError:
            return {"status": "error", "message": "Немає з'єднання з інтернетом"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ─── Публічні методи ───

    def get_sites(self) -> list:
        """Отримує список сайтів з таблиці."""
        result = self._get_cached("get_sites")
        return result.get("sites", [])

    def get_config(self) -> dict:
        """Отримує конфігурацію з таблиці."""
        result = self._get_cached("get_config")
        if result.get("status") == "error":
            return {}
        # get_config повертає config напряму (не обгорнутий в status)
        config = {k: v for k, v in result.items() if k != "status"}
        return config if config else result

    def get_banned(self) -> list:
        """Отримує список заборонених keywords."""
        result = self._get_cached("get_banned")
        return result.get("banned", [])

    def get_banned_domains(self) -> list:
        """Отримує список заборонених доменів."""
        result = self._get_cached("get_banned_domains")
        return result.get("banned_domains", [])

    def get_version(self) -> str:
        """Отримує версію з таблиці."""
        result = self._get("get_version")
        return result.get("version", "?.?.?")

    def get_all_stats(self) -> dict:
        """Отримує загальну статистику."""
        return self._get("get_all_stats")

    def get_farmer_stats(self, farmer: str) -> dict:
        """Отримує статистику фармера."""
        return self._get("get_farmer_stats", {"farmer": farmer})

    def log_generation(self, farmer: str, site_url: str) -> dict:
        """Логує генерацію CSV."""
        return self._post({
            "action": "log_generation",
            "farmer": farmer,
            "site_url": site_url
        })

    def submit_errors(self, farmer: str, errors: list) -> dict:
        """Відправляє заборонені keywords на модерацію (Pending Changes)."""
        return self._post({
            "action": "submit_errors",
            "farmer": farmer,
            "errors": errors
        })

    def submit_ad_errors(self, farmer: str, errors: list) -> dict:
        """
        Відправляє помилки з Google Ads CSV для самонавчання.
        Keywords автоматично додаються в Banned (обхід Pending).
        Headlines/Descriptions — в Pending для ревʼю.

        errors: [{type, value, reason, original_error, action}, ...]
        action: "auto_ban" | "pending"
        """
        return self._post({
            "action": "submit_ad_errors",
            "farmer": farmer,
            "errors": errors
        })

    def test_connection(self) -> tuple:
        """
        Тестує з'єднання з таблицею.
        Returns: (success: bool, message: str)
        """
        result = self._get("get_version")
        if result.get("status") == "error":
            return False, result.get("message", "Невідома помилка")
        version = result.get("version", "")
        if version:
            return True, f"Підключено! Версія: {version}"
        return True, "Підключено!"

    def sync_all(self) -> dict:
        """
        Синхронізує всі дані з таблиці.
        Returns: dict з sites, config, banned, banned_domains
        """
        self.clear_cache()
        return {
            "sites": self.get_sites(),
            "config": self.get_config(),
            "banned": self.get_banned(),
            "banned_domains": self.get_banned_domains()
        }
