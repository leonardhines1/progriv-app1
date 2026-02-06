"""
Smoke-test для Прогрів.exe
Запускає .exe, чекає 8 секунд, перевіряє:
 1. Процес запустився
 2. Процес не впав (exit code)
 3. Процес досі живий через 8 сек

Запуск: python tests/smoke_test.py
"""

import subprocess
import sys
import os
import time

EXE_PATH = os.path.join("dist", "Прогрів.exe")

def main():
    print(f"🧪 Smoke test: {EXE_PATH}")
    
    # Перевірка що файл існує
    if not os.path.isfile(EXE_PATH):
        print(f"❌ Файл не знайдено: {EXE_PATH}")
        sys.exit(1)
    
    size_mb = os.path.getsize(EXE_PATH) / (1024 * 1024)
    print(f"   Розмір: {size_mb:.1f} MB")
    
    # Запускаємо .exe
    print("   Запуск процесу...")
    try:
        proc = subprocess.Popen(
            [EXE_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # Не чекаємо завершення — GUI-додаток працює нескінченно
        )
    except Exception as e:
        print(f"❌ Не вдалося запустити: {e}")
        sys.exit(1)
    
    print(f"   PID: {proc.pid}")
    
    # Чекаємо 8 секунд — якщо впаде, poll() поверне exit code
    for i in range(8):
        time.sleep(1)
        ret = proc.poll()
        if ret is not None:
            # Процес завершився — це погано (GUI не повинен закриватися сам)
            stdout = proc.stdout.read().decode("utf-8", errors="replace")
            stderr = proc.stderr.read().decode("utf-8", errors="replace")
            print(f"❌ Процес впав через {i+1} сек з кодом {ret}")
            if stdout.strip():
                print(f"   STDOUT: {stdout[:500]}")
            if stderr.strip():
                print(f"   STDERR: {stderr[:500]}")
            sys.exit(1)
        print(f"   ... alive ({i+1}/8 sec)")
    
    # Процес досі живий — це добре!
    print("   Процес працює вже 8 секунд — завершуємо...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    
    print("✅ Smoke test PASSED — .exe запустився і не впав")
    sys.exit(0)


if __name__ == "__main__":
    main()
