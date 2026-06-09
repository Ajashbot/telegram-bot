import logging
from telegram import Update
from telegram.ext import ContextTypes
from src.database import DB
from src.join_service import join_service
from src.worker_pool import pool
from src import keyboards, states

logger = logging.getLogger(__name__)

# ── Menu ─────────────────────────────────────────────────────────────────────

async def show_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📎 *قسم الانضمام*\nاختر من القائمة:",
                                    parse_mode="Markdown",
                                    reply_markup=keyboards.join_menu())
    return states.JOIN_MENU

# ── Stats ─────────────────────────────────────────────────────────────────────

async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = DB.get_join_stats()
    rate = f"{(s['success']/s['total']*100):.1f}%" if s['total'] else "0%"
    await update.message.reply_text(
        f"📊 *إحصائيات الانضمام*\n\n"
        f"الإجمالي: {s['total']}\n"
        f"ناجح: ✅ {s['success']}\n"
        f"فاشل: ❌ {s['failed']}\n"
        f"معدل النجاح: {rate}",
        parse_mode="Markdown", reply_markup=keyboards.join_menu()
    )
    return states.JOIN_MENU

# ── Logs ──────────────────────────────────────────────────────────────────────

async def logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logs_list = DB.get_join_logs(limit=20)
    if not logs_list:
        await update.message.reply_text("لا توجد سجلات بعد.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    lines = []
    for log in logs_list:
        icon = "✅" if log["status"] == "success" else "❌"
        lines.append(f"{icon} {log.get('phone','?')[:10]} → {log['link'][:30]}")
    await update.message.reply_text(
        f"📋 *آخر {len(logs_list)} عملية انضمام*\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=keyboards.join_menu()
    )
    return states.JOIN_MENU

# ── Stop all ──────────────────────────────────────────────────────────────────

async def stop_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = pool.get_active_tasks()
    cancelled = 0
    for tid in list(active.keys()):
        if "join" in tid:
            await pool.cancel_task(tid)
            cancelled += 1
    running = DB.get_running_tasks()
    for t in running:
        if t["task_type"] == "join":
            DB.cancel_task(t["id"])
    await update.message.reply_text(f"🛑 تم إيقاف {cancelled} عملية انضمام.",
                                    reply_markup=keyboards.join_menu())
    return states.JOIN_MENU

# ── Emergency ─────────────────────────────────────────────────────────────────

async def emergency(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await pool.cancel_all()
    running = DB.get_running_tasks()
    for t in running:
        DB.cancel_task(t["id"])
    await update.message.reply_text(
        "🆘 *طوارئ الانضمام*\n\nتم إيقاف جميع العمليات!",
        parse_mode="Markdown", reply_markup=keyboards.join_menu()
    )
    return states.JOIN_MENU

# ── Join links single (ask account first) ─────────────────────────────────────

async def links_single_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    ctx.user_data["join_mode"] = "single"
    ctx.user_data["join_target"] = "links"
    kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="📱 ")
    await update.message.reply_text("اختر الحساب للانضمام:", reply_markup=kb)
    return states.JOIN_SELECT_ACC

async def links_all_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["join_mode"] = "all"
    ctx.user_data["join_target"] = "links"
    await update.message.reply_text(
        "🔗 أرسل الروابط (رابط في كل سطر):\n\nأو اضغط إلغاء.",
        reply_markup=keyboards.cancel_only()
    )
    return states.JOIN_LINKS_ALL

async def select_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    phone = text.replace("📱 ", "").strip()
    accounts = DB.get_accounts()
    acc = next((a for a in accounts if a["phone"] == phone), None)
    if not acc:
        await update.message.reply_text("الحساب غير موجود.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    ctx.user_data["join_account_id"] = acc["id"]
    target = ctx.user_data.get("join_target", "links")
    if target == "folder":
        # Select folder
        folders = DB.get_folders()
        if not folders:
            await update.message.reply_text("لا توجد مجلدات.", reply_markup=keyboards.join_menu())
            return states.JOIN_MENU
        kb = keyboards.list_keyboard(folders, "name", back_label="❌ إلغاء", prefix="📂 ")
        await update.message.reply_text("اختر المجلد:", reply_markup=kb)
        return states.JOIN_FOLDER_SINGLE
    else:
        await update.message.reply_text(
            "🔗 أرسل الروابط (رابط في كل سطر):\n\nأو اضغط إلغاء.",
            reply_markup=keyboards.cancel_only()
        )
        return states.JOIN_LINKS_SINGLE

async def recv_links_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    links = [l.strip() for l in text.split("\n") if l.strip()]
    if not links:
        await update.message.reply_text("❌ لم تُرسل روابط صحيحة.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    account_id = ctx.user_data.get("join_account_id")
    await update.message.reply_text(f"⏳ جاري الانضمام إلى {len(links)} رابط...")
    msg = await join_service.join(links, target_type="single", account_id=account_id)
    await update.message.reply_text(f"✅ {msg}", reply_markup=keyboards.join_menu())
    return states.JOIN_MENU

async def recv_links_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    links = [l.strip() for l in text.split("\n") if l.strip()]
    if not links:
        await update.message.reply_text("❌ لم تُرسل روابط صحيحة.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    await update.message.reply_text(f"⏳ جاري الانضمام إلى {len(links)} رابط بجميع الحسابات...")
    msg = await join_service.join(links, target_type="all")
    await update.message.reply_text(f"✅ {msg}", reply_markup=keyboards.join_menu())
    return states.JOIN_MENU

# ── Join folder ───────────────────────────────────────────────────────────────

async def folder_single_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    accounts = DB.get_accounts(active_only=True)
    if not accounts:
        await update.message.reply_text("لا توجد حسابات نشطة.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    ctx.user_data["join_mode"] = "single"
    ctx.user_data["join_target"] = "folder"
    kb = keyboards.list_keyboard(accounts, "phone", back_label="❌ إلغاء", prefix="📱 ")
    await update.message.reply_text("اختر الحساب:", reply_markup=kb)
    return states.JOIN_SELECT_ACC

async def folder_all_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    folders = DB.get_folders()
    if not folders:
        await update.message.reply_text("لا توجد مجلدات.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    ctx.user_data["join_mode"] = "all"
    kb = keyboards.list_keyboard(folders, "name", back_label="❌ إلغاء", prefix="📂 ")
    await update.message.reply_text("اختر المجلد للانضمام بجميع الحسابات:", reply_markup=kb)
    return states.JOIN_FOLDER_ALL

async def recv_folder_single(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    folder_name = text.replace("📂 ", "").strip()
    folders = DB.get_folders()
    folder = next((f for f in folders if f["name"][:35] == folder_name[:35]), None)
    if not folder:
        await update.message.reply_text("المجلد غير موجود.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    account_id = ctx.user_data.get("join_account_id")
    await update.message.reply_text(f"⏳ جاري الانضمام من المجلد *{folder['name']}*...",
                                    parse_mode="Markdown")
    msg = await join_service.join_folder(folder["id"], target_type="single", account_id=account_id)
    await update.message.reply_text(f"✅ {msg}", reply_markup=keyboards.join_menu())
    return states.JOIN_MENU

async def recv_folder_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "❌ إلغاء":
        await update.message.reply_text("❌ تم الإلغاء.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    folder_name = text.replace("📂 ", "").strip()
    folders = DB.get_folders()
    folder = next((f for f in folders if f["name"][:35] == folder_name[:35]), None)
    if not folder:
        await update.message.reply_text("المجلد غير موجود.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU
    await update.message.reply_text(f"⏳ جاري الانضمام من المجلد *{folder['name']}* بجميع الحسابات...",
                                    parse_mode="Markdown")
    msg = await join_service.join_folder(folder["id"], target_type="all")
    await update.message.reply_text(f"✅ {msg}", reply_markup=keyboards.join_menu())
    return states.JOIN_MENU


# ═══════════════════════════════════════════════════════════════════════════════
# ⏰ JOIN SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

async def sched_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Entry: show join-type selection for the scheduler."""
    await update.message.reply_text(
        "⏰ *جدولة الانضمام*\n\n"
        "اختر نوع الانضمام المطلوب جدولته:",
        parse_mode="Markdown",
        reply_markup=keyboards.join_sched_type_menu()
    )
    return states.JOIN_SCHED_TYPE


async def sched_select_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle type selection button (links/folder × single/all)."""
    text = update.message.text.strip()

    is_links  = "روابط" in text
    is_folder = "مجلد"  in text
    is_single = "واحد"  in text

    if not (is_links or is_folder):
        await update.message.reply_text("اختر من الأزرار أدناه.",
                                        reply_markup=keyboards.join_sched_type_menu())
        return states.JOIN_SCHED_TYPE

    ctx.user_data["jsched_mode"]   = "links" if is_links else "folder"
    ctx.user_data["jsched_target"] = "single" if is_single else "all"

    if is_single:
        accounts = DB.get_accounts(active_only=True)
        if not accounts:
            await update.message.reply_text("❌ لا توجد حسابات نشطة.",
                                            reply_markup=keyboards.join_menu())
            return states.JOIN_MENU
        kb = keyboards.list_keyboard(accounts, "phone", prefix="📱 ")
        await update.message.reply_text("📱 اختر الحساب:", reply_markup=kb)
        return states.JOIN_SCHED_ACC

    # "all" mode — go straight to content input
    if is_folder:
        folders = DB.get_folders()
        if not folders:
            await update.message.reply_text("❌ لا توجد مجلدات.", reply_markup=keyboards.join_menu())
            return states.JOIN_MENU
        kb = keyboards.list_keyboard(folders, "name", prefix="📂 ")
        await update.message.reply_text("📂 اختر المجلد:", reply_markup=kb)
    else:
        await update.message.reply_text(
            "🔗 أرسل الروابط (رابط في كل سطر):",
            reply_markup=keyboards.cancel_only()
        )
    return states.JOIN_SCHED_INPUT


async def sched_select_acc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle account selection for single-account scheduler."""
    text  = update.message.text.strip()
    phone = text.replace("📱 ", "").strip()

    accounts = DB.get_accounts()
    acc = next((a for a in accounts if a["phone"] == phone), None)
    if not acc:
        await update.message.reply_text("الحساب غير موجود.", reply_markup=keyboards.join_menu())
        return states.JOIN_MENU

    ctx.user_data["jsched_account_id"] = acc["id"]
    mode = ctx.user_data.get("jsched_mode", "links")

    if mode == "folder":
        folders = DB.get_folders()
        if not folders:
            await update.message.reply_text("❌ لا توجد مجلدات.", reply_markup=keyboards.join_menu())
            return states.JOIN_MENU
        kb = keyboards.list_keyboard(folders, "name", prefix="📂 ")
        await update.message.reply_text("📂 اختر المجلد:", reply_markup=kb)
    else:
        await update.message.reply_text(
            "🔗 أرسل الروابط (رابط في كل سطر):",
            reply_markup=keyboards.cancel_only()
        )
    return states.JOIN_SCHED_INPUT


async def sched_recv_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive links (free text) or folder name (button) then ask for interval."""
    text = update.message.text.strip()
    mode = ctx.user_data.get("jsched_mode", "links")

    if mode == "folder":
        folder_name = text.replace("📂 ", "").strip()
        folders = DB.get_folders()
        folder = next((f for f in folders if f["name"][:35] == folder_name[:35]), None)
        if not folder:
            await update.message.reply_text(
                "❌ المجلد غير موجود. اختر من الأزرار:",
                reply_markup=keyboards.list_keyboard(folders, "name", prefix="📂 ")
                if folders else keyboards.join_menu()
            )
            return states.JOIN_SCHED_INPUT if folders else states.JOIN_MENU
        ctx.user_data["jsched_folder_id"]   = folder["id"]
        ctx.user_data["jsched_folder_name"] = folder["name"]
        ctx.user_data["jsched_link_count"]  = len(DB.get_folder_links(folder["id"]))
    else:
        links = [l.strip() for l in text.split("\n") if l.strip()]
        if not links:
            await update.message.reply_text(
                "❌ لم تُرسل روابط صحيحة. أرسل رابطاً في كل سطر:",
                reply_markup=keyboards.cancel_only()
            )
            return states.JOIN_SCHED_INPUT
        ctx.user_data["jsched_links"]      = links
        ctx.user_data["jsched_link_count"] = len(links)

    link_count = ctx.user_data.get("jsched_link_count", 0)
    await update.message.reply_text(
        f"✅ تم تحديد *{link_count}* رابط.\n\n"
        "⏱ *حدد الفاصل الزمني بين كل انضمام:*\n\n"
        "أمثلة صحيحة:\n"
        "• `5` أو `5s`  ← 5 ثواني\n"
        "• `30s`        ← 30 ثانية\n"
        "• `1m`         ← دقيقة كاملة\n"
        "• `2.5m`       ← دقيقتان ونصف\n"
        "• `0.5`        ← نصف ثانية\n\n"
        "أرسل القيمة الآن:",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only()
    )
    return states.JOIN_SCHED_INTERVAL


async def sched_recv_interval(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Parse interval, start background scheduled-join task."""
    text = update.message.text.strip().lower().replace(" ", "")

    # ── Parse interval ────────────────────────────────────────────────────────
    try:
        if text.endswith("m"):
            seconds = float(text[:-1]) * 60
        elif text.endswith("s"):
            seconds = float(text[:-1])
        else:
            seconds = float(text)
        if seconds < 0:
            raise ValueError("negative")
    except ValueError:
        await update.message.reply_text(
            "❌ قيمة غير صحيحة.\n"
            "أمثلة: `5s`  `30s`  `2m`  `1.5m`  `10`",
            parse_mode="Markdown"
        )
        return states.JOIN_SCHED_INTERVAL

    # ── Gather context ────────────────────────────────────────────────────────
    mode       = ctx.user_data.get("jsched_mode",   "links")
    target     = ctx.user_data.get("jsched_target", "all")
    account_id = ctx.user_data.get("jsched_account_id")
    link_count = ctx.user_data.get("jsched_link_count", 0)

    if mode == "folder":
        folder_id   = ctx.user_data.get("jsched_folder_id")
        folder_name = ctx.user_data.get("jsched_folder_name", "مجلد")
        source_desc = f"مجلد: {folder_name}"
    else:
        link_count  = len(ctx.user_data.get("jsched_links", []))
        source_desc = f"{link_count} رابط"

    target_label = "حساب واحد" if target == "single" else "جميع الحسابات"
    interval_str = f"{seconds:.0f}s" if seconds < 60 else f"{seconds/60:.1f}m"
    import time as _time
    task_id = f"jsched_{int(_time.time())}"

    await update.message.reply_text(
        f"⏰ *تم بدء جدولة الانضمام*\n\n"
        f"📊 المصدر: {source_desc}\n"
        f"🎯 الهدف: {target_label}\n"
        f"⏱ الفاصل الزمني: {interval_str} ({seconds:.1f} ثانية)\n"
        f"🔑 المعرف: `{task_id}`\n\n"
        f"البوت يعمل في الخلفية — يمكنك مراقبة التقدم من قسم المهام.",
        parse_mode="Markdown",
        reply_markup=keyboards.join_menu()
    )

    # ── Capture values for closure ────────────────────────────────────────────
    _mode       = mode
    _target     = target
    _account_id = account_id
    _folder_id  = ctx.user_data.get("jsched_folder_id")
    _links      = list(ctx.user_data.get("jsched_links", []))
    _seconds    = seconds

    # ── Build and submit background coroutine ─────────────────────────────────
    async def _run():
        import asyncio as _aio
        from src.telethon_manager import telethon_mgr

        db_task = DB.add_task("join_sched", f"جدولة انضمام {source_desc} | فاصل: {interval_str}")
        logger.info(f"[JSCHED:{task_id}] START mode={_mode} target={_target} interval={_seconds}s")

        try:
            # Resolve link list
            if _mode == "folder":
                rows  = DB.get_folder_links(_folder_id)
                links = [r["link"] for r in rows]
            else:
                links = _links

            if not links:
                logger.warning(f"[JSCHED:{task_id}] No links — aborting.")
                DB.finish_task(db_task, "done", "No links")
                return

            # Resolve accounts
            if _target == "all":
                accounts = DB.get_accounts(active_only=True)
            else:
                a = DB.get_account(_account_id)
                accounts = [a] if a else []

            if not accounts:
                logger.warning(f"[JSCHED:{task_id}] No accounts — aborting.")
                DB.finish_task(db_task, "done", "No accounts")
                return

            total_ok = 0
            total_fail = 0
            start_ts = _aio.get_event_loop().time()

            logger.info(
                f"[JSCHED:{task_id}] Running: {len(links)} links × "
                f"{len(accounts)} accounts | interval={_seconds}s"
            )

            for link_idx, link in enumerate(links, 1):
                for acc_idx, acc in enumerate(accounts, 1):
                    try:
                        ok = await telethon_mgr.join_group(acc["id"], link)
                        status = "success" if ok else "failed"
                        err    = None if ok else "join_group returned False"
                    except Exception as e:
                        status = "failed"
                        err    = str(e)
                        logger.error(
                            f"[JSCHED:{task_id}] Error acc={acc['phone']} link={link}: {e}"
                        )

                    DB.add_join_log(acc["id"], link, status, err)

                    if status == "success":
                        total_ok += 1
                        logger.info(
                            f"[JSCHED:{task_id}] ✅ [{link_idx}/{len(links)}] "
                            f"{acc['phone']} → {link}"
                        )
                    else:
                        total_fail += 1
                        logger.warning(
                            f"[JSCHED:{task_id}] ❌ [{link_idx}/{len(links)}] "
                            f"{acc['phone']} → {link} | {err}"
                        )

                    # Sleep between every individual join
                    if _seconds > 0:
                        logger.info(
                            f"[JSCHED:{task_id}] 💤 sleeping {_seconds}s "
                            f"(link {link_idx}/{len(links)}, acc {acc_idx}/{len(accounts)})"
                        )
                        await _aio.sleep(_seconds)

            elapsed = _aio.get_event_loop().time() - start_ts
            logger.info(
                f"[JSCHED:{task_id}] DONE ✅{total_ok} ❌{total_fail} "
                f"elapsed={elapsed:.1f}s"
            )
            DB.finish_task(db_task, "done")

        except Exception as e:
            logger.error(f"[JSCHED:{task_id}] FATAL: {e}", exc_info=True)
            DB.finish_task(db_task, "failed", str(e))

    await pool.submit(task_id, _run(), description=f"⏰ جدولة انضمام | {source_desc}")
    return states.JOIN_MENU
