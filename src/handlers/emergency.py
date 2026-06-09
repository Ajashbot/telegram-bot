import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.worker_pool import pool
from src.scheduler import scheduler
from src.telethon_manager import telethon_mgr
from src import keyboards

logger = logging.getLogger(__name__)


async def emergency_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 إيقاف جميع المهام", callback_data="em_stop_tasks")],
        [InlineKeyboardButton("⏹ إيقاف Scheduler", callback_data="em_stop_scheduler")],
        [InlineKeyboardButton("🔌 قطع جميع الاتصالات", callback_data="em_disconnect")],
        [InlineKeyboardButton("🔄 إعادة تشغيل Scheduler", callback_data="em_restart_scheduler")],
        [InlineKeyboardButton("🆘 إيقاف شامل", callback_data="em_full_stop")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="menu_main")],
    ])
    await q.edit_message_text(
        "🆘 *نظام الطوارئ*\n\n⚠️ اختر العملية بحذر:",
        parse_mode="Markdown",
        reply_markup=kb
    )


async def em_stop_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await pool.cancel_all()
    running = DB.get_running_tasks()
    for t in running:
        DB.cancel_task(t["id"])
    logger.warning("EMERGENCY: All tasks stopped")
    await q.edit_message_text("⏹ تم إيقاف جميع المهام.",
                              reply_markup=keyboards.back_button("menu_emergency"))


async def em_stop_scheduler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await scheduler.stop()
    logger.warning("EMERGENCY: Scheduler stopped")
    await q.edit_message_text("⏹ تم إيقاف المجدول.",
                              reply_markup=keyboards.back_button("menu_emergency"))


async def em_restart_scheduler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await scheduler.start()
    logger.info("Scheduler restarted via emergency panel")
    await q.edit_message_text("✅ تم إعادة تشغيل المجدول.",
                              reply_markup=keyboards.back_button("menu_emergency"))


async def em_disconnect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await telethon_mgr.disconnect_all()
    logger.warning("EMERGENCY: All Telethon connections disconnected")
    await q.edit_message_text("🔌 تم قطع جميع الاتصالات.",
                              reply_markup=keyboards.back_button("menu_emergency"))


async def em_full_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await pool.cancel_all()
    running = DB.get_running_tasks()
    for t in running:
        DB.cancel_task(t["id"])
    await scheduler.stop()
    await telethon_mgr.disconnect_all()
    ctx.user_data.clear()
    logger.warning("EMERGENCY: Full system stop executed")
    await q.edit_message_text(
        "🆘 *تم تنفيذ الإيقاف الشامل*\n\n"
        "✅ جميع المهام متوقفة\n"
        "✅ المجدول متوقف\n"
        "✅ جميع الاتصالات مقطوعة\n"
        "✅ جميع الحالات مسحت\n\n"
        "يمكنك العودة للقائمة الرئيسية وإعادة التشغيل.",
        parse_mode="Markdown",
        reply_markup=keyboards.main_menu()
    )
