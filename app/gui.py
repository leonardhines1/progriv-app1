"""
GUI — головний інтерфейс програми (CustomTkinter).
Вкладки: Аккаунт | Генерація | Статистика | Налаштування
"""

import os
import sys
import json
import threading
import customtkinter as ctk
from datetime import datetime
from tkinter import filedialog, messagebox

from app.api_client import SheetAPI, GistResolver
from app.generator import AdsGenerator
from app.error_parser import parse_error_csv, errors_to_submission, format_summary
from app.constants import APP_NAME, APP_VERSION, DEFAULT_OUTPUT_FOLDER, SETTINGS_FILE

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """Головне вікно програми."""

    def __init__(self):
        super().__init__()

        # Розміри
        self.geometry("1050x750")
        self.minsize(900, 650)

        # Title (after(0) щоб уникнути crash з кирилицею в PyInstaller bundle)
        self.after(0, lambda: self.title(APP_NAME))

        # Дані
        self.api: SheetAPI | None = None
        self.generator: AdsGenerator | None = None
        self.gist = GistResolver()
        self.sites: list = []
        self.config: dict = {}
        self.banned: list = []
        self.banned_domains: list = []
        self.site_vars: dict = {}  # url → BooleanVar
        self.is_generating = False
        self.is_connected = False

        # Налаштування
        self.settings = self._load_settings()

        # Побудова UI
        self._build_ui()

        # Автопідключення
        self.after(500, self._startup_sequence)

    # ─────────────────────────────────────────
    #  SETTINGS (локальний файл)
    # ─────────────────────────────────────────

    def _load_settings(self) -> dict:
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, **kwargs):
        """Зберігає налаштування. Можна передати окремі поля."""
        for k, v in kwargs.items():
            self.settings[k] = v
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _get_farmer_tag(self) -> str:
        return self.settings.get("farmer_tag", "").strip()

    def _is_tag_locked(self) -> bool:
        return self.settings.get("tag_locked", False)

    # ─────────────────────────────────────────
    #  BUILD UI
    # ─────────────────────────────────────────

    def _build_ui(self):
        # Основна сітка
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ─── Sidebar ───
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        # Logo
        self.lbl_logo = ctk.CTkLabel(
            self.sidebar, text="📊 ADS Tool",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        self.lbl_logo.pack(pady=(25, 5))

        self.lbl_version = ctk.CTkLabel(
            self.sidebar, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=12), text_color="gray"
        )
        self.lbl_version.pack(pady=(0, 20))

        # Tabs
        self.btn_tab_account = ctk.CTkButton(
            self.sidebar, text="🏷️ Аккаунт", command=lambda: self._show_tab("account"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=40
        )
        self.btn_tab_account.pack(fill="x", padx=10, pady=2)

        self.btn_tab_generate = ctk.CTkButton(
            self.sidebar, text="🚀 Генерація", command=lambda: self._show_tab("generate"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=40
        )
        self.btn_tab_generate.pack(fill="x", padx=10, pady=2)

        self.btn_tab_stats = ctk.CTkButton(
            self.sidebar, text="📈 Статистика", command=lambda: self._show_tab("stats"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=40
        )
        self.btn_tab_stats.pack(fill="x", padx=10, pady=2)

        self.btn_tab_settings = ctk.CTkButton(
            self.sidebar, text="⚙️ Налаштування", command=lambda: self._show_tab("settings"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=40
        )
        self.btn_tab_settings.pack(fill="x", padx=10, pady=2)

        self.btn_tab_feedback = ctk.CTkButton(
            self.sidebar, text="📤 Feedback", command=lambda: self._show_tab("feedback"),
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), anchor="w", height=40
        )
        self.btn_tab_feedback.pack(fill="x", padx=10, pady=2)

        # Статус підключення
        self.lbl_status = ctk.CTkLabel(
            self.sidebar, text="⚪ Не підключено",
            font=ctk.CTkFont(size=12), text_color="gray"
        )
        self.lbl_status.pack(side="bottom", pady=(0, 15))

        self.btn_sync = ctk.CTkButton(
            self.sidebar, text="🔄 Синхронізація", command=self._sync,
            fg_color="transparent", border_width=1, height=32
        )
        self.btn_sync.pack(side="bottom", fill="x", padx=10, pady=(0, 5))

        # Тег фармера в sidebar
        self.lbl_farmer_sidebar = ctk.CTkLabel(
            self.sidebar, text="",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.lbl_farmer_sidebar.pack(side="bottom", pady=(0, 8))
        self._update_sidebar_tag()

        # ─── Main content ───
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Tabs frames
        self.tabs = {}
        self._build_account_tab()
        self._build_generate_tab()
        self._build_stats_tab()
        self._build_settings_tab()
        self._build_feedback_tab()

        # Показуємо стартовий таб
        if self._is_tag_locked() or self._is_dev_mode():
            self._show_tab("generate")
        else:
            self._show_tab("account")

    # ─────────────────────────────────────────
    #  TAB: ACCOUNT (Аккаунт / Тег)
    # ─────────────────────────────────────────

    def _build_account_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.tabs["account"] = frame

        # Заголовок
        ctk.CTkLabel(frame, text="🏷️ Аккаунт",
                      font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10), anchor="w", padx=30)

        ctk.CTkLabel(frame, text="Ваш тег — це унікальний ідентифікатор фармера в системі.\n"
                                  "Вводиться один раз і не може бути змінений.",
                      font=ctk.CTkFont(size=13), text_color="gray",
                      justify="left").pack(anchor="w", padx=30, pady=(0, 20))

        # Контейнер
        self.account_container = ctk.CTkFrame(frame)
        self.account_container.pack(fill="x", padx=30, pady=(0, 15))

        if self._is_tag_locked():
            self._show_locked_tag()
        elif self._is_dev_mode():
            self._show_dev_tag()
        else:
            self._show_tag_input()

    def _show_tag_input(self):
        """Показує поле для введення тега (ще не залочений)."""
        for w in self.account_container.winfo_children():
            w.destroy()

        ctk.CTkLabel(self.account_container, text="Введіть ваш тег:",
                      font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=20, pady=(20, 5))

        ctk.CTkLabel(self.account_container,
                      text="⚠️ Увага! Після збереження тег буде заблокований назавжди.",
                      font=ctk.CTkFont(size=12), text_color="#ffc107").pack(anchor="w", padx=20, pady=(0, 10))

        self.entry_tag = ctk.CTkEntry(
            self.account_container,
            placeholder_text="Наприклад: John_DC, Farmer_01...",
            height=42, font=ctk.CTkFont(size=15)
        )
        self.entry_tag.pack(fill="x", padx=20, pady=(0, 15))

        # Якщо вже є збережений незалочений тег
        saved = self._get_farmer_tag()
        if saved:
            self.entry_tag.insert(0, saved)

        self.btn_save_tag = ctk.CTkButton(
            self.account_container, text="🔒 Зберегти тег назавжди",
            height=42, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#dc3545", hover_color="#c82333",
            command=self._lock_tag
        )
        self.btn_save_tag.pack(padx=20, pady=(0, 10), anchor="w")

        # Dev mode кнопка
        self.btn_dev_mode = ctk.CTkButton(
            self.account_container, text="🧪 Dev Mode (тестування без статистики)",
            height=36, font=ctk.CTkFont(size=12),
            fg_color="transparent", border_width=1,
            text_color=("gray40", "gray60"),
            hover_color=("gray85", "gray25"),
            command=self._enter_dev_mode
        )
        self.btn_dev_mode.pack(padx=20, pady=(0, 20), anchor="w")

    def _show_locked_tag(self):
        """Показує залочений тег."""
        for w in self.account_container.winfo_children():
            w.destroy()

        tag = self._get_farmer_tag()

        # Іконка замка + тег
        tag_row = ctk.CTkFrame(self.account_container, fg_color="transparent")
        tag_row.pack(fill="x", padx=20, pady=(25, 10))

        ctk.CTkLabel(tag_row, text="🔒",
                      font=ctk.CTkFont(size=28)).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(tag_row, text=tag,
                      font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")

        # Статус
        ctk.CTkLabel(self.account_container,
                      text="✅ Тег збережений та заблокований",
                      font=ctk.CTkFont(size=14), text_color="#28a745").pack(anchor="w", padx=20, pady=(5, 5))

        ctk.CTkLabel(self.account_container,
                      text="Для зміни тега зверніться до адміністратора.",
                      font=ctk.CTkFont(size=12), text_color="gray").pack(anchor="w", padx=20, pady=(0, 25))

    def _lock_tag(self):
        """Блокує тег назавжди."""
        tag = self.entry_tag.get().strip()

        if not tag:
            messagebox.showwarning("Помилка", "Введіть тег!")
            return

        if len(tag) < 2:
            messagebox.showwarning("Помилка", "Тег занадто короткий (мінімум 2 символи)")
            return

        # Підтвердження
        confirm = messagebox.askyesno(
            "⚠️ Підтвердження",
            f"Ви впевнені що хочете зберегти тег:\n\n"
            f"   🏷️  {tag}\n\n"
            f"Після збереження тег не можна буде змінити!",
            icon="warning"
        )

        if not confirm:
            return

        # Зберігаємо і лочимо
        self._save_settings(farmer_tag=tag, tag_locked=True)
        self._show_locked_tag()
        self._update_sidebar_tag()

        # Автопідключення якщо ще не підключені
        if not self.is_connected:
            self._startup_sequence()

    def _enter_dev_mode(self):
        """Вмикає Dev Mode — тестовий тег без статистики."""
        self._save_settings(farmer_tag="_DEV_", tag_locked=False)
        self._show_dev_tag()
        self._update_sidebar_tag()
        self._show_tab("generate")

    def _show_dev_tag(self):
        """Показує Dev Mode стан в Account."""
        for w in self.account_container.winfo_children():
            w.destroy()

        # Dev іконка + тег
        tag_row = ctk.CTkFrame(self.account_container, fg_color="transparent")
        tag_row.pack(fill="x", padx=20, pady=(25, 10))

        ctk.CTkLabel(tag_row, text="🧪",
                      font=ctk.CTkFont(size=28)).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(tag_row, text="DEV MODE",
                      font=ctk.CTkFont(size=24, weight="bold"),
                      text_color="#ffc107").pack(side="left")

        ctk.CTkLabel(self.account_container,
                      text="⚠️ Тестовий режим — генерація працює,\n"
                           "але статистика НЕ записується в таблицю.",
                      font=ctk.CTkFont(size=13), text_color="#ffc107",
                      justify="left").pack(anchor="w", padx=20, pady=(5, 10))

        ctk.CTkButton(
            self.account_container, text="🔙 Вийти з Dev Mode",
            height=36, fg_color="transparent", border_width=1,
            command=self._exit_dev_mode
        ).pack(padx=20, pady=(5, 20), anchor="w")

    def _exit_dev_mode(self):
        """Виходить з Dev Mode."""
        self._save_settings(farmer_tag="", tag_locked=False)
        self._show_tag_input()
        self._update_sidebar_tag()

    def _update_sidebar_tag(self):
        """Оновлює відображення тега в sidebar."""
        tag = self._get_farmer_tag()
        if tag:
            if self._is_dev_mode():
                self.lbl_farmer_sidebar.configure(text=f"🧪 DEV MODE")
            else:
                self.lbl_farmer_sidebar.configure(text=f"👤 {tag}")
        else:
            self.lbl_farmer_sidebar.configure(text="")

    # ─────────────────────────────────────────
    #  TAB: SETTINGS (Налаштування)
    # ─────────────────────────────────────────

    def _build_settings_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.tabs["settings"] = frame

        # Заголовок
        ctk.CTkLabel(frame, text="⚙️ Налаштування",
                      font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 25), anchor="w", padx=30)

        # Контейнер
        container = ctk.CTkFrame(frame)
        container.pack(fill="x", padx=30, pady=(0, 15))

        # Output folder
        ctk.CTkLabel(container, text="Папка для CSV:",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=(15, 3))

        output_row = ctk.CTkFrame(container, fg_color="transparent")
        output_row.pack(fill="x", padx=20, pady=(0, 15))
        output_row.grid_columnconfigure(0, weight=1)

        self.entry_output = ctk.CTkEntry(output_row, placeholder_text=DEFAULT_OUTPUT_FOLDER, height=38)
        self.entry_output.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(output_row, text="📁", width=45, height=38,
                       command=self._pick_output_folder).grid(row=0, column=1)

        # Кнопка збереження
        ctk.CTkButton(container, text="💾 Зберегти", height=42,
                       font=ctk.CTkFont(size=14, weight="bold"),
                       command=self._save_settings_from_ui).pack(padx=20, pady=(5, 15), anchor="w")

        # Інфо
        self.lbl_settings_info = ctk.CTkLabel(frame, text="",
                                               font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_settings_info.pack(anchor="w", padx=30, pady=(0, 10))

        # Інформація про підключення
        info_frame = ctk.CTkFrame(frame)
        info_frame.pack(fill="x", padx=30, pady=(10, 15))

        ctk.CTkLabel(info_frame, text="📡 Інформація про підключення",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=(15, 8))

        self.lbl_connection_info = ctk.CTkLabel(
            info_frame, text="Очікування підключення...",
            font=ctk.CTkFont(size=12, family="Menlo"), text_color="gray",
            justify="left"
        )
        self.lbl_connection_info.pack(anchor="w", padx=20, pady=(0, 15))

        # Заповнюємо збережені значення
        output = self.settings.get("output_folder", DEFAULT_OUTPUT_FOLDER)
        self.entry_output.insert(0, output)

    def _save_settings_from_ui(self):
        """Зберігає налаштування з UI полів."""
        output = self.entry_output.get().strip() or DEFAULT_OUTPUT_FOLDER

        self._save_settings(output_folder=output)
        self.lbl_settings_info.configure(text="✅ Збережено!", text_color="#28a745")

        # Оновлюємо генератор якщо потрібно
        if self.is_connected:
            gemini_key = self.settings.get("gemini_key", "")
            gemini_model = self.settings.get("gemini_model", "gemini-2.5-flash")
            if gemini_key:
                self.generator = AdsGenerator(gemini_key, output, gemini_model)

    # ─────────────────────────────────────────
    #  TAB: GENERATE
    # ─────────────────────────────────────────

    def _build_generate_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.tabs["generate"] = frame

        # Заголовок
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(20, 10))

        ctk.CTkLabel(header, text="🚀 Генерація рекламних кампаній",
                      font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")

        self.btn_refresh_sites = ctk.CTkButton(
            header, text="🔄", width=40, height=32,
            fg_color="transparent", border_width=1,
            command=self._refresh_sites
        )
        self.btn_refresh_sites.pack(side="right", padx=(0, 8))

        # ─── Перемикач режиму ───
        self.gen_mode = ctk.StringVar(value="random")
        self.gen_mode_switcher = ctk.CTkSegmentedButton(
            frame,
            values=["🎲 Випадковий сайт", "✅ Вибрати сайти"],
            command=self._set_gen_mode,
            font=ctk.CTkFont(size=14, weight="bold"),
            selected_color="#2d6a4f", selected_hover_color="#40916c",
        )
        self.gen_mode_switcher.set("🎲 Випадковий сайт")
        self.gen_mode_switcher.pack(fill="x", padx=30, pady=(0, 10))

        # ─── Контейнер «Випадковий сайт» ───
        self.random_site_frame = ctk.CTkFrame(frame, fg_color="#1a1a2e", corner_radius=12)
        self.lbl_random_info = ctk.CTkLabel(
            self.random_site_frame,
            text="⏳ Завантаження сайтів...",
            font=ctk.CTkFont(size=15),
            text_color="#b0b0b0",
        )
        self.lbl_random_info.pack(pady=40)
        # покажемо за замовчуванням
        self.random_site_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))

        # ─── Контейнер «Вибрати сайти» (прихований) ───
        self.pick_sites_wrapper = ctk.CTkFrame(frame, fg_color="transparent")
        # НЕ pack — покажемо через _set_gen_mode

        self.pick_header = ctk.CTkFrame(self.pick_sites_wrapper, fg_color="transparent")
        self.pick_header.pack(fill="x")

        self.btn_select_all = ctk.CTkButton(
            self.pick_header, text="Обрати всі", width=110, height=32,
            fg_color="transparent", border_width=1,
            command=self._toggle_all_sites
        )
        self.btn_select_all.pack(side="right")

        self.sites_frame = ctk.CTkScrollableFrame(
            self.pick_sites_wrapper, label_text="📋 Сайти з таблиці"
        )
        self.sites_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.lbl_no_sites = ctk.CTkLabel(
            self.sites_frame,
            text="Зачекайте, підключення до таблиці...",
            text_color="gray"
        )
        self.lbl_no_sites.pack(pady=30)

        # ─── Нижня панель ───
        bottom = ctk.CTkFrame(frame)
        bottom.pack(fill="x", padx=30, pady=(0, 10))
        bottom.grid_columnconfigure(1, weight=1)

        # Вибрано
        self.lbl_selected = ctk.CTkLabel(bottom, text="Обрано: 0 сайтів",
                                          font=ctk.CTkFont(size=13))
        self.lbl_selected.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        # Прогрес
        self.progress = ctk.CTkProgressBar(bottom)
        self.progress.grid(row=0, column=1, padx=10, pady=12, sticky="ew")
        self.progress.set(0)

        # Кнопка генерації
        self.btn_generate = ctk.CTkButton(
            bottom, text="▶ Генерувати", height=42, width=170,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#28a745", hover_color="#218838",
            command=self._start_generation
        )
        self.btn_generate.grid(row=0, column=2, padx=(10, 15), pady=12)

        # ─── Лог ───
        self.log_frame = ctk.CTkFrame(frame)
        self.log_frame.pack(fill="x", padx=30, pady=(0, 15))

        self.log_text = ctk.CTkTextbox(self.log_frame, height=140,
                                        font=ctk.CTkFont(family="Menlo", size=12))
        self.log_text.pack(fill="both", expand=True, padx=2, pady=2)
        self._log("Очікування підключення до таблиці...")

    # ─────────────────────────────────────────
    #  TAB: STATS
    # ─────────────────────────────────────────

    def _build_stats_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.tabs["stats"] = frame

        ctk.CTkLabel(frame, text="📈 Статистика",
                      font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 15), anchor="w", padx=30)

        # Кнопка оновлення
        ctk.CTkButton(frame, text="🔄 Оновити статистику", height=36,
                       fg_color="transparent", border_width=1,
                       command=self._load_stats).pack(anchor="w", padx=30, pady=(0, 15))

        # Контейнер зі стат-картками
        self.stats_container = ctk.CTkScrollableFrame(frame, label_text="Ваша статистика")
        self.stats_container.pack(fill="both", expand=True, padx=30, pady=(0, 15))

        self.lbl_no_stats = ctk.CTkLabel(
            self.stats_container,
            text="Натисніть 🔄 щоб завантажити статистику",
            text_color="gray"
        )
        self.lbl_no_stats.pack(pady=30)

    # ─────────────────────────────────────────
    #  TAB: FEEDBACK (Google Ads помилки)
    # ─────────────────────────────────────────

    def _build_feedback_tab(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.tabs["feedback"] = frame

        # Стан
        self.feedback_parsed = None  # ParseResult
        self.feedback_filepath = None

        # Заголовок
        ctk.CTkLabel(frame, text="📤 Google Ads Feedback",
                      font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 5), anchor="w", padx=30)

        ctk.CTkLabel(frame, text="Завантажте CSV з помилками від Google Ads.\n"
                                  "Відхилені keywords автоматично додаються в Banned (самонавчання).",
                      font=ctk.CTkFont(size=13), text_color="gray",
                      justify="left").pack(anchor="w", padx=30, pady=(0, 15))

        # ─── Drop Zone (візуальна зона + кнопка) ───
        self.drop_zone = ctk.CTkFrame(frame, height=120, border_width=2,
                                       border_color=("gray60", "gray40"),
                                       fg_color=("gray90", "gray17"))
        self.drop_zone.pack(fill="x", padx=30, pady=(0, 10))
        self.drop_zone.pack_propagate(False)

        # Іконка та текст
        self.lbl_drop_icon = ctk.CTkLabel(
            self.drop_zone, text="📂",
            font=ctk.CTkFont(size=36)
        )
        self.lbl_drop_icon.pack(pady=(15, 5))

        self.lbl_drop_text = ctk.CTkLabel(
            self.drop_zone, text="Натисніть щоб обрати CSV файл з помилками",
            font=ctk.CTkFont(size=14), text_color="gray"
        )
        self.lbl_drop_text.pack(pady=(0, 5))

        self.lbl_drop_file = ctk.CTkLabel(
            self.drop_zone, text="",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#2196F3"
        )
        self.lbl_drop_file.pack(pady=(0, 10))

        # Клікабельна зона
        self.drop_zone.bind("<Button-1>", lambda e: self._pick_error_csv())
        self.lbl_drop_icon.bind("<Button-1>", lambda e: self._pick_error_csv())
        self.lbl_drop_text.bind("<Button-1>", lambda e: self._pick_error_csv())
        self.lbl_drop_file.bind("<Button-1>", lambda e: self._pick_error_csv())

        # Hover ефект
        def on_enter(e):
            self.drop_zone.configure(border_color="#2196F3")
        def on_leave(e):
            self.drop_zone.configure(border_color=("gray60", "gray40"))
        self.drop_zone.bind("<Enter>", on_enter)
        self.drop_zone.bind("<Leave>", on_leave)

        # ─── Результати парсингу ───
        self.feedback_result_frame = ctk.CTkFrame(frame)
        self.feedback_result_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))

        self.feedback_text = ctk.CTkTextbox(
            self.feedback_result_frame, height=200,
            font=ctk.CTkFont(family="Menlo", size=12)
        )
        self.feedback_text.pack(fill="both", expand=True, padx=2, pady=2)
        self.feedback_text.insert("end", "Оберіть CSV файл з результатами завантаження Google Ads.\n\n"
                                          "Що відбувається:\n"
                                          "  🔑 Відхилені Keywords → автоматично в Banned\n"
                                          "  📝 Відхилені Headlines → в Pending Changes\n"
                                          "  📄 Відхилені Descriptions → в Pending Changes\n\n"
                                          "Система вчиться на кожній помилці і більше не генерує\n"
                                          "контент з забороненими словами.")
        self.feedback_text.configure(state="disabled")

        # ─── Нижня панель ───
        bottom = ctk.CTkFrame(frame)
        bottom.pack(fill="x", padx=30, pady=(0, 15))
        bottom.grid_columnconfigure(0, weight=1)

        self.lbl_feedback_status = ctk.CTkLabel(
            bottom, text="", font=ctk.CTkFont(size=13), text_color="gray"
        )
        self.lbl_feedback_status.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.btn_submit_errors = ctk.CTkButton(
            bottom, text="🚀 Відправити в Banned", height=42, width=200,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#dc3545", hover_color="#c82333",
            command=self._submit_ad_errors, state="disabled"
        )
        self.btn_submit_errors.grid(row=0, column=1, padx=(10, 15), pady=10)

    def _pick_error_csv(self):
        """Вибір CSV файлу з помилками Google Ads."""
        filepath = filedialog.askopenfilename(
            title="Оберіть CSV з помилками Google Ads",
            filetypes=[
                ("CSV files", "*.csv"),
                ("TSV files", "*.tsv"),
                ("All files", "*.*")
            ]
        )
        if not filepath:
            return

        self.feedback_filepath = filepath
        filename = os.path.basename(filepath)
        self.lbl_drop_file.configure(text=f"📄 {filename}")
        self.lbl_drop_text.configure(text="Файл обрано. Аналіз...")
        self.lbl_drop_icon.configure(text="⏳")

        # Парсимо в окремому потоці
        def do_parse():
            try:
                parsed = parse_error_csv(filepath)
                self.after(0, lambda: self._on_csv_parsed(parsed))
            except Exception as e:
                self.after(0, lambda: self._on_csv_parse_error(str(e)))

        threading.Thread(target=do_parse, daemon=True).start()

    def _on_csv_parsed(self, parsed):
        """Callback після парсингу CSV."""
        self.feedback_parsed = parsed

        # Оновлюємо drop zone
        self.lbl_drop_icon.configure(text="✅")
        self.lbl_drop_text.configure(text="Файл проаналізовано! Натисніть для іншого файлу")

        # Показуємо результати
        summary = format_summary(parsed)
        self.feedback_text.configure(state="normal")
        self.feedback_text.delete("1.0", "end")
        self.feedback_text.insert("end", summary)
        self.feedback_text.configure(state="disabled")

        # Оновлюємо статус
        total_to_ban = len(parsed.keywords) + len(parsed.headlines) + len(parsed.descriptions)
        if total_to_ban > 0:
            self.lbl_feedback_status.configure(
                text=f"🎯 {total_to_ban} елементів готово до відправки",
                text_color="#ffc107"
            )
            self.btn_submit_errors.configure(state="normal")
        else:
            self.lbl_feedback_status.configure(
                text="✅ Помилок не знайдено — всі рядки успішні!",
                text_color="#28a745"
            )
            self.btn_submit_errors.configure(state="disabled")

    def _on_csv_parse_error(self, error_msg: str):
        """Callback при помилці парсингу."""
        self.feedback_parsed = None
        self.lbl_drop_icon.configure(text="❌")
        self.lbl_drop_text.configure(text="Помилка! Натисніть для іншого файлу")

        self.feedback_text.configure(state="normal")
        self.feedback_text.delete("1.0", "end")
        self.feedback_text.insert("end", f"❌ Помилка парсингу:\n\n{error_msg}\n\n"
                                          "Переконайтесь що це CSV файл з результатами\n"
                                          "завантаження Google Ads.")
        self.feedback_text.configure(state="disabled")
        self.btn_submit_errors.configure(state="disabled")
        self.lbl_feedback_status.configure(text="", text_color="gray")

    def _submit_ad_errors(self):
        """Відправляє розпізнані помилки на сервер."""
        if not self.feedback_parsed:
            messagebox.showwarning("Помилка", "Спочатку оберіть CSV файл")
            return

        if not self.is_connected or not self.api:
            messagebox.showwarning("Помилка", "Немає підключення до таблиці")
            return

        farmer = self._get_farmer_tag()
        if not farmer:
            messagebox.showwarning("Помилка", "Збережіть тег в Аккаунті")
            return

        # Підтвердження
        parsed = self.feedback_parsed
        kw_count = len(parsed.keywords)
        h_count = len(parsed.headlines)
        d_count = len(parsed.descriptions)
        total = kw_count + h_count + d_count

        confirm = messagebox.askyesno(
            "📤 Підтвердження",
            f"Відправити помилки для самонавчання?\n\n"
            f"🔑 Keywords → Banned: {kw_count}\n"
            f"📝 Headlines → Pending: {h_count}\n"
            f"📄 Descriptions → Pending: {d_count}\n"
            f"{'─'*30}\n"
            f"Всього: {total}\n\n"
            f"Keywords будуть АВТОМАТИЧНО додані в Banned!",
            icon="warning"
        )

        if not confirm:
            return

        # Відправка
        self.btn_submit_errors.configure(state="disabled", text="⏳ Відправка...")
        self.lbl_feedback_status.configure(text="🔄 Відправка...", text_color="yellow")

        def do_submit():
            try:
                submissions = errors_to_submission(parsed, action="auto_ban")
                result = self.api.submit_ad_errors(farmer, submissions)
                self.after(0, lambda: self._on_submit_done(result))
            except Exception as e:
                self.after(0, lambda: self._on_submit_error(str(e)))

        threading.Thread(target=do_submit, daemon=True).start()

    def _on_submit_done(self, result: dict):
        """Callback після відправки помилок."""
        self.btn_submit_errors.configure(text="🚀 Відправити в Banned")

        if result.get("status") == "ok":
            auto_banned = result.get("auto_banned", 0)
            pending = result.get("pending_added", 0)
            duplicates = result.get("duplicates", 0)

            self.lbl_feedback_status.configure(
                text=f"✅ Готово! Banned: +{auto_banned} | Pending: +{pending} | Дублікати: {duplicates}",
                text_color="#28a745"
            )

            # Оновлюємо результати
            self.feedback_text.configure(state="normal")
            self.feedback_text.insert("end", f"\n\n{'='*40}\n"
                                              f"✅ ВІДПРАВЛЕНО УСПІШНО!\n"
                                              f"  🔑 Auto-banned: {auto_banned}\n"
                                              f"  📝 Pending: {pending}\n"
                                              f"  🔄 Дублікати: {duplicates}\n"
                                              f"{'='*40}")
            self.feedback_text.configure(state="disabled")

            # Оновлюємо banned list
            if self.api and auto_banned > 0:
                def do_refresh():
                    self.api.clear_cache()
                    banned = self.api.get_banned()
                    self.after(0, lambda: setattr(self, 'banned', banned))
                threading.Thread(target=do_refresh, daemon=True).start()

            messagebox.showinfo(
                "✅ Успіх!",
                f"Помилки оброблено!\n\n"
                f"🔑 Додано в Banned: {auto_banned}\n"
                f"📝 В Pending: {pending}\n"
                f"🔄 Дублікати: {duplicates}\n\n"
                f"Система оновлена — ці слова більше\n"
                f"не будуть генеруватися."
            )
        else:
            msg = result.get("message", "Невідома помилка")
            self.lbl_feedback_status.configure(
                text=f"❌ Помилка: {msg}", text_color="#dc3545"
            )
            self.btn_submit_errors.configure(state="normal")

    def _on_submit_error(self, error_msg: str):
        """Callback при помилці відправки."""
        self.btn_submit_errors.configure(state="normal", text="🚀 Відправити в Banned")
        self.lbl_feedback_status.configure(
            text=f"❌ {error_msg}", text_color="#dc3545"
        )

    # ─────────────────────────────────────────
    #  TAB SWITCHING
    # ─────────────────────────────────────────

    def _show_tab(self, name: str):
        for key, frm in self.tabs.items():
            frm.grid_forget()

        self.tabs[name].grid(row=0, column=0, sticky="nsew")

        # Підсвічуємо кнопку
        buttons = {
            "account": self.btn_tab_account,
            "generate": self.btn_tab_generate,
            "stats": self.btn_tab_stats,
            "settings": self.btn_tab_settings,
            "feedback": self.btn_tab_feedback,
        }
        for key, btn in buttons.items():
            if key == name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

    # ─────────────────────────────────────────
    #  STARTUP SEQUENCE
    # ─────────────────────────────────────────

    def _is_dev_mode(self) -> bool:
        """Чи ввімкнений dev-режим (тег _DEV_)."""
        return self._get_farmer_tag().upper() == "_DEV_"

    def _startup_sequence(self):
        """Послідовність при старті: Gist → повний конфіг → Connect."""
        tag = self._get_farmer_tag()

        # Показуємо Account tab якщо нема тега, але все одно підключаємось
        if not tag and not self._is_tag_locked():
            self._show_tab("account")

        self.lbl_status.configure(text="🟡 Підключення...", text_color="yellow")
        self.update_idletasks()

        def do_startup():
            # 1. Отримуємо повний конфіг з Gist (URL + key + model)
            gist_config = self.gist.fetch_config()
            script_url = gist_config["script_url"]
            gemini_key = gist_config["gemini_key"]
            gemini_model = gist_config["gemini_model"]
            source = gist_config["_source"]

            # Зберігаємо актуальні значення
            self.after(0, lambda: self._save_settings(
                script_url=script_url,
                gemini_key=gemini_key,
                gemini_model=gemini_model
            ))

            # 2. Підключаємося
            self.api = SheetAPI(script_url)
            ok, msg = self.api.test_connection()

            if ok:
                data = self.api.sync_all()
                self.after(0, lambda: self._on_connected(data, msg, source))
            else:
                self.after(0, lambda: self._on_connect_fail(msg))

        threading.Thread(target=do_startup, daemon=True).start()

    # ─────────────────────────────────────────
    #  CONNECTION
    # ─────────────────────────────────────────

    def _on_connected(self, data: dict, msg: str, url_source: str = ""):
        """Callback після успішного підключення."""
        self.sites = data.get("sites", [])
        self.config = data.get("config", {})
        self.banned = data.get("banned", [])
        self.banned_domains = data.get("banned_domains", [])
        self.is_connected = True

        # Ініціалізуємо генератор (key + model з Gist)
        gemini_key = self.settings.get("gemini_key", "")
        gemini_model = self.settings.get("gemini_model", "gemini-2.5-flash")
        output = self.settings.get("output_folder", DEFAULT_OUTPUT_FOLDER)
        if gemini_key:
            self.generator = AdsGenerator(gemini_key, output, gemini_model)

        self.lbl_status.configure(text=f"🟢 Онлайн", text_color="#28a745")

        # Connection info в налаштуваннях
        source_text = {"gist": "GitHub Gist", "cached": "Кешований", "saved": "Збережений", "fallback": "Резервний"}.get(url_source, "")
        model_name = self.settings.get("gemini_model", "gemini-2.5-flash")
        info = (f"Статус: ✅ Підключено\n"
                f"Версія таблиці: {msg}\n"
                f"AI модель: {model_name}\n"
                f"Сайтів: {len(self.sites)}\n"
                f"Banned keywords: {len(self.banned)}\n"
                f"Banned domains: {len(self.banned_domains)}")
        if source_text:
            info += f"\nКонфіг джерело: {source_text}"
        self.lbl_connection_info.configure(text=info, text_color="#28a745")

        self._populate_sites()
        self._log(f"✅ {msg} | Сайтів: {len(self.sites)} | Banned: {len(self.banned)}")

        # Перевіряємо message з конфігу
        message = self.config.get("message", "").strip()
        if message:
            messagebox.showinfo("📢 Повідомлення", message)

    def _on_connect_fail(self, msg: str):
        """Callback після невдалого підключення."""
        self.is_connected = False
        self.lbl_status.configure(text=f"🔴 Офлайн", text_color="#dc3545")
        self.lbl_connection_info.configure(
            text=f"Статус: ❌ Не підключено\nПомилка: {msg}",
            text_color="#dc3545"
        )
        self._log(f"❌ Підключення не вдалося: {msg}")

    def _sync(self):
        """Синхронізація даних."""
        if not self._is_tag_locked() and not self._is_dev_mode():
            messagebox.showinfo("Інформація", "Спочатку збережіть тег в Аккаунті")
            return

        self.lbl_status.configure(text="🟡 Синхронізація...", text_color="yellow")

        def do_sync():
            # Оновлюємо повний конфіг з Gist
            gist_config = self.gist.fetch_config()
            script_url = gist_config["script_url"]
            source = gist_config["_source"]
            self.after(0, lambda: self._save_settings(
                script_url=script_url,
                gemini_key=gist_config["gemini_key"],
                gemini_model=gist_config["gemini_model"]
            ))

            self.api = SheetAPI(script_url)
            ok, msg = self.api.test_connection()
            if ok:
                data = self.api.sync_all()
                self.after(0, lambda: self._on_connected(data, "Синхронізовано", source))
            else:
                self.after(0, lambda: self._on_connect_fail(msg))

        threading.Thread(target=do_sync, daemon=True).start()

    # ─────────────────────────────────────────
    #  SITES LIST
    # ─────────────────────────────────────────

    def _populate_sites(self):
        """Заповнює список сайтів чекбоксами."""
        for w in self.sites_frame.winfo_children():
            w.destroy()
        self.site_vars.clear()

        # Оновлюємо інфо-лейбл «Випадковий сайт»
        n = len(self.sites) if self.sites else 0
        if n > 0:
            names = "\n".join(f"  • {s.get('name', s.get('url', '?'))}" for s in self.sites)
            self.lbl_random_info.configure(
                text=f"🎲 Один випадковий сайт із {n} доступних\n\n{names}",
            )
        else:
            self.lbl_random_info.configure(text="Таблиця порожня — додайте сайти в Google Sheet")

        if not self.sites:
            ctk.CTkLabel(self.sites_frame, text="Таблиця порожня — додайте сайти в Google Sheet",
                          text_color="gray").pack(pady=30)
            return

        for i, site in enumerate(self.sites):
            url = site.get("url", "")
            name = site.get("name", url)
            if not url:
                continue

            var = ctk.BooleanVar(value=False)
            self.site_vars[url] = var

            row = ctk.CTkFrame(self.sites_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            cb = ctk.CTkCheckBox(
                row, text="", variable=var, width=24,
                command=self._update_selected_count
            )
            cb.pack(side="left", padx=(5, 8))

            lbl_name = ctk.CTkLabel(row, text=name,
                                     font=ctk.CTkFont(size=13, weight="bold"))
            lbl_name.pack(side="left", padx=(0, 10))

            lbl_url = ctk.CTkLabel(row, text=url,
                                    font=ctk.CTkFont(size=11), text_color="gray")
            lbl_url.pack(side="left")

        self._update_selected_count()

    def _toggle_all_sites(self):
        """Обрати/зняти всі."""
        any_selected = any(v.get() for v in self.site_vars.values())
        new_val = not any_selected
        for var in self.site_vars.values():
            var.set(new_val)
        self._update_selected_count()
        self.btn_select_all.configure(text="Зняти всі" if new_val else "Обрати всі")

    def _update_selected_count(self):
        count = sum(1 for v in self.site_vars.values() if v.get())
        self.lbl_selected.configure(text=f"Обрано: {count} сайтів")

    def _set_gen_mode(self, value: str):
        """Перемикає між «Випадковий сайт» та «Вибрати сайти»."""
        if value == "🎲 Випадковий сайт":
            self.gen_mode.set("random")
            self.pick_sites_wrapper.pack_forget()
            self.random_site_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))
            n = len(self.sites) if self.sites else 0
            self.lbl_selected.configure(text=f"🎲 Випадковий із {n}")
        else:
            self.gen_mode.set("pick")
            self.random_site_frame.pack_forget()
            self.pick_sites_wrapper.pack(fill="both", expand=True, padx=30, pady=(0, 10))
            self._update_selected_count()

    def _refresh_sites(self):
        if not self.api:
            return
        self._log("🔄 Оновлення списку сайтів...")

        def do_refresh():
            self.api.clear_cache()
            sites = self.api.get_sites()
            self.after(0, lambda: self._on_sites_refreshed(sites))

        threading.Thread(target=do_refresh, daemon=True).start()

    def _on_sites_refreshed(self, sites):
        self.sites = sites
        self._populate_sites()
        if self.gen_mode.get() == "random":
            self.lbl_selected.configure(text=f"🎲 Випадковий із {len(sites)}")
        self._log(f"✅ Сайтів завантажено: {len(sites)}")

    # ─────────────────────────────────────────
    #  GENERATION
    # ─────────────────────────────────────────

    def _start_generation(self):
        """Запуск генерації."""
        if self.is_generating:
            messagebox.showinfo("Зайнято", "Генерація вже запущена")
            return

        if not self.is_connected or not self.api:
            messagebox.showwarning("Помилка", "Немає підключення до таблиці")
            return

        if not self.generator:
            gemini_key = self.settings.get("gemini_key", "")
            gemini_model = self.settings.get("gemini_model", "gemini-2.5-flash")
            output = self.settings.get("output_folder", DEFAULT_OUTPUT_FOLDER)
            if not gemini_key:
                messagebox.showwarning("Помилка", "API ключ не знайдено. Натисніть 🔄 Синхронізація")
                return
            self.generator = AdsGenerator(gemini_key, output, gemini_model)

        # Визначаємо список сайтів за режимом
        import random as _rnd
        if self.gen_mode.get() == "random":
            available = [s for s in self.sites if s.get("url")]
            if not available:
                messagebox.showwarning("Помилка", "Немає сайтів для генерації")
                return
            pick = _rnd.choice(available)
            selected = [pick.get("url")]
            self._log(f"🎲 Випадковий вибір: {pick.get('name', pick.get('url'))}")
        else:
            selected = [url for url, var in self.site_vars.items() if var.get()]

        if not selected:
            messagebox.showwarning("Помилка", "Оберіть хоча б один сайт")
            return

        farmer = self._get_farmer_tag()
        if not farmer:
            messagebox.showwarning("Помилка", "Збережіть тег в Аккаунті")
            self._show_tab("account")
            return

        self.is_generating = True
        self.btn_generate.configure(state="disabled", text="⏳ Генерація...")
        self.progress.set(0)
        self._log(f"\n{'='*50}")
        self._log(f"🚀 Старт генерації для {len(selected)} сайтів")
        self._log(f"👤 Фармер: {farmer}")
        self._log(f"{'='*50}")

        def do_generate():
            # Авто-синхронізація конфігу перед генерацією
            try:
                self.api.clear_cache()
                fresh_config = self.api.get_config()
                if fresh_config:
                    self.config = fresh_config
                    budget = fresh_config.get('budget', '?')
                    days = fresh_config.get('campaign_days', '?')
                    self._log_safe(f"⚙️ Конфіг: бюджет=${budget}, днів={days}")
            except Exception:
                self._log_safe("⚠️ Не вдалося оновити конфіг, використовую кешований")

            total = len(selected)
            success_count = 0
            fail_count = 0
            all_errors = []
            generated_files = []

            for i, url in enumerate(selected, 1):
                # Знаходимо назву бізнесу
                site_info = next((s for s in self.sites if s.get("url") == url), {})
                name = site_info.get("name", url)

                self.after(0, lambda p=i/total: self.progress.set(p))
                self._log_safe(f"\n[{i}/{total}] 🔄 {name}")

                result = self.generator.generate_csv(
                    website_url=url,
                    business_name=name,
                    config=self.config,
                    banned=self.banned,
                    banned_domains=self.banned_domains,
                    on_status=lambda msg: self._log_safe(f"   {msg}")
                )

                if result["success"]:
                    success_count += 1
                    generated_files.append(result['filepath'])
                    # Логуємо генерацію (DEV теж логує для тестування)
                    try:
                        self.api.log_generation(farmer, url)
                    except Exception as e:
                        self._log_safe(f"   ⚠️ log_generation: {e}")
                    self._log_safe(f"   ✅ Готово: {os.path.basename(result['filepath'])}")

                    # Збираємо banned keywords для Pending
                    if result.get("removed_keywords"):
                        all_errors.extend(result["removed_keywords"])
                        self._log_safe(f"   🚫 Заборонених: {len(result['removed_keywords'])}")
                else:
                    fail_count += 1
                    err = result.get("stats", {}).get("error", "Невідома помилка")
                    self._log_safe(f"   ❌ Помилка: {err}")

            # Відправляємо всі errors на модерацію
            if all_errors:
                try:
                    self.api.submit_errors(farmer, all_errors)
                    self._log_safe(f"\n📤 Відправлено {len(all_errors)} заборонених на модерацію")
                except Exception as e:
                    self._log_safe(f"\n⚠️ submit_errors: {e}")

            self.after(0, lambda: self._on_generation_done(success_count, fail_count, total, generated_files))

        threading.Thread(target=do_generate, daemon=True).start()

    def _on_generation_done(self, success: int, fail: int, total: int, generated_files: list = None):
        """Callback після завершення генерації."""
        self.is_generating = False
        self.btn_generate.configure(state="normal", text="▶ Генерувати")
        self.progress.set(1)

        self._log(f"\n{'='*50}")
        self._log(f"🏁 Завершено! ✅ {success}/{total} | ❌ {fail}/{total}")
        self._log(f"{'='*50}")

        # Показуємо кнопки копіювання імен файлів
        if generated_files:
            self._log(f"\n📂 Згенеровані файли:")
            for fp in generated_files:
                fname = os.path.basename(fp)
                self._log(f"   📄 {fname}")

            # Додаємо кнопку копіювання
            self._show_copy_buttons(generated_files)

        if success > 0:
            output = self.settings.get("output_folder", DEFAULT_OUTPUT_FOLDER)
            abs_output = os.path.abspath(output)
            messagebox.showinfo(
                "Готово!",
                f"Згенеровано: {success} з {total}\n\n"
                f"Файли в:\n{abs_output}"
            )

    def _show_copy_buttons(self, filepaths: list):
        """Показує кнопки для копіювання імен згенерованих файлів."""
        # Видаляємо попередні кнопки копіювання
        if hasattr(self, '_copy_frame') and self._copy_frame:
            self._copy_frame.destroy()

        self._copy_frame = ctk.CTkFrame(self.tabs["generate"], fg_color="transparent")
        self._copy_frame.pack(fill="x", padx=30, pady=(0, 10))

        ctk.CTkLabel(self._copy_frame, text="📋 Копіювати назву файлу:",
                      font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 5))

        for fp in filepaths:
            fname = os.path.basename(fp)
            btn_frame = ctk.CTkFrame(self._copy_frame, fg_color="#1a1a2e",
                                      corner_radius=8)
            btn_frame.pack(fill="x", pady=2)

            ctk.CTkLabel(btn_frame, text=f"📄 {fname}",
                          font=ctk.CTkFont(size=11),
                          text_color="#b0b0b0").pack(side="left", padx=10, pady=6)

            btn = ctk.CTkButton(
                btn_frame, text="📋 Копіювати", width=100, height=28,
                font=ctk.CTkFont(size=11),
                fg_color="#2d6a4f", hover_color="#40916c",
                command=lambda f=fname: self._copy_filename(f)
            )
            btn.pack(side="right", padx=10, pady=6)

    def _copy_filename(self, filename: str):
        """Копіює назву файлу в буфер обміну."""
        self.clipboard_clear()
        self.clipboard_append(filename)
        self.update()
        self._log(f"📋 Скопійовано: {filename}")

    # ─────────────────────────────────────────
    #  STATS
    # ─────────────────────────────────────────

    def _load_stats(self):
        """Завантажує статистику."""
        if not self.is_connected or not self.api:
            messagebox.showinfo("Інформація", "Немає підключення до таблиці")
            return

        farmer = self._get_farmer_tag()
        if not farmer:
            messagebox.showinfo("Інформація", "Збережіть тег в Аккаунті")
            return

        for w in self.stats_container.winfo_children():
            w.destroy()

        ctk.CTkLabel(self.stats_container, text="🔄 Завантаження...",
                      text_color="gray").pack(pady=30)

        def do_load():
            result = self.api.get_farmer_stats(farmer)
            self.after(0, lambda: self._show_stats(result))

        threading.Thread(target=do_load, daemon=True).start()

    def _show_stats(self, data: dict):
        """Показує статистику."""
        for w in self.stats_container.winfo_children():
            w.destroy()

        if data.get("status") == "error":
            ctk.CTkLabel(self.stats_container,
                          text=f"❌ {data.get('message', 'Помилка')}",
                          text_color="#dc3545").pack(pady=30)
            return

        # API повертає дані фармера в farmer_info (вкладений об'єкт)
        info = data.get("farmer_info") or data

        stats_items = [
            ("📊 Всього генерацій", info.get("total", data.get("total_generations", "0"))),
            ("📅 Сьогодні", info.get("today", "0")),
            ("📆 За 7 днів", info.get("last_7d", "0")),
            ("📆 За 30 днів", info.get("last_30d", "0")),
            ("📈 Середнє/день", info.get("avg_per_day", "0")),
            ("🏆 Ранг", info.get("rank", "—")),
            ("🕐 Остання активність", info.get("last_active", "—")),
        ]

        for label, value in stats_items:
            card = ctk.CTkFrame(self.stats_container)
            card.pack(fill="x", pady=3, padx=5)

            ctk.CTkLabel(card, text=label,
                          font=ctk.CTkFont(size=13)).pack(side="left", padx=15, pady=10)
            ctk.CTkLabel(card, text=str(value),
                          font=ctk.CTkFont(size=15, weight="bold")).pack(side="right", padx=15, pady=10)

    # ─────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────

    def _log(self, message: str):
        """Додає рядок у лог."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

    def _log_safe(self, message: str):
        """Thread-safe лог."""
        self.after(0, lambda: self._log(message))

    def _pick_output_folder(self):
        folder = filedialog.askdirectory(title="Оберіть папку для CSV")
        if folder:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, folder)

    def _open_output_folder(self):
        output = self.settings.get("output_folder", DEFAULT_OUTPUT_FOLDER)
        abs_path = os.path.abspath(output)
        if os.path.isdir(abs_path):
            if sys.platform == "darwin":
                os.system(f'open "{abs_path}"')
            elif sys.platform == "win32":
                os.startfile(abs_path)
            else:
                os.system(f'xdg-open "{abs_path}"')
