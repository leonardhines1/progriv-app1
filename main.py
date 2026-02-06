#!/usr/bin/env python3
"""
ADS Campaign Tool — Desktop App
Точка входу.
"""

import sys
import os

# Додаємо кореневу папку в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
