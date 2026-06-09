"""
📦 تجهيز ونقل المشروع — One-Click Deploy System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يقوم بـ:
  1. قراءة كامل ملفات المشروع
  2. إزالة البيانات الحساسة فقط
  3. إنشاء installer.py بنظام Setup Mode
  4. إنشاء requirements.txt وسكريبت التشغيل
  5. ضغط المشروع في project_one_click_deploy.zip
  6. إرسال الملف إلى OWNER_ID فقط
"""

import os
import re
import shutil
import zipfile
import logging
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from src import keyboards, states

logger = logging.getLogger(__name__)

ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
BOT_ROOT  = Path(__file__).parent.parent.parent  # telegram-bot/

# ── ملفات وأنماط يجب استبعادها ──────────────────────────────────────────────
EXCLUDE_PATTERNS = {
    "__pycache__", "*.pyc", "*.pyo", "*.session", "*.session-journal",
    "userdata.pkl", "conversations.pkl", "deploy_temp", "*.zip",
    ".env", ".env.*", "*.log",
}

# ── أسماء متغيرات الأسرار التي تُستبدل بـ os.getenv ──────────────────────────
SECRET_VARS = {
    "BOT_TOKEN": 'os.getenv("BOT_TOKEN")',
    "API_ID":    'int(os.getenv("API_ID", "0"))',
    "API_HASH":  'os.getenv("API_HASH")',
    "ADMIN_ID":  'int(os.getenv("ADMIN_ID", "0"))',
    "SESSION_SECRET": 'os.getenv("SESSION_SECRET")',
}


# ═══════════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _should_exclude(path: Path) -> bool:
    name = path.name
    for pat in EXCLUDE_PATTERNS:
        if "*" in pat:
            suffix = pat.lstrip("*")
            if name.endswith(suffix):
                return True
        else:
            if name == pat:
                return True
    return False


def _sanitize_content(text: str) -> str:
    """
    استبدال القيم الحساسة المُعيّنة مباشرةً في الكود
    (أي سطر يحتوي: VAR = "ACTUAL_VALUE" أو VAR = 'ACTUAL_VALUE')
    بـ os.getenv(...) المقابلة.
    """
    for var, replacement in SECRET_VARS.items():
        # Pattern: VAR_NAME = "anything" أو VAR_NAME = 'anything'
        pattern = rf'({re.escape(var)}\s*=\s*)["\']([^"\']+)["\']'
        text = re.sub(pattern, rf'\1{replacement}', text)
    return text


def _write_installer(dest: Path) -> None:
    """إنشاء installer.py — نظام Setup Mode للتشغيل الأول."""
    content = '''\
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
    print("\\n" + "="*50)
    print("🚀 مرحباً بك في نظام إعداد البوت")
    print("="*50)
    print("سيتم طلب بيانات الإعداد مرة واحدة فقط.\\n")

    config_lines = []
    for key, prompt in REQUIRED.items():
        while True:
            value = input(prompt).strip()
            if value:
                break
            print(f"❌ لا يمكن ترك {key} فارغاً.")
        config_lines.append(f"{key}={value}")
        os.environ[key] = value

    CONFIG_FILE.write_text("\\n".join(config_lines) + "\\n", encoding="utf-8")
    print("\\n✅ تم حفظ الإعدادات بنجاح في .env")


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

    print("\\n🤖 جاري تشغيل البوت...\\n")
    os.execv(sys.executable, [sys.executable, "bot.py"])


if __name__ == "__main__":
    main()
'''
    (dest / "installer.py").write_text(content, encoding="utf-8")


def _write_requirements(dest: Path) -> None:
    """إنشاء requirements.txt بكل المتطلبات."""
    src_req = BOT_ROOT / "requirements.txt"
    if src_req.exists():
        shutil.copy2(src_req, dest / "requirements.txt")
        return

    # fallback إذا لم يوجد الملف
    content = """\
python-telegram-bot==22.7
telethon==1.43.2
cryptg
aiofiles
"""
    (dest / "requirements.txt").write_text(content, encoding="utf-8")


def _write_start_script(dest: Path) -> None:
    """إنشاء سكريبت تشغيل start.sh وstart.bat."""
    sh_content = """\
#!/usr/bin/env bash
# start.sh — تشغيل البوت
set -e
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi
python installer.py
"""
    bat_content = """\
@echo off
REM start.bat — تشغيل البوت على Windows
if exist .env (
    for /f "tokens=*" %%i in (.env) do set %%i
)
python installer.py
pause
"""
    (dest / "start.sh").write_text(sh_content, encoding="utf-8")
    (dest / "start.bat").write_text(bat_content, encoding="utf-8")
    try:
        os.chmod(dest / "start.sh", 0o755)
    except Exception:
        pass


