"""
Generator — Gemini AI генерація контенту + створення CSV файлу.
Працює з даними з Google Sheet (config, banned, sites).
"""

import os
import json
import csv
import urllib.request
from datetime import datetime, timedelta

from app.constants import DEFAULT_OUTPUT_FOLDER


class AdsGenerator:
    """Генератор Google Ads кампаній."""

    def __init__(self, gemini_api_key: str, output_folder: str = None,
                 gemini_model: str = "gemini-2.5-flash"):
        self.api_key = gemini_api_key
        self.model = gemini_model
        self.output_folder = output_folder or DEFAULT_OUTPUT_FOLDER
        os.makedirs(self.output_folder, exist_ok=True)

    # ─── Фільтрація ───

    @staticmethod
    def filter_keywords(keywords: list, banned: list) -> tuple:
        """
        Фільтрує keywords, видаляючи заборонені.
        Returns: (filtered_list, removed_list)
        """
        banned_lower = [b.lower() for b in banned]
        filtered = []
        removed = []

        for kw in keywords:
            kw_lower = kw.lower().strip()
            is_banned = False
            for b in banned_lower:
                if b in kw_lower or kw_lower in b:
                    is_banned = True
                    break
            if is_banned:
                removed.append(kw)
            else:
                filtered.append(kw)

        return filtered, removed

    @staticmethod
    def filter_by_domains(url: str, banned_domains: list) -> bool:
        """Перевіряє чи домен заборонений."""
        clean = url.lower().replace("https://", "").replace("http://", "").replace("www.", "")
        domain = clean.split("/")[0]
        for bd in banned_domains:
            if bd.lower() in domain or domain in bd.lower():
                return True
        return False

    @staticmethod
    def validate_headlines(headlines: list) -> list:
        """Валідує headlines: макс 30 символів, унікальні."""
        validated = []
        seen = set()
        forbidden = ["best", "cheap", "free", "#1", "guaranteed"]

        for h in headlines:
            h = h.strip()
            if len(h) > 30:
                h = h[:30].rsplit(' ', 1)[0]
            h_lower = h.lower()
            if h_lower in seen:
                continue
            seen.add(h_lower)
            has_banned = any(f in h_lower for f in forbidden)
            if not has_banned and len(h) >= 5:
                validated.append(h)

        return validated[:8]

    @staticmethod
    def validate_descriptions(descriptions: list) -> list:
        """Валідує descriptions: макс 90 символів."""
        validated = []
        for d in descriptions:
            d = d.strip()
            if len(d) > 90:
                d = d[:90].rsplit(' ', 1)[0]
            if len(d) >= 20:
                validated.append(d)
        return validated[:2]

    # ─── Gemini AI ───

    def generate_content(self, website_url: str, business_name: str,
                         on_status=None) -> dict | None:
        """
        Генерує контент через Gemini AI.
        on_status: callback(message: str) для оновлення статусу
        """
        if on_status:
            on_status(f"🤖 Gemini генерує для {business_name}...")

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.api_key}")

        prompt = f"""You are an ELITE Google Ads specialist with 15+ years experience.

TASK: Generate Google Ads Search Campaign content for a FITNESS/GYM business.

BUSINESS INFO:
- Website: {website_url}
- Business name: {business_name}
- Industry: Fitness, Gym, Personal Training
- Location: Washington DC area

STRICT REQUIREMENTS:

📌 KEYWORDS (exactly 10):
   ✅ Specific fitness terms, location + service, brand variations
   ❌ FORBIDDEN: "quality service", "professional team", "best prices", "affordable", "guaranteed", competitor names

📌 HEADLINES (exactly 8, each MAX 30 characters):
   ✅ Action + brand, location + service, benefit
   ❌ FORBIDDEN: "Best", "Cheapest", "#1", "Free" (unless actually free), ALL CAPS

📌 DESCRIPTIONS (exactly 2, each MAX 90 characters):
   ✅ Community, training, sign up CTA
   ❌ FORBIDDEN: "Best prices", "Professional team", "Quality service"

OUTPUT FORMAT (ONLY JSON, no markdown):
{{"keywords": ["kw1", ...], "headlines": ["H1", ...], "descriptions": ["D1", "D2"]}}

Count characters carefully! Headlines MAX 30, Descriptions MAX 90."""

        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 2000}
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                text = result['candidates'][0]['content']['parts'][0]['text']

                # Очищаємо від markdown
                clean_text = text.strip()
                if clean_text.startswith("```"):
                    lines = clean_text.split("\n")
                    json_start = json_end = -1
                    for i, line in enumerate(lines):
                        if line.strip().startswith("{"):
                            json_start = i
                        if line.strip().endswith("}"):
                            json_end = i
                    if json_start >= 0 and json_end >= 0:
                        clean_text = "\n".join(lines[json_start:json_end + 1])

                ads_data = json.loads(clean_text)

                if all(k in ads_data for k in ["keywords", "headlines", "descriptions"]):
                    ads_data["headlines"] = self.validate_headlines(ads_data["headlines"])
                    ads_data["descriptions"] = self.validate_descriptions(ads_data["descriptions"])
                    return ads_data

        except Exception as e:
            if on_status:
                on_status(f"⚠️ Gemini помилка: {e}")

        return None

    # ─── CSV генерація ───

    def generate_csv(self, website_url: str, business_name: str,
                     config: dict, banned: list, banned_domains: list,
                     on_status=None) -> dict:
        """
        Повний цикл: Gemini → фільтрація → CSV.

        Returns: {
            "success": bool,
            "filepath": str,
            "removed_keywords": list,  # заборонені keywords для Pending
            "stats": dict
        }
        """
        result = {
            "success": False,
            "filepath": "",
            "removed_keywords": [],
            "stats": {}
        }

        # Перевірка домену
        if self.filter_by_domains(website_url, banned_domains):
            if on_status:
                on_status(f"🚫 {website_url} — заборонений домен")
            result["stats"]["error"] = "Banned domain"
            return result

        # Генеруємо контент
        content = self.generate_content(website_url, business_name, on_status)
        if not content:
            if on_status:
                on_status(f"❌ Не вдалося згенерувати для {business_name}")
            result["stats"]["error"] = "Gemini failed"
            return result

        # Фільтруємо keywords
        original_kw = content["keywords"][:]
        content["keywords"], removed = self.filter_keywords(content["keywords"], banned)
        result["removed_keywords"] = [{"value": kw, "type": "keyword", "reason": "Generic"} for kw in removed]

        if on_status:
            on_status(f"📊 Keywords: {len(original_kw)} → {len(content['keywords'])} "
                       f"(🚫 {len(removed)} заборонених)")

        # Дефолтні keywords якщо мало
        if len(content["keywords"]) < 5:
            content["keywords"].extend([
                f"{business_name} membership",
                "fitness classes DC",
                "gym membership DC",
                "personal training near me",
                "workout classes DC"
            ])
            content["keywords"] = list(set(content["keywords"]))[:10]

        # Дефолтні headlines/descriptions
        short_name = business_name[:27] + "..." if len(business_name) > 30 else business_name
        if len(content["headlines"]) < 3:
            content["headlines"] = [
                f"Join {short_name} Today",
                "Start Your Fitness Journey",
                "Transform Your Body Now"
            ]
        if len(content["descriptions"]) < 2:
            content["descriptions"] = [
                f"Join {business_name}. Expert trainers & flexible memberships. Start today!",
                "Transform your fitness with our community. Personal & group training available."
            ]

        # Конфіг
        budget = config.get("budget", "10")
        bid_strategy = config.get("bid_strategy", "Maximize Conversions")
        networks = config.get("networks", "Google Search")
        location = config.get("target_country", "United States")
        language = config.get("target_language", "en")
        eu_political = config.get("eu_political_ads", "No")
        match_type_raw = config.get("keyword_match_type", "Broad match")
        # Google Ads Editor приймає: Broad, Phrase, Exact (без слова "match")
        match_type = match_type_raw.replace(" match", "").replace(" Match", "")
        campaign_days = int(config.get("campaign_days", "7") or "7")

        # Дати
        today = datetime.now()
        start_date = today.strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=campaign_days)).strftime("%Y-%m-%d")

        # Назви
        timestamp = today.strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in business_name)
        filename = f"ads_{safe_name}_{timestamp}.csv"
        filepath = os.path.join(self.output_folder, filename)

        campaign_name = f"{business_name} - Search Campaign"
        ad_group_name = f"{business_name} - Main"

        # ─── Будуємо рядки ───
        # Google Ads Editor визначає тип рядка за заповненими колонками,
        # тому НЕ використовуємо "Row Type" — він не підтримується.
        # Кожен рядок просто заповнює відповідні стовпці.

        rows = []

        # Campaign row — заповнюємо Campaign-level поля
        rows.append({
            "Campaign": campaign_name,
            "Campaign status": "Enabled",
            "Campaign type": "Search",
            "Networks": networks,
            "Budget": budget,
            "Bid strategy type": bid_strategy,
            "Start date": start_date,
            "End date": end_date,
            "Location": location,
            "Language": language,
            "EU political ads": eu_political,
        })

        # Ad Group row — кампанія + група
        rows.append({
            "Campaign": campaign_name,
            "Ad group": ad_group_name,
            "Ad group status": "Enabled",
        })

        # Keyword rows
        for kw in content["keywords"][:10]:
            rows.append({
                "Campaign": campaign_name,
                "Ad group": ad_group_name,
                "Keyword": kw,
                "Keyword match type": match_type,
            })

        # Responsive Search Ad row — headlines + descriptions
        final_url = website_url if website_url.startswith("http") else f"https://{website_url}"
        ad_row = {
            "Campaign": campaign_name,
            "Ad group": ad_group_name,
            "Ad type": "Responsive search ad",
            "Ad status": "Enabled",
            "Final URL": final_url,
        }
        for i, h in enumerate(content["headlines"][:8], 1):
            ad_row[f"Headline {i}"] = h[:30]
        for i, d in enumerate(content["descriptions"][:2], 1):
            ad_row[f"Description {i}"] = d[:90]
        rows.append(ad_row)

        # ─── Записуємо CSV ───
        all_columns = set()
        for row in rows:
            all_columns.update(row.keys())

        # Порядок стовпців відповідає Google Ads Editor
        priority = [
            "Campaign", "Campaign status", "Campaign type",
            "Networks", "Budget", "Bid strategy type",
            "Start date", "End date", "Location", "Language",
            "EU political ads",
            "Ad group", "Ad group status",
            "Keyword", "Keyword match type",
            "Ad type", "Ad status", "Final URL"
        ]
        for i in range(1, 16):
            priority.append(f"Headline {i}")
        for i in range(1, 5):
            priority.append(f"Description {i}")

        columns = [c for c in priority if c in all_columns]
        columns.extend(sorted(all_columns - set(columns)))

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        if on_status:
            on_status(f"✅ CSV: {filename}")

        result["success"] = True
        result["filepath"] = filepath
        result["stats"] = {
            "keywords": len(content["keywords"]),
            "headlines": len(content["headlines"]),
            "descriptions": len(content["descriptions"]),
            "removed": len(removed),
            "campaign": campaign_name,
            "dates": f"{start_date} → {end_date}"
        }

        return result
