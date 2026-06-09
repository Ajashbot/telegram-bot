#!/usr/bin/env python3
"""
Telegram Bot — Production Version
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
State engine: ctx.user_data["fsm_state"]  (NO ConversationHandler)
Persistence:  PicklePersistence → user_data survives restarts
Routing:      ROUTES[state][label] → handler  (single source of truth)
"""

import os, sys, asyncio, logging, logging.handlers
from pathlib import Path
from typing import Callable

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "bot.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("bot")

# ── Telegram imports ──────────────────────────────────────────────────────────
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, PicklePersistence, filters,
)

# ── Project imports ───────────────────────────────────────────────────────────
from src.database import init_db, DB
from src.worker_pool import pool
from src.scheduler import scheduler
from src.publish_service import publish_service
from src import keyboards, states
from src.handlers import (
    accounts  as acc_h,
    ads       as ads_h,
    publish   as pub_h,
    join      as join_h,
    folders   as fold_h,
    groups    as grp_h,
    tasks     as task_h,
    dashboard as dash_h,
    deploy    as dep_h,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
TXT       = filters.TEXT & ~filters.COMMAND
PERSIST   = Path(__file__).parent / "userdata.pkl"

# ═════════════════════════════════════════════════════════════════════════════
# ROUTES — SINGLE SOURCE OF TRUTH
# Structure: ROUTES[menu_state] = { "button_label": handler_fn }
# ═════════════════════════════════════════════════════════════════════════════
ROUTES: dict[int, dict[str, Callable]] = {

    states.MAIN_MENU: {
        "📱 الحسابات":              acc_h.show_menu,
        "📢 الإعلانات":             ads_h.show_menu,
        "📤 النشر":                 pub_h.show_menu,
        "📎 الانضمام":              join_h.show_menu,
        "📂 المجلدات":              fold_h.show_menu,
        "🔄 جلب المجموعات":         grp_h.show_menu,
        "⚙️ المهام الجارية":        task_h.show_menu,
        "📊 لوحة التحكم":           dash_h.show_menu,
        "📦 تجهيز ونقل المشروع":    dep_h.show_menu,
    },

    states.DEPLOY_MENU: {
        "🚀 تجهيز الحزمة وإرسالها": dep_h.do_deploy,
    },

    states.ACCOUNTS_MENU: {
        "➕ إضافة حساب":         acc_h.add_start,
        "📋 عرض الحسابات":       acc_h.list_accounts,
        "✅ تفعيل حساب":         acc_h.ask_activate,
        "⛔ إيقاف حساب":         acc_h.ask_deactivate,
        "🗑️ حذف حساب":          acc_h.ask_delete,
        "🔄 تحديث الجلسة":       acc_h.ask_refresh,
        "📊 إحصائيات الحسابات":  acc_h.stats,
    },

    states.ADS_MENU: {
        "➕ إضافة إعلان":         ads_h.add_start,
        "📋 عرض الإعلانات":       ads_h.list_ads,
        "✏️ تعديل إعلان":        ads_h.edit_start,
        "🗑️ حذف إعلان":          ads_h.delete_start,
        "🧠 الصياغات الذكية":     ads_h.variants_start,
        "🔄 إعادة توليد الصيغ":   ads_h.regen_start,
        "📊 إحصائيات الإعلانات":  ads_h.stats,
    },

    states.PUBLISH_MENU: {
        "📢 نشر بحساب واحد":            pub_h.pub_single_start,
        "📢 نشر بجميع الحسابات":        pub_h.pub_all_start,
        "⏰ جدولة النشر":               pub_h.schedule_start,
        "📊 إحصائيات النشر":            pub_h.stats,
        "📋 سجل النشر":                 pub_h.logs,
        "🛑 إيقاف جميع عمليات النشر":  pub_h.stop_all,
        "🆘 طوارئ النشر":              pub_h.emergency,
    },

    states.JOIN_MENU: {
        "🔗 انضمام رابط بحساب واحد":      join_h.links_single_start,
        "🔗 انضمام رابط بجميع الحسابات":  join_h.links_all_start,
        "📂 انضمام مجلد بحساب واحد":      join_h.folder_single_start,
        "📂 انضمام مجلد بجميع الحسابات":  join_h.folder_all_start,
        "⏰ جدولة الانضمام":              join_h.sched_start,
        "📊 إحصائيات الانضمام":           join_h.stats,
        "📋 سجل الانضمام":                join_h.logs,
        "🛑 إيقاف جميع عمليات الانضمام": join_h.stop_all,
        "🆘 طوارئ الانضمام":             join_h.emergency,
    },

    states.FOLDERS_MENU: {
        "➕ إنشاء مجلد":          fold_h.create_start,
        "📎 إضافة روابط لمجلد":   fold_h.add_links_start,
        "📋 عرض المجلدات":         fold_h.list_folders,
        "🗑️ حذف مجلد":           fold_h.delete_start,
        "📊 إحصائيات المجلدات":   fold_h.stats,
    },

    states.GROUPS_MENU: {
        "🔄 جلب مجموعات حساب واحد":     grp_h.fetch_one_start,
        "🔄 جلب مجموعات جميع الحسابات": grp_h.fetch_all,
        "📋 عرض المجموعات":              grp_h.view_groups,
        "🔍 البحث عن مجموعة":            grp_h.search_start,
        "🗑️ حذف مجموعة":               grp_h.delete_start,
        "📊 إحصائيات المجموعات":         grp_h.stats,
        "♻️ تحديث تلقائي":              grp_h.auto_update,
        "🆘 طوارئ جلب المجموعات":       grp_h.emergency,
    },

    states.TASKS_MENU: {
        "📋 عرض المهام الجارية":   task_h.view_running,
        "🛑 إيقاف مهمة":          task_h.stop_one_start,
        "⏸️ إيقاف جميع المهام":  task_h.stop_all,
        "🔄 تحديث الحالة":         task_h.refresh,
        "📊 إحصائيات المهام":      task_h.stats,
    },

    states.DASHBOARD_MENU: {
        "🔄 تحديث لوحة التحكم":   dash_h.refresh,
        "📊 إحصائيات مفصلة":      dash_h.detailed_stats,
        "📋 آخر الأخطاء":         dash_h.last_errors,
        "⚡ تحكم سريع":           dash_h.quick_control,
        "🛑 إيقاف جميع المهام":   dash_h.quick_stop_all,
        "🔌 قطع جميع الاتصالات":  dash_h.quick_disconnect,
        "⏹ إيقاف Scheduler":     dash_h.quick_stop_scheduler,
        "▶️ تشغيل Scheduler":    dash_h.quick_start_scheduler,
        "🔙 لوحة التحكم":         dash_h.show_menu,
    },
}

# ── Input-state handlers (waiting for free-text user input) ───────────────────
# When FSM is in one of these states, ANY text (except navigation) goes here.
INPUT_HANDLERS: dict[int, Callable] = {
    states.ACC_ADD_PHONE:       acc_h.recv_phone,
    states.ACC_ADD_CODE:        acc_h.recv_code,
    states.ACC_ADD_2FA:         acc_h.recv_2fa,
    states.ACC_SELECT_ACTION:   acc_h.select_action,
    states.ACC_CONFIRM_DELETE:  acc_h.confirm_delete,

    states.AD_ADD_TITLE:        ads_h.recv_title,
    states.AD_ADD_CONTENT:      ads_h.recv_content,
    states.AD_SELECT_EDIT:      ads_h.select_edit,
    states.AD_EDIT_TITLE:       ads_h.recv_edit_title,
    states.AD_EDIT_CONTENT:     ads_h.recv_edit_content,
    states.AD_SELECT_DELETE:    ads_h.select_delete,
    states.AD_SELECT_VARIANTS:  ads_h.select_variants,
    states.AD_SELECT_REGEN:     ads_h.select_regen,

    states.PUB_SELECT_AD:       pub_h.select_ad,
    states.PUB_SELECT_ACCOUNT:  pub_h.select_account,
    states.PUB_SCHEDULE_NAME:   pub_h.schedule_name,
    states.PUB_SCHEDULE_AD:     pub_h.schedule_ad,
    states.PUB_SCHEDULE_HOURS:  pub_h.schedule_hours,
    states.PUB_SCHEDULE_TARGET: pub_h.schedule_target,
    states.PUB_SCHEDULE_ACC:    pub_h.schedule_acc,

    states.JOIN_LINKS_SINGLE:    join_h.recv_links_single,
    states.JOIN_SELECT_ACC:      join_h.select_account,
    states.JOIN_LINKS_ALL:       join_h.recv_links_all,
    states.JOIN_FOLDER_SINGLE:   join_h.recv_folder_single,
    states.JOIN_FOLDER_ALL:      join_h.recv_folder_all,
    # Join Scheduler
    states.JOIN_SCHED_TYPE:      join_h.sched_select_type,
    states.JOIN_SCHED_ACC:       join_h.sched_select_acc,
    states.JOIN_SCHED_INPUT:     join_h.sched_recv_input,
    states.JOIN_SCHED_INTERVAL:  join_h.sched_recv_interval,

    states.FOLDER_CREATE_NAME:  fold_h.recv_name,
    states.FOLDER_ADD_SELECT:   fold_h.select_folder_for_add,
    states.FOLDER_ADD_LINKS:    fold_h.recv_links,
    states.FOLDER_DEL_SELECT:   fold_h.recv_delete,
    states.FOLDER_VIEW_SELECT:  fold_h.recv_view_select,

    states.GROUPS_FETCH_ONE:    grp_h.recv_fetch_one,
    states.GROUPS_SEARCH:       grp_h.recv_search,
    states.GROUPS_DELETE_SEL:   grp_h.recv_delete,

    states.TASK_STOP_SELECT:    task_h.recv_stop_one,
}

# ── Sub-state → parent section (for "رجوع / إلغاء") ─────────────────────────
_PARENT: dict[int, int] = {
    states.ACC_ADD_PHONE:       states.ACCOUNTS_MENU,
    states.ACC_ADD_CODE:        states.ACCOUNTS_MENU,
    states.ACC_ADD_2FA:         states.ACCOUNTS_MENU,
    states.ACC_SELECT_ACTION:   states.ACCOUNTS_MENU,
    states.ACC_CONFIRM_DELETE:  states.ACCOUNTS_MENU,

    states.AD_ADD_TITLE:        states.ADS_MENU,
    states.AD_ADD_CONTENT:      states.ADS_MENU,
    states.AD_SELECT_EDIT:      states.ADS_MENU,
    states.AD_EDIT_TITLE:       states.ADS_MENU,
    states.AD_EDIT_CONTENT:     states.ADS_MENU,
    states.AD_SELECT_DELETE:    states.ADS_MENU,
    states.AD_SELECT_VARIANTS:  states.ADS_MENU,
    states.AD_SELECT_REGEN:     states.ADS_MENU,

    states.PUB_SELECT_AD:       states.PUBLISH_MENU,
    states.PUB_SELECT_ACCOUNT:  states.PUBLISH_MENU,
    states.PUB_SCHEDULE_NAME:   states.PUBLISH_MENU,
    states.PUB_SCHEDULE_AD:     states.PUBLISH_MENU,
    states.PUB_SCHEDULE_HOURS:  states.PUBLISH_MENU,
    states.PUB_SCHEDULE_TARGET: states.PUBLISH_MENU,
    states.PUB_SCHEDULE_ACC:    states.PUBLISH_MENU,

    states.JOIN_LINKS_SINGLE:    states.JOIN_MENU,
    states.JOIN_SELECT_ACC:      states.JOIN_MENU,
    states.JOIN_LINKS_ALL:       states.JOIN_MENU,
    states.JOIN_FOLDER_SINGLE:   states.JOIN_MENU,
    states.JOIN_FOLDER_ALL:      states.JOIN_MENU,
    states.JOIN_SCHED_TYPE:      states.JOIN_MENU,
    states.JOIN_SCHED_ACC:       states.JOIN_MENU,
    states.JOIN_SCHED_INPUT:     states.JOIN_MENU,
    states.JOIN_SCHED_INTERVAL:  states.JOIN_MENU,

    states.FOLDER_CREATE_NAME:  states.FOLDERS_MENU,
    states.FOLDER_ADD_SELECT:   states.FOLDERS_MENU,
    states.FOLDER_ADD_LINKS:    states.FOLDERS_MENU,
    states.FOLDER_DEL_SELECT:   states.FOLDERS_MENU,
    states.FOLDER_VIEW_SELECT:  states.FOLDERS_MENU,

    states.GROUPS_FETCH_ONE:    states.GROUPS_MENU,
    states.GROUPS_SEARCH:       states.GROUPS_MENU,
    states.GROUPS_DELETE_SEL:   states.GROUPS_MENU,

    states.TASK_STOP_SELECT:    states.TASKS_MENU,
}

# ── Section menu display functions ────────────────────────────────────────────
_SECTION_SHOW: dict[int, Callable] = {
    states.MAIN_MENU:     None,   # handled by _go_main
    states.ACCOUNTS_MENU: acc_h.show_menu,
    states.ADS_MENU:      ads_h.show_menu,
    states.PUBLISH_MENU:  pub_h.show_menu,
    states.JOIN_MENU:     join_h.show_menu,
    states.FOLDERS_MENU:  fold_h.show_menu,
    states.GROUPS_MENU:   grp_h.show_menu,
    states.TASKS_MENU:    task_h.show_menu,
    states.DASHBOARD_MENU: dash_h.show_menu,
    states.DEPLOY_MENU:   dep_h.show_menu,
}

# ═════════════════════════════════════════════════════════════════════════════
# CORE DISPATCHER
# ═════════════════════════════════════════════════════════════════════════════

async def _go_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🏠 *القائمة الرئيسية*\nاختر قسماً:",
        parse_mode="Markdown",
        reply_markup=keyboards.main_menu()
    )
    return states.MAIN_MENU


