@echo off
chcp 65001 >nul 2>&1
title Збірка «Прогрів» для Windows
echo.
echo ══════════════════════════════════════════════
echo    Збірка програми «Прогрів» для Windows
echo ══════════════════════════════════════════════
echo.

REM ── Перевірка Python ──
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python не знайдено!
    echo.
    echo Встанови Python з https://www.python.org/downloads/
    echo ⚠️  При встановленні обов'язково постав галочку:
    echo    [✓] Add Python to PATH
    echo.
    pause
    exit /b 1
)

echo ✅ Python знайдено:
python --version
echo.

REM ── Створення віртуального середовища ──
echo [1/4] Створення віртуального середовища...
if exist .venv (
    echo     .venv вже існує, пропускаю...
) else (
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo ❌ Не вдалося створити .venv
        pause
        exit /b 1
    )
)
echo.

REM ── Встановлення залежностей ──
echo [2/4] Встановлення залежностей...
.venv\Scripts\pip install --upgrade pip >nul 2>&1
.venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ❌ Помилка встановлення залежностей
    pause
    exit /b 1
)
echo.

REM ── Очищення попередньої збірки ──
echo [3/4] Очищення попередньої збірки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo     Очищено.
echo.

REM ── Збірка .exe ──
echo [4/4] Збірка Прогрів.exe ...
echo     Це може зайняти 1-3 хвилини...
echo.
.venv\Scripts\pyinstaller Progriv_win.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo.
    echo ❌ Помилка збірки! Перевір логи вище.
    pause
    exit /b 1
)

echo.
echo ══════════════════════════════════════════════
echo    ✅ ГОТОВО!
echo ══════════════════════════════════════════════
echo.
echo    Файл: dist\Прогрів.exe
echo.
echo    Скопіюй цей файл і надішли фармерам.
echo.
echo ══════════════════════════════════════════════

REM ── Відкрити папку з результатом ──
if exist "dist\Прогрів.exe" (
    explorer dist
)

pause
