import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.ad_variants import generate_variants
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 *قسم الإعلانات*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.ads_menu())
    return states.ADS_MENU

# ── List ──────────────────────────────────────────────────────────────────────

async def list_ads(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads()
    if not ads:
        await update.message.reply_text("لا توجد إعلانات بعد.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    lines = []
    for i, ad in enumerate(ads, 1):
        variants = DB.get_ad_variants(ad["id"])
        status = "✅" if ad["is_active"] else "⛔"
        lines.append(f"{i}. {status} *{ad['title'][:30]}* | صيغ: {len(variants)}")
    await update.message.reply_text(
        f"📋 *الإعلانات ({len(ads)})*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboards.ads_menu()
    )
    return states.ADS_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads()
    total_variants = sum(len(DB.get_ad_variants(a["id"])) for a in ads)
    active = sum(1 for a in ads if a["is_active"])
    await update.message.reply_text(
        f"📊 *إحصائيات الإعلانات*\n\n"
        f"إجمالي الإعلانات: {len(ads)}\n"
        f"نشطة: {active}\n"
        f"إجمالي الصيغ: {total_variants}",
        parse_mode="Markdown",
        reply_markup=keyboards.ads_menu()
    )
    return states.ADS_MENU

# ── Add Ad ─────────────────────────────────────────────────────────────────────

async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 أرسل *عنوان* الإعلان:", parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.AD_ADD_TITLE

async def recv_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    ctx.user_data["ad_title"] = text
    await update.message.reply_text(
        "📝 الآن أرسل *محتوى* الإعلان (النص كاملاً):",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.AD_ADD_CONTENT

async def recv_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    title = ctx.user_data.get("ad_title", "إعلان")
    ad_id = DB.add_ad(title, text)
    await update.message.reply_text(f"✅ تم إضافة الإعلان *{title}*!\n\n⏳ جاري توليد 20 صيغة ذكية...",
                                    parse_mode="Markdown")
    try:
        variants = generate_variants(text, count=20)
        DB.add_ad_variants(ad_id, variants)
        await update.message.reply_text(f"✅ تم توليد {len(variants)} صيغة بنجاح!",
                                        reply_markup=keyboards.ads_menu())
    except Exception as e:
        logger.error(f"Variant generation error: {e}")
        await update.message.reply_text("⚠️ تم حفظ الإعلان لكن حدث خطأ في توليد الصيغ.",
                                        reply_markup=keyboards.ads_menu())
    return states.ADS_MENU

# ── Edit Ad ───────────────────────────────────────────────────────────────────

async def edit_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads()
    if not ads:
        await update.message.reply_text("لا توجد إعلانات.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="✏️ ")
    await update.message.reply_text("اختر الإعلان للتعديل:", reply_markup=kb)
    return states.AD_SELECT_EDIT

async def select_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    title = text.replace("✏️ ", "").strip()
    ads = DB.get_ads()
    ad = next((a for a in ads if a["title"][:35] == title[:35]), None)
    if not ad:
        await update.message.reply_text("الإعلان غير موجود.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    ctx.user_data["edit_ad_id"] = ad["id"]
    await update.message.reply_text(
        f"✏️ العنوان الحالي: *{ad['title']}*\n\nأرسل العنوان الجديد:",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.AD_EDIT_TITLE

async def recv_edit_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    ctx.user_data["edit_ad_title"] = text
    ad_id = ctx.user_data.get("edit_ad_id")
    ad = DB.get_ad(ad_id)
    await update.message.reply_text(
        f"📝 المحتوى الحالي:\n{ad['content'][:300]}...\n\nأرسل المحتوى الجديد:",
        reply_markup=keyboards.cancel_only()
    )
    return states.AD_EDIT_CONTENT

async def recv_edit_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    ad_id = ctx.user_data.get("edit_ad_id")
    title = ctx.user_data.get("edit_ad_title", "")
    DB.update_ad(ad_id, title, text)
    await update.message.reply_text("✅ تم تحديث الإعلان بنجاح!", reply_markup=keyboards.ads_menu())
    return states.ADS_MENU

# ── Delete Ad ─────────────────────────────────────────────────────────────────

async def delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads()
    if not ads:
        await update.message.reply_text("لا توجد إعلانات.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="🗑️ ")
    await update.message.reply_text("اختر الإعلان للحذف:", reply_markup=kb)
    return states.AD_SELECT_DELETE

async def select_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    title = text.replace("🗑️ ", "").strip()
    ads = DB.get_ads()
    ad = next((a for a in ads if a["title"][:35] == title[:35]), None)
    if not ad:
        await update.message.reply_text("الإعلان غير موجود.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    DB.delete_ad(ad["id"])
    await update.message.reply_text(f"🗑️ تم حذف الإعلان *{ad['title']}* وجميع صيغه.",
                                    parse_mode="Markdown", reply_markup=keyboards.ads_menu())
    return states.ADS_MENU

# ── Smart Variants (view) ──────────────────────────────────────────────────────

async def variants_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads()
    if not ads:
        await update.message.reply_text("لا توجد إعلانات.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="🧠 ")
    await update.message.reply_text("اختر الإعلان لعرض صيغه:", reply_markup=kb)
    return states.AD_SELECT_VARIANTS

async def select_variants(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    title = text.replace("🧠 ", "").strip()
    ads = DB.get_ads()
    ad = next((a for a in ads if a["title"][:35] == title[:35]), None)
    if not ad:
        await update.message.reply_text("الإعلان غير موجود.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    variants = DB.get_ad_variants(ad["id"])
    if not variants:
        await update.message.reply_text(
            f"لا توجد صيغ للإعلان *{ad['title']}*.\nاستخدم 'إعادة توليد الصيغ' أولاً.",
            parse_mode="Markdown", reply_markup=keyboards.ads_menu()
        )
        return states.ADS_MENU
    # Show first 5 variants
    lines = []
    for i, v in enumerate(variants[:5], 1):
        lines.append(f"*صيغة {i}* (استُخدمت {v['used_count']} مرة):\n{v['content'][:150]}...")
    summary = f"🧠 *صيغ إعلان: {ad['title']}* ({len(variants)} صيغة)\n\n" + "\n\n─────\n\n".join(lines)
    if len(variants) > 5:
        summary += f"\n\n_...وأكثر {len(variants)-5} صيغة_"
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=keyboards.ads_menu())
    return states.ADS_MENU

# ── Regenerate Variants ───────────────────────────────────────────────────────

async def regen_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ads = DB.get_ads()
    if not ads:
        await update.message.reply_text("لا توجد إعلانات.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    kb = keyboards.list_keyboard(ads, "title", back_label="❌ إلغاء", prefix="🔄 ")
    await update.message.reply_text("اختر الإعلان لإعادة توليد صيغه:", reply_markup=kb)
    return states.AD_SELECT_REGEN

async def select_regen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    title = text.replace("🔄 ", "").strip()
    ads = DB.get_ads()
    ad = next((a for a in ads if a["title"][:35] == title[:35]), None)
    if not ad:
        await update.message.reply_text("الإعلان غير موجود.", reply_markup=keyboards.ads_menu())
        return states.ADS_MENU
    await update.message.reply_text(f"⏳ جاري توليد 20 صيغة جديدة لـ *{ad['title']}*...",
                                    parse_mode="Markdown")
    try:
        # Delete old variants first
        conn = __import__("sqlite3").connect(str(__import__("pathlib").Path(__file__).parent.parent.parent / "bot_data.db"))
        conn.execute("DELETE FROM ad_variants WHERE ad_id=?", (ad["id"],))
        conn.commit()
        conn.close()
        variants = generate_variants(ad["content"], count=20)
        DB.add_ad_variants(ad["id"], variants)
        await update.message.reply_text(f"✅ تم توليد {len(variants)} صيغة جديدة!",
                                        reply_markup=keyboards.ads_menu())
    except Exception as e:
        logger.error(f"Regen error: {e}")
        await update.message.reply_text(f"❌ خطأ: {e}", reply_markup=keyboards.ads_menu())
    return states.ADS_MENU