async def _go_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE, state: int) -> int:
    """Go back one level: sub-state → section menu, section menu → main."""
    parent = _PARENT.get(state)
    if parent is not None:
        show = _SECTION_SHOW.get(parent)
        if show:
            return await show(update, ctx)
    # Section menus go to main
    return await _go_main(update, ctx)


async def _dispatch(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                    state: int, t: str) -> int:
    # ── Universal navigation (works in every state) ───────────────────────────
    if t in ("🏠 الرئيسية",):
        return await _go_main(update, ctx)

    if t in ("🔙 رجوع", "❌ إلغاء"):
        return await _go_back(update, ctx, state)

    # ── Input state: send raw text to handler ─────────────────────────────────
    input_fn = INPUT_HANDLERS.get(state)
    if input_fn:
        return await input_fn(update, ctx)

    # ── Menu state: look up button in ROUTES ──────────────────────────────────
    menu_fn = ROUTES.get(state, {}).get(t)
    if menu_fn:
        return await menu_fn(update, ctx)

    # ── Post-restart rescue: button from a different section ──────────────────
    for other_state, buttons in ROUTES.items():
        if t in buttons:
            fn = buttons[t]
            logger.warning(f"[RESCUE] '{t}' found in state={other_state}, was in state={state}")
            return await fn(update, ctx)

    # ── Unknown button — log silently, re-show section ────────────────────────
    logger.warning(f"[UNKNOWN] state={state} text='{t}'")
    try:
        DB.log_error("router", "UnknownButton", f"state={state} label={t}")
    except Exception:
        pass
    # Re-show current section without sending an error message
    parent = _PARENT.get(state, state)
    show = _SECTION_SHOW.get(parent) or _SECTION_SHOW.get(state)
    if show:
        return await show(update, ctx)
    return await _go_main(update, ctx)