def _write_readme(dest: Path) -> None:
    readme = """\
# 🤖 Telegram Bot — One-Click Deploy

## 🚀 التشغيل الأول (Setup Mode)

```bash
python installer.py
```

سيطلب منك البيانات مرة واحدة ثم يُشغّل البوت تلقائياً.

## ⚙️ المتطلبات

```
python >= 3.10
pip install -r requirements.txt
```

## 🔑 متغيرات البيئة

| المتغير | الوصف |
|---------|-------|
| BOT_TOKEN | توكن البوت من @BotFather |
| API_ID | من my.telegram.org |
| API_HASH | من my.telegram.org |
| ADMIN_ID | معرفك الرقمي في تيليجرام |

## 📁 بنية المشروع

```
bot.py           ← نقطة الدخول الرئيسية
installer.py     ← معالج الإعداد الأول
requirements.txt ← المتطلبات
src/
  handlers/      ← معالجات الأوامر
  keyboards.py   ← لوحات المفاتيح
  states.py      ← حالات FSM
  database.py    ← قاعدة البيانات
  ...
```

## 🌐 الاستضافة

يعمل على أي بيئة تدعم Python 3.10+:
- VPS (Ubuntu / Debian / CentOS)
- Replit
- Railway
- Render
- Heroku
"""
    (dest / "README.md").write_text(readme, encoding="utf-8")


def _copy_project(dest: Path) -> int:
    """
    نسخ كامل مجلد telegram-bot إلى dest مع:
    - استبعاد الملفات غير الضرورية
    - تنظيف الأسرار من ملفات Python
    يُعيد عدد الملفات المنسوخة.
    """
    count = 0
    for src_path in BOT_ROOT.rglob("*"):
        if src_path.is_dir():
            continue

        # التحقق من كل جزء في المسار
        rel = src_path.relative_to(BOT_ROOT)
        skip = False
        for part in rel.parts:
            if _should_exclude(Path(part)):
                skip = True
                break
        if skip:
            continue

        dst_path = dest / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.suffix == ".py":
            try:
                original = src_path.read_text(encoding="utf-8")
                sanitized = _sanitize_content(original)
                dst_path.write_text(sanitized, encoding="utf-8")
            except Exception:
                shutil.copy2(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)

        count += 1

    return count


def _build_zip(deploy_dir: Path, zip_path: Path) -> None:
    """ضغط deploy_dir في zip_path."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in deploy_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(deploy_dir)
                zf.write(file_path, arcname)


def _verify_zip(zip_path: Path) -> bool:
    """التحقق من سلامة ملف ZIP."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            return bad is None
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Telegram Handlers
# ═══════════════════════════════════════════════════════════════════════════════

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة التجهيز — متاح للأدمن فقط."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 هذه الخدمة للمالك فقط.")
        return states.MAIN_MENU

    ctx.user_data["fsm_state"] = states.DEPLOY_MENU
    await update.message.reply_text(
        "📦 *تجهيز ونقل المشروع*\n\n"
        "سيتم تنفيذ الخطوات التالية:\n\n"
        "1️⃣ قراءة كامل ملفات المشروع\n"
        "2️⃣ جمع الأكواد بدون تعديل المنطق\n"
        "3️⃣ تنظيف البيانات الحساسة فقط\n"
        "4️⃣ إنشاء نظام التثبيت التلقائي (installer.py)\n"
        "5️⃣ إنشاء ملفات التشغيل (start.sh / start.bat)\n"
        "6️⃣ ضغط المشروع في ملف واحد\n"
        "7️⃣ التحقق من سلامة الملف\n"
        "8️⃣ إرسال الملف إليك مباشرة\n\n"
        "اضغط *🚀 تجهيز الحزمة وإرسالها* للبدء:",
        parse_mode="Markdown",
        reply_markup=keyboards.deploy_menu(),
    )
    return states.DEPLOY_MENU


