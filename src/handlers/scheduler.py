import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from src.database import DB
from src import keyboards, states

logger = logging.getLogger(__name__)


async def scheduler_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏰ *إدارة الجدولة*", parse_mode="Markdown",
                              reply_markup=keyboards.scheduler_menu())


async def sched_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    schedules = DB.get_schedules()
    if not schedules:
        await q.edit_message_text("لا توجد جدولات بعد.",
                                  reply_markup=keyboards.back_button("menu_scheduler"))
        return
    await q.edit_message_text(f"📋 *الجدولات ({len(schedules)})*",
                              parse_mode="Markdown",
                              reply_markup=keyboards.schedules_list_keyboard(schedules))


async def sched_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sched_id = int(q.data.split("_")[-1])
    schedules = DB.get_schedules()
    sched = next((s for s in schedules if s["id"] == sched_id), None)
    if not sched:
        await q.edit_message_text("الجدولة غير موجودة.", reply_markup=keyboards.back_button("sched_list"))
        return
    status = "✅ نشطة" if sched["is_active"] else "⛔ متوقفة"
    text = (f"⏰ *{sched['name']}*\n\n"
            f"الحالة: {status}\n"
            f"كل: {sched['interval_hours']} ساعة\n"
            f"عدد التشغيل: {sched['run_count']}\n"
            f"التشغيل التالي: {sched['next_run'] or 'غير محدد'}")
    await q.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=keyboards.schedule_actions(sched_id, sched["is_active"]))


async def sched_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    sched_id = int(parts[-2])
    new_state = int(parts[-1])
    DB.toggle_schedule(sched_id, new_state)
    state_text = "✅ تم تفعيل الجدولة." if new_state else "⏸ تم إيقاف الجدولة."
    await q.edit_message_text(state_text, reply_markup=keyboards.back_button("sched_list"))


async def sched_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sched_id = int(q.data.split("_")[-1])
    DB.delete_schedule(sched_id)
    await q.edit_message_text("🗑 تم حذف الجدولة.", reply_markup=keyboards.back_button("sched_list"))


# ── Create Schedule (Conversation) ────────────────────────────────────────────

async def sched_create_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏰ أرسل *اسم* الجدولة:", parse_mode="Markdown")
    return states.SCHEDULE_NAME


async def sched_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["sched_name"] = update.message.text.strip()
    ads = DB.get_ads(active_only=True)
    if not ads:
        await update.message.reply_text("❌ لا توجد إعلانات نشطة. أضف إعلاناً أولاً.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 اختر الإعلان:",
        reply_markup=keyboards.ads_select_keyboard(ads, "sched_pick_ad")
    )
    return states.SCHEDULE_AD


async def sched_pick_ad_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ad_id = int(q.data.split("_")[-1])
    ctx.user_data["sched_ad_id"] = ad_id
    await q.edit_message_text("⏱ كم ساعة بين كل تشغيل؟ (أرسل رقماً مثل: 2 أو 0.5):")
    return states.SCHEDULE_HOURS


async def sched_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        hours = float(update.message.text.strip())
        if hours <= 0:
            raise ValueError
        ctx.user_data["sched_hours"] = hours
    except ValueError:
        await update.message.reply_text("❌ أرسل رقماً صحيحاً أكبر من 0.")
        return states.SCHEDULE_HOURS

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 جميع الحسابات", callback_data="sched_target_all")],
        [InlineKeyboardButton("📱 حساب واحد", callback_data="sched_target_single")],
    ])
    await update.message.reply_text("🎯 اختر الهدف:", reply_markup=kb)
    return states.SCHEDULE_TARGET


async def sched_target_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target = q.data.split("_")[-1]
    ctx.user_data["sched_target"] = target

    if target == "single":
        accounts = DB.get_accounts(active_only=True)
        if not accounts:
            await q.edit_message_text("❌ لا توجد حسابات نشطة.")
            return ConversationHandler.END
        await q.edit_message_text("📱 اختر الحساب:",
                                  reply_markup=keyboards.accounts_select_keyboard(accounts, "sched_pick_acc"))
        return states.SCHEDULE_ACCOUNT
    else:
        ctx.user_data["sched_account_id"] = None
        return await _save_schedule(q, ctx)


async def sched_pick_acc_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    account_id = int(q.data.split("_")[-1])
    ctx.user_data["sched_account_id"] = account_id
    return await _save_schedule(q, ctx)


async def _save_schedule(q_or_update, ctx):
    name = ctx.user_data.get("sched_name", "جدولة جديدة")
    ad_id = ctx.user_data["sched_ad_id"]
    hours = ctx.user_data["sched_hours"]
    target = ctx.user_data.get("sched_target", "all")
    account_id = ctx.user_data.get("sched_account_id")

    DB.add_schedule(name, ad_id, target, account_id, hours)
    msg = f"✅ تم إنشاء الجدولة *{name}*\nكل {hours} ساعة"

    if hasattr(q_or_update, "edit_message_text"):
        await q_or_update.edit_message_text(msg, parse_mode="Markdown",
                                            reply_markup=keyboards.scheduler_menu())
    else:
        await q_or_update.reply_text(msg, parse_mode="Markdown",
                                     reply_markup=keyboards.scheduler_menu())
    return ConversationHandler.END


async def sched_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END