# ═════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text("⛔ غير مصرح.")
        return
    uid = update.effective_user.id
    logger.info(f"[START] uid={uid}")
    ctx.user_data["fsm_state"] = states.MAIN_MENU
    await update.message.reply_text(
        "🤖 *مرحباً بك في نظام البوت*\n\n"
        "🔧 WorkerPool: 20 عامل\n"
        "⏰ Scheduler: نشط\n"
        "🗄 قاعدة البيانات: جاهزة\n\n"
        "اختر قسماً:",
        parse_mode="Markdown",
        reply_markup=keyboards.main_menu()
    )


async def universal_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Single handler for ALL text messages. FSM state lives in user_data."""
    if not _is_admin(update):
        return

    t   = (update.message.text or "").strip()
    uid = update.effective_user.id

    # Read current state (default MAIN_MENU for new/unknown users)
    state = ctx.user_data.get("fsm_state", states.MAIN_MENU)
    logger.info(f"[MSG] uid={uid} state={state} text='{t}'")

    try:
        new_state = await _dispatch(update, ctx, state, t)
    except Exception as exc:
        logger.error(f"[HANDLER-ERR] uid={uid} state={state} text='{t}': {exc}", exc_info=True)
        try:
            DB.log_error("handler", type(exc).__name__, str(exc))
        except Exception:
            pass
        try:
            await update.message.reply_text(
                "❌ حدث خطأ داخلي — تم تسجيله.\nالرجاء المحاولة مرة أخرى.",
                reply_markup=keyboards.main_menu()
            )
        except Exception:
            pass
        new_state = states.MAIN_MENU

    # Persist new state
    if new_state is not None:
        ctx.user_data["fsm_state"] = new_state
        if new_state != state:
            logger.info(f"[STATE] uid={uid}  {state} → {new_state}")


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"[PTB-ERR] {type(ctx.error).__name__}: {ctx.error}", exc_info=ctx.error)
    try:
        DB.log_error("ptb", type(ctx.error).__name__, str(ctx.error))
    except Exception:
        pass
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ خطأ — تم تسجيله. الرجاء المحاولة.",
                reply_markup=keyboards.main_menu()
            )
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# BUILD APPLICATION
# ═════════════════════════════════════════════════════════════════════════════

def build_app() -> Application:
    persistence = PicklePersistence(filepath=str(PERSIST))
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(TXT, universal_handler))
    app.add_error_handler(error_handler)
    return app


async def on_startup(app: Application):
    logger.info("Starting background services...")
    await pool.start()
    scheduler.set_publish_callback(publish_service.publish_scheduled)
    await scheduler.start()
    logger.info("All services started ✅")


async def on_shutdown(app: Application):
    logger.info("Shutting down...")
    await pool.stop()
    await scheduler.stop()
    from src.telethon_manager import telethon_mgr
    await telethon_mgr.disconnect_all()
    logger.info("Shutdown complete.")


# ═════════════════════════════════════════════════════════════════════════════
# STARTUP VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

def _validate():
    total = sum(len(v) for v in ROUTES.values())
    input_count = len(INPUT_HANDLERS)
    logger.info(f"[ROUTES] {total} menu buttons + {input_count} input states registered ✅")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not set!"); sys.exit(1)
    if not ADMIN_ID:
        logger.critical("ADMIN_ID not set!"); sys.exit(1)

    init_db()
    logger.info("Database initialized")
    _validate()

    # Remove old ConversationHandler pickle (incompatible format)
    for old in ["conversations.pkl"]:
        p = Path(__file__).parent / old
        if p.exists():
            p.unlink()
            logger.info(f"Removed stale file: {old}")

    # Validate new persistence file
    if PERSIST.exists():
        import pickle
        try:
            with open(PERSIST, "rb") as f:
                pickle.load(f)
            logger.info("Persistence file OK")
        except Exception:
            logger.warning("Corrupt persistence file — resetting")
            PERSIST.unlink(missing_ok=True)

    app = build_app()
    app.post_init     = on_startup
    app.post_shutdown = on_shutdown

    logger.info("Bot starting (polling)...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