async def do_deploy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تنفيذ عملية التجهيز والإرسال الكاملة."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 هذه الخدمة للمالك فقط.")
        return states.MAIN_MENU

    status_msg = await update.message.reply_text(
        "⏳ جاري تجهيز المشروع...\n\n"
        "🔄 الخطوة 1/7: قراءة ملفات المشروع...",
        parse_mode="Markdown",
    )

    tmp_dir   = None
    zip_path  = None

    try:
        with tempfile.TemporaryDirectory(prefix="deploy_temp_") as tmp_str:
            tmp_dir    = Path(tmp_str)
            deploy_dir = tmp_dir / "project_one_click_deploy"
            deploy_dir.mkdir()

            # ── الخطوة 2: نسخ المشروع ──────────────────────────────────
            await status_msg.edit_text(
                "⏳ جاري تجهيز المشروع...\n\n"
                "🔄 الخطوة 2/7: نسخ الملفات وتنظيف الأسرار...",
            )
            file_count = _copy_project(deploy_dir)
            logger.info(f"[DEPLOY] Copied {file_count} files to {deploy_dir}")

            # ── الخطوة 3: ملفات التثبيت والتشغيل ──────────────────────
            await status_msg.edit_text(
                "⏳ جاري تجهيز المشروع...\n\n"
                "🔄 الخطوة 3/7: إنشاء installer.py ونظام Setup Mode...",
            )
            _write_installer(deploy_dir)

            # ── الخطوة 4: requirements.txt ─────────────────────────────
            await status_msg.edit_text(
                "⏳ جاري تجهيز المشروع...\n\n"
                "🔄 الخطوة 4/7: إنشاء requirements.txt وسكريبتات التشغيل...",
            )
            _write_requirements(deploy_dir)
            _write_start_script(deploy_dir)
            _write_readme(deploy_dir)

            # ── الخطوة 5: الضغط ────────────────────────────────────────
            await status_msg.edit_text(
                "⏳ جاري تجهيز المشروع...\n\n"
                "🔄 الخطوة 5/7: ضغط المشروع في ملف واحد...",
            )
            zip_path = tmp_dir / "project_one_click_deploy.zip"
            _build_zip(deploy_dir, zip_path)
            zip_size_kb = zip_path.stat().st_size // 1024
            logger.info(f"[DEPLOY] ZIP created: {zip_path} ({zip_size_kb} KB)")

            # ── الخطوة 6: التحقق من سلامة الملف ───────────────────────
            await status_msg.edit_text(
                "⏳ جاري تجهيز المشروع...\n\n"
                "🔄 الخطوة 6/7: التحقق من سلامة الملف...",
            )
            if not _verify_zip(zip_path):
                await status_msg.edit_text("❌ فشل التحقق من سلامة ملف ZIP.")
                return states.DEPLOY_MENU

            # ── الخطوة 7: الإرسال ──────────────────────────────────────
            await status_msg.edit_text(
                "⏳ جاري تجهيز المشروع...\n\n"
                "🔄 الخطوة 7/7: إرسال الملف...",
            )

            with open(zip_path, "rb") as zf:
                await update.message.reply_document(
                    document=zf,
                    filename="project_one_click_deploy.zip",
                    caption=(
                        "✅ *تم تجهيز مشروعك الكامل للنشر بدون أي إعداد يدوي*\n\n"
                        f"📁 الملفات المُضمّنة: `{file_count}` ملف\n"
                        f"📦 حجم الحزمة: `{zip_size_kb} KB`\n\n"
                        "🚀 *طريقة التشغيل على أي استضافة:*\n"
                        "1. فك ضغط الملف\n"
                        "2. شغّل: `python installer.py`\n"
                        "3. أدخل البيانات مرة واحدة\n"
                        "4. البوت يعمل تلقائياً ✨\n\n"
                        "📖 راجع `README.md` للتفاصيل الكاملة."
                    ),
                    parse_mode="Markdown",
                )

            await status_msg.edit_text(
                f"✅ *اكتملت عملية التجهيز والإرسال*\n\n"
                f"📁 الملفات: `{file_count}` ملف\n"
                f"📦 الحجم: `{zip_size_kb} KB`\n"
                f"🔐 الأسرار: مُزالة ✔\n"
                f"📤 الإرسال: تم ✔",
                parse_mode="Markdown",
            )
            logger.info(f"[DEPLOY] Sent ZIP to ADMIN_ID={ADMIN_ID} ({zip_size_kb} KB)")

    except Exception as e:
        logger.error(f"[DEPLOY] Error: {e}", exc_info=True)
        try:
            await status_msg.edit_text(f"❌ حدث خطأ أثناء التجهيز:\n`{e}`", parse_mode="Markdown")
        except Exception:
            pass

    ctx.user_data["fsm_state"] = states.DEPLOY_MENU
    return states.DEPLOY_MENU
