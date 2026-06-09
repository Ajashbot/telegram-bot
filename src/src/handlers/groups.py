import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.telethon_manager import telethon_mgr
from src.worker_pool import pool
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 *قسم جلب المجموعات*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.groups_menu())
    return states.GROUPS_MENU

# ── View ──────────────────────────────────────────────────────────────────────

async def view_groups(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    groups = DB.get_groups()
    if not groups:
        await update.message.reply_text("لا توجد مجموعات محفوظة. اجلب المجموعات أولاً.",
                                        reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    lines = [f"{i+1}. {g['title'][:40]}" for i, g in enumerate(groups[:25])]
    text = f"📋 *المجموعات المحفوظة ({len(groups)})*\n\n" + "\n".join(lines)
    if len(groups) > 25:
        text += f"\n\n_...وأكثر {len(groups)-25} مجموعة_"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboards.groups_menu())
    return states.GROUPS_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    groups = DB.get_groups()
    accounts = DB.get_accounts()
    # Count per account
    per_acc = {}
    for g in groups:
        aid = g.get("account_id")
        per_acc[aid] = per_acc.get(aid, 0) + 1
    lines = [f"📊 *إحصائيات المجموعات*\n\nإجمالي المجموعات: {len(groups)}"]
    for acc in accounts:
        count = per_acc.get(acc["id"], 0)
        lines.append(f"📱 {acc['name'] or acc['phone']}: {count}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown",
                                    reply_markup=keyboards.groups_menu())
    return states.GROUPS_MENU

# ── Fetch one ─────────────────────────────────────────────────────────────────

async def fetch_one_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="📱 ")
    await update.message.reply_text("اختر الحساب لجلب مجموعاته:", reply_markup=kb)
    return states.GROUPS_FETCH_ONE

async def recv_fetch_one(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    phone = text.replace("📱 ", "").strip()
    accounts = DB.get_accounts()
    acc = next((a for a in accounts if a["phone"] == phone), None)
    if not acc:
        await update.message.reply_text("الحساب غير موجود.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    await update.message.reply_text(f"⏳ جاري جلب المجموعات لـ {phone}... (قد يستغرق دقيقة)")
    try:
        groups = await asyncio.wait_for(telethon_mgr.fetch_groups(acc["id"]), timeout=120)
        await update.message.reply_text(
            f"✅ تم جلب {len(groups)} مجموعة من {phone}!",
            reply_markup=keyboards.groups_menu()
        )
    except asyncio.TimeoutError:
        await update.message.reply_text("❌ انتهت مهلة الجلب.", reply_markup=keyboards.groups_menu())
    except Exception as e:
        logger.error(f"Fetch error: {e}")
        await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=keyboards.groups_menu())
    return states.GROUPS_MENU

# ── Fetch all ─────────────────────────────────────────────────────────────────

async def fetch_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    await update.message.reply_text(f"⏳ جاري جلب المجموعات من {len(accounts)} حساب... (قد يستغرق عدة دقائق)")
    total = 0
    for acc in accounts:
        try:
            groups = await asyncio.wait_for(telethon_mgr.fetch_groups(acc["id"]), timeout=120)
            total += len(groups)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Fetch all error for {acc['id']}: {e}")
    await update.message.reply_text(
        f"✅ تم جلب {total} مجموعة إجمالاً من {len(accounts)} حساب!",
        reply_markup=keyboards.groups_menu()
    )
    return states.GROUPS_MENU

# ── Auto update ───────────────────────────────────────────────────────────────

async def auto_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU

    async def _do_update():
        total = 0
        for acc in accounts:
            try:
                groups = await asyncio.wait_for(telethon_mgr.fetch_groups(acc["id"]), timeout=120)
                total += len(groups)
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"Auto-update error for {acc['id']}: {e}")
        logger.info(f"Auto-update complete: {total} groups")

    task_id = f"groups_auto_{asyncio.get_event_loop().time():.0f}"
    await pool.submit(task_id, _do_update(), description="تحديث تلقائي للمجموعات")
    await update.message.reply_text(
        "♻️ بدأ التحديث التلقائي في الخلفية.\nسيتم تحديث جميع المجموعات.",
        reply_markup=keyboards.groups_menu()
    )
    return states.GROUPS_MENU

# ── Search ────────────────────────────────────────────────────────────────────

async def search_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 أرسل اسم المجموعة أو جزء منه للبحث:",
        reply_markup=keyboards.cancel_only()
    )
    return states.GROUPS_SEARCH

async def recv_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    groups = DB.get_groups()
    results = [g for g in groups if text.lower() in (g.get("title") or "").lower()]
    if not results:
        await update.message.reply_text(f"لا توجد نتائج لـ '{text}'.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    lines = [f"{i+1}. {g['title'][:40]}" for i, g in enumerate(results[:20])]
    await update.message.reply_text(
        f"🔍 *نتائج البحث ({len(results)})*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=keyboards.groups_menu()
    )
    return states.GROUPS_MENU

# ── Delete group ──────────────────────────────────────────────────────────────

async def delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    groups = DB.get_groups()
    if not groups:
        await update.message.reply_text("لا توجد مجموعات للحذف.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    # Show first 20 as a keyboard
    from telegram import ReplyKeyboardMarkup
    buttons = [[f"🗑️ {g['title'][:35]}"] for g in groups[:20]]
    buttons.append(["❌ إلغاء"])
    kb = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("اختر المجموعة للحذف:", reply_markup=kb)
    return states.GROUPS_DELETE_SEL

async def recv_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    title = text.replace("🗑️ ", "").strip()
    groups = DB.get_groups()
    group = next((g for g in groups if g.get("title", "")[:35] == title[:35]), None)
    if not group:
        await update.message.reply_text("المجموعة غير موجودة.", reply_markup=keyboards.groups_menu())
        return states.GROUPS_MENU
    # Delete from DB
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent.parent / "bot_data.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM groups WHERE id=?", (group["id"],))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ تم حذف المجموعة *{group['title']}*.",
                                    parse_mode="Markdown", reply_markup=keyboards.groups_menu())
    return states.GROUPS_MENU

# ── Emergency ─────────────────────────────────────────────────────────────────

async def emergency(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = pool.get_active_tasks()
    cancelled = 0
    for tid in list(active.keys()):
        if "groups" in tid or "fetch" in tid:
            await pool.cancel_task(tid)
            cancelled += 1
    await update.message.reply_text(
        f"🆘 تم إيقاف {cancelled} عملية جلب مجموعات.",
        reply_markup=keyboards.groups_menu()
    )
    return states.GROUPS_MENU
