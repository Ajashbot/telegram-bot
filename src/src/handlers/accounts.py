import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.telethon_manager import telethon_mgr
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu display ──────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📱 *قسم الحسابات*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.accounts_menu())
    return states.ACCOUNTS_MENU

# ── List ──────────────────────────────────────────────────────────────────────

async def list_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts()
    if not accounts:
        await update.message.reply_text("لا توجد حسابات مضافة بعد.",
                                        reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU

    lines = []
    for i, acc in enumerate(accounts, 1):
        status = "✅" if acc["is_active"] else "⛔"
        lines.append(f"{i}. {status} {acc['name'] or acc['phone']} | {acc['phone']}")

    await update.message.reply_text(
        f"📋 *الحسابات ({len(accounts)})*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboards.accounts_menu()
    )
    return states.ACCOUNTS_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = DB.get_account_stats()
    await update.message.reply_text(
        f"📊 *إحصائيات الحسابات*\n\n"
        f"الإجمالي: {s['total']}\n"
        f"النشطة: {s['active']}\n"
        f"المتوقفة: {s['inactive']}",
        parse_mode="Markdown",
        reply_markup=keyboards.accounts_menu()
    )
    return states.ACCOUNTS_MENU

# ── Activate / Deactivate ─────────────────────────────────────────────────────

async def ask_activate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts()
    inactive = [a for a in accounts if not a["is_active"]]
    if not inactive:
        await update.message.reply_text("لا توجد حسابات متوقفة.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    ctx.user_data["acc_action"] = "activate"
    kb = keyboards.list_keyboard(inactive, "phone", back_label="❌ إلغاء", prefix="▶️ ")
    await update.message.reply_text("اختر الحساب لتفعيله:", reply_markup=kb)
    return states.ACC_SELECT_ACTION

async def ask_deactivate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts()
    active = [a for a in accounts if a["is_active"]]
    if not active:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    ctx.user_data["acc_action"] = "deactivate"
    kb = keyboards.list_keyboard(active, "phone", back_label="❌ إلغاء", prefix="⛔ ")
    await update.message.reply_text("اختر الحساب لإيقافه:", reply_markup=kb)
    return states.ACC_SELECT_ACTION

async def select_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU

    # Strip prefix
    phone = text.replace("▶️ ", "").replace("⛔ ", "").replace("🗑️ ", "").replace("🔄 ", "").strip()
    action = ctx.user_data.get("acc_action", "")

    accounts = DB.get_accounts()
    acc = next((a for a in accounts if a["phone"] == phone), None)
    if not acc:
        await update.message.reply_text("الحساب غير موجود.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU

    if action == "activate":
        DB.update_account_status(acc["id"], 1, "active")
        await update.message.reply_text(f"✅ تم تفعيل الحساب {phone}", reply_markup=keyboards.accounts_menu())
    elif action == "deactivate":
        DB.update_account_status(acc["id"], 0, "inactive")
        await update.message.reply_text(f"⛔ تم إيقاف الحساب {phone}", reply_markup=keyboards.accounts_menu())
    elif action == "delete":
        ctx.user_data["delete_acc_id"] = acc["id"]
        ctx.user_data["delete_acc_phone"] = phone
        await update.message.reply_text(
            f"⚠️ هل أنت متأكد من حذف الحساب {phone}؟",
            reply_markup=keyboards.confirm_menu()
        )
        return states.ACC_CONFIRM_DELETE
    elif action == "refresh":
        await update.message.reply_text(f"🔄 جاري تحديث جلسة {phone}...")
        ok = await telethon_mgr.update_session(acc["id"])
        msg = "✅ تم تحديث الجلسة." if ok else "❌ فشل تحديث الجلسة."
        await update.message.reply_text(msg, reply_markup=keyboards.accounts_menu())

    return states.ACCOUNTS_MENU

# ── Delete ─────────────────────────────────────────────────────────────────────

async def ask_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts()
    if not accounts:
        await update.message.reply_text("لا توجد حسابات.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    ctx.user_data["acc_action"] = "delete"
    kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="🗑️ ")
    await update.message.reply_text("اختر الحساب للحذف:", reply_markup=kb)
    return states.ACC_SELECT_ACTION

async def confirm_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "✅ تأكيد":
        acc_id = ctx.user_data.get("delete_acc_id")
        phone = ctx.user_data.get("delete_acc_phone", "")
        await telethon_mgr.disconnect_account(acc_id)
        DB.delete_account(acc_id)
        await update.message.reply_text(f"🗑️ تم حذف الحساب {phone}", reply_markup=keyboards.accounts_menu())
    else:
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.accounts_menu())
    return states.ACCOUNTS_MENU

# ── Refresh session ───────────────────────────────────────────────────────────

async def ask_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    ctx.user_data["acc_action"] = "refresh"
    kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="🔄 ")
    await update.message.reply_text("اختر الحساب لتحديث جلسته:", reply_markup=kb)
    return states.ACC_SELECT_ACTION

# ── Add Account (conversation) ────────────────────────────────────────────────

async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 أرسل رقم الهاتف بالصيغة الدولية:\nمثال: `+966501234567`\n\nأو اضغط إلغاء.",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.ACC_ADD_PHONE

async def recv_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    phone = text
    ctx.user_data["acc_phone"] = phone
    await update.message.reply_text("⏳ جاري إرسال رمز التحقق...")
    try:
        result = await telethon_mgr.start_login(phone)
        if result == "code_sent":
            await update.message.reply_text(
                "✅ تم إرسال الرمز.\n📨 أرسل رمز التحقق الآن:",
                reply_markup=keyboards.cancel_only()
            )
            return states.ACC_ADD_CODE
        else:
            await update.message.reply_text(f"❌ خطأ: {result}", reply_markup=keyboards.accounts_menu())
            return states.ACCOUNTS_MENU
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU

async def recv_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    phone = ctx.user_data.get("acc_phone", "")
    ctx.user_data["acc_code"] = text
    await update.message.reply_text("⏳ جاري التحقق...")
    try:
        result = await telethon_mgr.complete_login(phone, text)
        if result == "success":
            await update.message.reply_text("✅ تم تسجيل الحساب بنجاح!", reply_markup=keyboards.accounts_menu())
            return states.ACCOUNTS_MENU
        elif result == "2fa_required":
            await update.message.reply_text(
                "🔐 أرسل كلمة مرور التحقق الثنائي (2FA):",
                reply_markup=keyboards.cancel_only()
            )
            return states.ACC_ADD_2FA
        else:
            await update.message.reply_text(f"❌ خطأ: {result}", reply_markup=keyboards.accounts_menu())
            return states.ACCOUNTS_MENU
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU

async def recv_2fa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.accounts_menu())
        return states.ACCOUNTS_MENU
    phone = ctx.user_data.get("acc_phone", "")
    code = ctx.user_data.get("acc_code", "")
    await update.message.reply_text("⏳ جاري التحقق...")
    try:
        result = await telethon_mgr.complete_login(phone, code, text)
        if result == "success":
            await update.message.reply_text("✅ تم تسجيل الحساب بنجاح!", reply_markup=keyboards.accounts_menu())
        else:
            await update.message.reply_text(f"❌ خطأ: {result}", reply_markup=keyboards.accounts_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=keyboards.accounts_menu())
    return states.ACCOUNTS_MENU
