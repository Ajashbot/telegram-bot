import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.worker_pool import pool
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚙️ *المهام الجارية*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.tasks_menu())
    return states.TASKS_MENU

# ── View running ──────────────────────────────────────────────────────────────

async def view_running(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    running = DB.get_running_tasks()
    active_pool = pool.get_active_tasks()
    active_count = pool.active_count()

    if not running and not active_count:
        await update.message.reply_text("لا توجد مهام جارية حالياً.", reply_markup=keyboards.tasks_menu())
        return states.TASKS_MENU

    lines = [f"🔧 Worker Pool النشط: {active_count} مهمة\n"]
    for t in running[:15]:
        desc = (t.get("description") or t["task_type"])[:50]
        lines.append(f"🔄 [{t['id']}] {desc}")

    await update.message.reply_text(
        f"📋 *المهام الجارية*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=keyboards.tasks_menu()
    )
    return states.TASKS_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    all_tasks = DB.get_all_tasks(limit=100)
    running = [t for t in all_tasks if t["status"] == "running"]
    done = [t for t in all_tasks if t["status"] == "done"]
    failed = [t for t in all_tasks if t["status"] == "failed"]
    cancelled = [t for t in all_tasks if t["status"] == "cancelled"]

    await update.message.reply_text(
        f"📊 *إحصائيات المهام*\n\n"
        f"🔄 جارية: {len(running)}\n"
        f"✅ منتهية: {len(done)}\n"
        f"❌ فاشلة: {len(failed)}\n"
        f"⏹ ملغاة: {len(cancelled)}\n"
        f"⚙️ Pool النشط: {pool.active_count()}",
        parse_mode="Markdown", reply_markup=keyboards.tasks_menu()
    )
    return states.TASKS_MENU

# ── Stop one task ─────────────────────────────────────────────────────────────

async def stop_one_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    running = DB.get_running_tasks()
    if not running:
        await update.message.reply_text("لا توجد مهام جارية.", reply_markup=keyboards.tasks_menu())
        return states.TASKS_MENU
    from telegram import ReplyKeyboardMarkup
    buttons = [[f"🛑 [{t['id']}] {(t.get('description') or t['task_type'])[:30]}"] for t in running[:15]]
    buttons.append(["❌ إلغاء"])
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("اختر المهمة لإيقافها:", reply_markup=kb)
    return states.TASK_STOP_SELECT

async def recv_stop_one(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.tasks_menu())
        return states.TASKS_MENU
    # Extract task ID from text like "🛑 [5] description"
    try:
        task_id_str = text.split("[")[1].split("]")[0]
        task_id = int(task_id_str)
        DB.cancel_task(task_id)
        await update.message.reply_text(f"⏹ تم إيقاف المهمة #{task_id}.", reply_markup=keyboards.tasks_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ لم أتمكن من تحديد المهمة: {e}", reply_markup=keyboards.tasks_menu())
    return states.TASKS_MENU

# ── Stop all ──────────────────────────────────────────────────────────────────

async def stop_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await pool.cancel_all()
    running = DB.get_running_tasks()
    for t in running:
        DB.cancel_task(t["id"])
    await update.message.reply_text(
        f"⏸️ تم إيقاف جميع المهام ({len(running)} مهمة).",
        reply_markup=keyboards.tasks_menu()
    )
    return states.TASKS_MENU

# ── Refresh ───────────────────────────────────────────────────────────────────

async def refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    running = DB.get_running_tasks()
    active = pool.active_count()
    await update.message.reply_text(
        f"🔄 *تحديث الحالة*\n\n"
        f"مهام قاعدة البيانات: {len(running)}\n"
        f"مهام Worker Pool: {active}",
        parse_mode="Markdown", reply_markup=keyboards.tasks_menu()
    )
    return states.TASKS_MENU
