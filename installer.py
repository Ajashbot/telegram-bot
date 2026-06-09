#!/usr/bin/env python3
"""
installer.py — نظام التثبيت والإعداد الذاتي
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قم بتشغيل هذا الملف للمرة الأولى لإعداد البوت تلقائياً:
    python installer.py
"""
import os
import sys
import subprocess
from pathlib import Path

CONFIG_FILE = Path(".env")

REQUIRED = {
    "BOT_TOKEN":  "🔑 أدخل BOT_TOKEN (من @BotFather): ",
    "API_ID":     "🔑 أدخل API_ID (من my.telegram.org): ",
    "API_HASH":   "🔑 أدخل API_HASH (من my.telegram.org): ",
    "ADMIN_ID":   "🔑 أدخل ADMIN_ID (معرفك الرقمي في تيليجرام): ",
}


def load_env():
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def setup_mode():
    print("\n" + "="*50)
    print("🚀 مرحباً بك في نظام إعداد البوت")
    print("="*50)
    print("سيتم طلب بيانات الإعداد مرة واحدة فقط.\n")

    config_lines = []
    for key, prompt in REQUIRED.items():
        while True:
            value = input(prompt).strip()
            if value:
                break
            print(f"❌ لا يمكن ترك {key} فارغاً.")
        config_lines.append(f"{key}={value}")
        os.environ[key] = value

    CONFIG_FILE.write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    print("\n✅ تم حفظ الإعدادات بنجاح في .env")


def check_deps():
    try:
        import telegram  # noqa: F401
    except ImportError:
        print("📦 جاري تثبيت المتطلبات...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ تم تثبيت المتطلبات.")


def main():
    load_env()

    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"⚠️  المتغيرات التالية غير موجودة: {', '.join(missing)}")
        setup_mode()

    check_deps()

    print("\n🤖 جاري تشغيل البوت...\n")
    os.execv(sys.executable, [sys.executable, "bot.py"])


if __name__ == "__main__":
    main()
