import logging
import sqlite3
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.worker_pool import pool
from src.scheduler import scheduler
from src.telethon_manager import telethon_mgr
from src import keyboards, states

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "bot_data.db"

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _show_dashboard(update, ctx)
    return states.DASHBOARD_MENU

async def _show_dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    acc_stats = DB.get_account_stats()
    pub_stats = DB.get_publish_stats()
    join_stats = DB.get_join_stats()
    ads = DB.get_ads()
    folders = DB.get_folders()
    groups = DB.get_groups()
    running_tasks = DB.get_running_tasks()
    schedules = DB.get_schedules(active_only=True)

    text = (
        f"📊 *لوحة التحكم*\n"
        f"{'─' * 25}\n\n"
        f"📱 الحسابات: {acc_stats['total']} | نشط: {acc_stats['active']}\n"
        f"📢 الإعلانات: {len(ads)}\n"
        f"📂 المجلدات: {len(folders)}\n"
        f"👥 المجموعات: {len(groups)}\n"
        f"⏰ الجدولات النشطة: {len(schedules)}\n\n"
        f"📤 النشر: {pub_stats['total']} | ✅{pub_stats['success']} ❌{pub_stats['failed']}\n"
        f"📎 الانضمام: {join_stats['total']} | ✅{join_stats['success']} ❌{join_stats['failed']}\n\n"
        f"⚙️ المهام الجارية: {len(running_tasks)}\n"
        f"🔧 Worker Pool: {pool.active_count()}"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=keyboards.dashboard_menu())

# ── Refresh ───────────────────────────────────────────────────────────────────

async def refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _show_dashboard(update, ctx)
    return states.DASHBOARD_MENU

# ── Detailed Stats ─────────────────────────────────────────────────────────────

async def detailed_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pub = DB.get_publish_stats()
    join = DB.get_join_stats()
    pub_rate = f"{(pub['success']/pub['total']*100):.1f}%" if pub['total'] else "0%"
    join_rate = f"{(join['success']/join['total']*100):.1f}%" if join['total'] else "0%"

    all_tasks = DB.get_all_tasks(limit=200)
    task_done = sum(1 for t in all_tasks if t["status"] == "done")
    task_failed = sum(1 for t in all_tasks if t["status"] == "failed")

    accounts = DB.get_accounts()
    ads = DB.get_ads()
    total_variants = sum(len(DB.get_ad_variants(a["id"])) for a in ads)

    text = (
        f"📈 *إحصائيات مفصلة*\n"
        f"{'─' * 25}\n\n"
        f"📤 *النشر*\n"
        f"  إجمالي: {pub['total']}\n"
        f"  ناجح: {pub['success']} ({pub_rate})\n"
        f"  فاشل: {pub['failed']}\n\n"
        f"📎 *الانضمام*\n"
        f"  إجمالي: {join['total']}\n"
        f"  ناجح: {join['success']} ({join_rate})\n"
        f"  فاشل: {join['failed']}\n\n"
        f"⚙️ *المهام*\n"
        f"  منتهية: {task_done}\n"
        f"  فاشلة: {task_failed}\n\n"
        f"🧠 *الإعلانات*\n"
        f"  عدد الإعلانات: {len(ads)}\n"
        f"  إجمالي الصيغ: {total_variants}\n\n"
        f"📱 *الحسابات*\n"
        f"  إجمالي: {len(accounts)}\n"
        f"  نشط: {sum(1 for a in accounts if a['is_active'])}"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=keyboards.dashboard_menu())
    return states.DASHBOARD_MENU

# ── Last Errors ───────────────────────────────────────────────────────────────

async def last_errors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM errors ORDER BY occurred_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("✅ لا توجد أخطاء مسجلة!", reply_markup=keyboards.dashboard_menu())
        return states.DASHBOARD_MENU

    lines = []
    for r in rows:
        lines.append(f"❌ [{r['source']}] {r['error_type']}: {r['message'][:60]}")

    await update.message.reply_text(
        f"📋 *آخر الأخطاء ({len(rows)})*\n\n" + "\n\n".join(lines),
        parse_mode="Markdown", reply_markup=keyboards.dashboard_menu()
    )
    return states.DASHBOARD_MENU

# ── Quick Control ─────────────────────────────────────────────────────────────

async def quick_control(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from telegram import ReplyKeyboardMarkup
    kb = ReplyKeyboardMarkup([
        ["🛑 إيقاف جميع المهام", "🔌 قطع جميع الاتصالات"],
        ["⏹ إيقاف Scheduler",    "▶️ تشغيل Scheduler"],
        ["🔙 لوحة التحكم"],
    ], resize_keyboard=True)
    await update.message.reply_text(
        "⚡ *التحكم السريع*\nاختر العملية:",
        parse_mode="Markdown", reply_markup=kb
    )
    return states.DASHBOARD_MENU

async def quick_stop_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await pool.cancel_all()
    running = DB.get_running_tasks()
    for t in running:
        DB.cancel_task(t["id"])
    await update.message.reply_text("🛑 تم إيقاف جميع المهام.", reply_markup=keyboards.dashboard_menu())
    return states.DASHBOARD_MENU

async def quick_disconnect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await telethon_mgr.disconnect_all()
    await update.message.reply_text("🔌 تم قطع جميع اتصالات Telethon.", reply_markup=keyboards.dashboard_menu())
    return states.DASHBOARD_MENU

async def quick_stop_scheduler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await scheduler.stop()
    await update.message.reply_text("⏹ تم إيقاف المجدول.", reply_markup=keyboards.dashboard_menu())
    return states.DASHBOARD_MENU

async def quick_start_scheduler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await scheduler.start()
    await update.message.reply_text("▶️ تم تشغيل المجدول.", reply_markup=keyboards.dashboard_menu())
    return states.DASHBOARD_MENU
