import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📂 *قسم المجلدات*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.folders_menu())
    return states.FOLDERS_MENU

# ── List ──────────────────────────────────────────────────────────────────────

async def list_folders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    folders = DB.get_folders()
    if not folders:
        await update.message.reply_text("لا توجد مجلدات بعد.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    lines = []
    for i, f in enumerate(folders, 1):
        links = DB.get_folder_links(f["id"])
        lines.append(f"{i}. 📂 *{f['name']}* | {len(links)} رابط")
    await update.message.reply_text(
        f"📋 *المجلدات ({len(folders)})*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=keyboards.folders_menu()
    )
    return states.FOLDERS_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    folders = DB.get_folders()
    total_links = sum(len(DB.get_folder_links(f["id"])) for f in folders)
    await update.message.reply_text(
        f"📊 *إحصائيات المجلدات*\n\n"
        f"عدد المجلدات: {len(folders)}\n"
        f"إجمالي الروابط: {total_links}",
        parse_mode="Markdown", reply_markup=keyboards.folders_menu()
    )
    return states.FOLDERS_MENU

# ── Create Folder ─────────────────────────────────────────────────────────────

async def create_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📂 أرسل *اسم* المجلد الجديد:", parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.FOLDER_CREATE_NAME

async def recv_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    folder_id = DB.add_folder(text)
    ctx.user_data["new_folder_id"] = folder_id
    ctx.user_data["new_folder_name"] = text
    await update.message.reply_text(
        f"✅ تم إنشاء المجلد *{text}*!\n\n"
        f"📎 أرسل الروابط الآن (رابط في كل سطر).\n"
        f"أو اضغط ⏭ تخطي للتخطي.",
        parse_mode="Markdown",
        reply_markup=keyboards.skip_or_cancel()
    )
    return states.FOLDER_ADD_LINKS

# ── Add Links to Folder ───────────────────────────────────────────────────────

async def add_links_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    folders = DB.get_folders()
    if not folders:
        await update.message.reply_text("لا توجد مجلدات. أنشئ مجلداً أولاً.",
                                        reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    kb = keyboards.list_keyboard(folders, "name", back_label="❌ إلغاء", prefix="📂 ")
    await update.message.reply_text("اختر المجلد لإضافة روابط إليه:", reply_markup=kb)
    return states.FOLDER_ADD_SELECT

async def select_folder_for_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    folder_name = text.replace("📂 ", "").strip()
    folders = DB.get_folders()
    folder = next((f for f in folders if f["name"][:35] == folder_name[:35]), None)
    if not folder:
        await update.message.reply_text("المجلد غير موجود.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    ctx.user_data["new_folder_id"] = folder["id"]
    ctx.user_data["new_folder_name"] = folder["name"]
    await update.message.reply_text(
        f"📎 أرسل الروابط لمجلد *{folder['name']}* (رابط في كل سطر):",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.FOLDER_ADD_LINKS

async def recv_links(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    if text == "⏭ تخطي":
        name = ctx.user_data.get("new_folder_name", "")
        await update.message.reply_text(f"✅ تم إنشاء المجلد *{name}* بدون روابط.",
                                        parse_mode="Markdown", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    folder_id = ctx.user_data.get("new_folder_id")
    folder_name = ctx.user_data.get("new_folder_name", "")
    links = [l.strip() for l in text.split("\n") if l.strip()]
    if not links:
        await update.message.reply_text("❌ لم تُرسل روابط صحيحة.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    DB.add_folder_links(folder_id, links)
    await update.message.reply_text(
        f"✅ تم إضافة {len(links)} رابط إلى المجلد *{folder_name}*!",
        parse_mode="Markdown", reply_markup=keyboards.folders_menu()
    )
    return states.FOLDERS_MENU

# ── View Folder Links ──────────────────────────────────────────────────────────

async def view_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    folders = DB.get_folders()
    if not folders:
        await update.message.reply_text("لا توجد مجلدات.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    kb = keyboards.list_keyboard(folders, "name", back_label="❌ إلغاء", prefix="📂 ")
    await update.message.reply_text("اختر المجلد لعرض روابطه:", reply_markup=kb)
    return states.FOLDER_VIEW_SELECT

async def recv_view_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    folder_name = text.replace("📂 ", "").strip()
    folders = DB.get_folders()
    folder = next((f for f in folders if f["name"][:35] == folder_name[:35]), None)
    if not folder:
        await update.message.reply_text("المجلد غير موجود.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    links = DB.get_folder_links(folder["id"])
    if not links:
        await update.message.reply_text(f"المجلد *{folder['name']}* فارغ.",
                                        parse_mode="Markdown", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    lines = [f"{i+1}. {l['link']}" for i, l in enumerate(links[:30])]
    text_out = f"🔗 *روابط {folder['name']}* ({len(links)} رابط)\n\n" + "\n".join(lines)
    if len(links) > 30:
        text_out += f"\n\n_...وأكثر {len(links)-30} رابط_"
    await update.message.reply_text(text_out, parse_mode="Markdown", reply_markup=keyboards.folders_menu())
    return states.FOLDERS_MENU

# ── Delete Folder ─────────────────────────────────────────────────────────────

async def delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    folders = DB.get_folders()
    if not folders:
        await update.message.reply_text("لا توجد مجلدات.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    kb = keyboards.list_keyboard(folders, "name", back_label="❌ إلغاء", prefix="🗑️ ")
    await update.message.reply_text("اختر المجلد للحذف:", reply_markup=kb)
    return states.FOLDER_DEL_SELECT

async def recv_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    folder_name = text.replace("🗑️ ", "").strip()
    folders = DB.get_folders()
    folder = next((f for f in folders if f["name"][:35] == folder_name[:35]), None)
    if not folder:
        await update.message.reply_text("المجلد غير موجود.", reply_markup=keyboards.folders_menu())
        return states.FOLDERS_MENU
    DB.delete_folder(folder["id"])
    await update.message.reply_text(f"🗑️ تم حذف المجلد *{folder['name']}* وجميع روابطه.",
                                    parse_mode="Markdown", reply_markup=keyboards.folders_menu())
    return states.FOLDERS_MENU
