# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для додатку «Прогрів» — Windows
Збірка: python -m PyInstaller Progriv_win.spec --clean
"""

import os
import sys
import importlib

block_cipher = None

# Шляхи
ROOT = os.path.abspath('.')

# Знаходимо customtkinter автоматично (працює в будь-якому venv)
ctk_spec = importlib.util.find_spec('customtkinter')
if ctk_spec and ctk_spec.submodule_search_locations:
    CTK_PATH = ctk_spec.submodule_search_locations[0]
else:
    # Fallback
    CTK_PATH = os.path.join(ROOT, '.venv', 'Lib', 'site-packages', 'customtkinter')

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # CustomTkinter assets (теми, іконки)
        (CTK_PATH, 'customtkinter'),
        # Іконка додатку
        (os.path.join(ROOT, 'assets', 'icon.png'), 'assets'),
        (os.path.join(ROOT, 'assets', 'icon.ico'), 'assets'),
    ],
    hiddenimports=[
        'customtkinter',
        'darkdetect',
        'PIL',
        'PIL._tkinter_finder',
        'requests',
        'certifi',
        'charset_normalizer',
        'idna',
        'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'pytest', 'unittest', 'doctest',
        'tkinter.test', 'lib2to3',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Прогрів',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # БЕЗ чорного вікна консолі
    disable_windowed_traceback=False,
    argv_emulation=False,   # Windows не потребує
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'assets', 'icon.ico'),
    # Інформація про версію (відображається у Властивостях файлу)
    version=None,
)
