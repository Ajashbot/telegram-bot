import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.publish_service import publish_service
from src.worker_pool import pool
from src.scheduler import scheduler
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📤 *قسم النشر*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.publish_menu())
    return states.PUBLISH_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = DB.get_publish_stats()
    rate = f"{(s['success']/s['total']*100):.1f}%" if s['total'] else "0%"
    await update.message.reply_text(
        f"📊 *إحصائيات النشر*\n\n"
        f"الإجمالي: {s['total']}\n"
        f"ناجح: ✅ {s['success']}\n"
        f"فاشل: ❌ {s['failed']}\n"
        f"معدل النجاح: {rate}",
        parse_mode="Markdown", reply_markup=keyboards.publish_menu()
    )
    return states.PUBLISH_MENU

# ── Logs ──────────────────────────────────────────────────────────────────────

async def logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logs_list = DB.get_publish_logs(limit=20)
    if not logs_list:
        await update.message.reply_text("لا توجد سجلات بعد.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    lines = []
    for log in logs_list:
        icon = "✅" if log["status"] == "success" else "❌"
        lines.append(f"{icon} {log.get('phone','?')[:10]} → {log.get('group_title','?')[:20]}")
    await update.message.reply_text(
        f"📋 *آخر {len(logs_list)} عملية نشر*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=keyboards.publish_menu()
    )
    return states.PUBLISH_MENU

# ── Stop all ──────────────────────────────────────────────────────────────────

async def stop_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    running = DB.get_running_tasks()
    pub_tasks = [t for t in running if t["task_type"] == "publish"]
    for t in pub_tasks:
        DB.cancel_task(t["id"])
    # Cancel worker pool tasks with publish prefix
    active = pool.get_active_tasks()
    cancelled = 0
    for tid in list(active.keys()):
        if "publish" in tid:
            await pool.cancel_task(tid)
            cancelled += 1
    await update.message.reply_text(
        f"🛑 تم إيقاف {cancelled} عملية نشر نشطة.",
        reply_markup=keyboards.publish_menu()
    )
    return states.PUBLISH_MENU

# ── Emergency ─────────────────────────────────────────────────────────────────

async def emergency(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await pool.cancel_all()
    running = DB.get_running_tasks()
    for t in running:
        DB.cancel_task(t["id"])
    await update.message.reply_text(
        "🆘 *طوارئ النشر*\n\nتم إيقاف جميع العمليات النشطة!",
        parse_mode="Markdown", reply_markup=keyboards.publish_menu()
    )
    return states.PUBLISH_MENU

# ── Publish single (select account then ad) ───────────────────────────────────

async def pub_single_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    ctx.user_data["pub_mode"] = "single"
    kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="📱 ")
    await update.message.reply_text("اختر الحساب للنشر:", reply_markup=kb)
    return states.PUB_SELECT_ACCOUNT

async def select_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    phone = text.replace("📱 ", "").strip()
    accounts = DB.get_accounts()
    acc = next((a for a in accounts if a["phone"] == phone), None)
    if not acc:
        await update.message.reply_text("الحساب غير موجود.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    ctx.user_data["pub_account_id"] = acc["id"]
    ads = DB.get_ads(active_only=True)
    if not ads:
        await update.message.reply_text("لا توجد إعلانات نشطة.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="📢 ")
    await update.message.reply_text("اختر الإعلان:", reply_markup=kb)
    return states.PUB_SELECT_AD

# ── Publish all (select ad) ───────────────────────────────────────────────────

async def pub_all_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads(active_only=True)
    if not ads:
        await update.message.reply_text("لا توجد إعلانات نشطة.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    ctx.user_data["pub_mode"] = "all"
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="📢 ")
    await update.message.reply_text("اختر الإعلان للنشر بجميع الحسابات:", reply_markup=kb)
    return states.PUB_SELECT_AD

async def select_ad(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    title = text.replace("📢 ", "").strip()
    ads = DB.get_ads()
    ad = next((a for a in ads if a["title"][:35] == title[:35]), None)
    if not ad:
        await update.message.reply_text("الإعلان غير موجود.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    mode = ctx.user_data.get("pub_mode", "all")
    account_id = ctx.user_data.get("pub_account_id")
    await update.message.reply_text(f"⏳ جاري بدء النشر للإعلان *{ad['title']}*...",
                                    parse_mode="Markdown")
    msg = await publish_service.publish(ad["id"], target_type=mode, account_id=account_id)
    await update.message.reply_text(f"✅ {msg}", reply_markup=keyboards.publish_menu())
    return states.PUBLISH_MENU

# ── Schedule ──────────────────────────────────────────────────────────────────

async def schedule_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏰ أرسل *اسم* الجدولة:", parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.PUB_SCHEDULE_NAME

async def schedule_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    ctx.user_data["sched_name"] = text
    ads = DB.get_ads(active_only=True)
    if not ads:
        await update.message.reply_text("لا توجد إعلانات نشطة.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="📢 ")
    await update.message.reply_text("اختر الإعلان:", reply_markup=kb)
    return states.PUB_SCHEDULE_AD

async def schedule_ad(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    title = text.replace("📢 ", "").strip()
    ads = DB.get_ads()
    ad = next((a for a in ads if a["title"][:35] == title[:35]), None)
    if not ad:
        await update.message.reply_text("الإعلان غير موجود.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    ctx.user_data["sched_ad_id"] = ad["id"]
    await update.message.reply_text(
        "⏱ كم ساعة بين كل نشر؟ (مثال: 2 أو 0.5 أو 24):",
        reply_markup=keyboards.cancel_only()
    )
    return states.PUB_SCHEDULE_HOURS

async def schedule_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    try:
        hours = float(text)
        if hours <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً صحيحاً أكبر من 0.")
        return states.PUB_SCHEDULE_HOURS
    ctx.user_data["sched_hours"] = hours
    from telegram import ReplyKeyboardMarkup
    kb = ReplyKeyboardMarkup([
        ["👥 جميع الحسابات", "📱 حساب واحد"], ["❌ إلغاء"]
    ], resize_keyboard=True)
    await update.message.reply_text("🎯 اختر الهدف:", reply_markup=kb)
    return states.PUB_SCHEDULE_TARGET

async def schedule_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    if text == "📱 حساب واحد":
        ctx.user_data["sched_target"] = "single"
        accounts = DB.get_accounts(active_only=True)
        if not accounts:
            await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.publish_menu())
            return states.PUBLISH_MENU
        kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="📱 ")
        await update.message.reply_text("اختر الحساب:", reply_markup=kb)
        return states.PUB_SCHEDULE_ACC
    else:
        ctx.user_data["sched_target"] = "all"
        return await _save_schedule(update, ctx, account_id=None)

async def schedule_acc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.publish_menu())
        return states.PUBLISH_MENU
    phone = text.replace("📱 ", "").strip()
    accounts = DB.get_accounts()
    acc = next((a for a in accounts if a["phone"] == phone), None)
    account_id = acc["id"] if acc else None
    return await _save_schedule(update, ctx, account_id=account_id)

async def _save_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE, account_id):
    name = ctx.user_data.get("sched_name", "جدولة")
    ad_id = ctx.user_data["sched_ad_id"]
    hours = ctx.user_data["sched_hours"]
    target = ctx.user_data.get("sched_target", "all")
    DB.add_schedule(name, ad_id, target, account_id, hours)
    await update.message.reply_text(
        f"✅ تم إنشاء الجدولة *{name}*\nكل {hours} ساعة",
        parse_mode="Markdown", reply_markup=keyboards.publish_menu()
    )
    return states.PUBLISH_MENU
