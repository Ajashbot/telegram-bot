import asyncio
import logging
from typing import List, Optional
from src.database import DB
from src.telethon_manager import telethon_mgr
from src.worker_pool import pool

logger = logging.getLogger(__name__)


class JoinService:
    async def join(self, links: List[str], target_type: str = "all",
                   account_id: int = None, delay: float = 3.0) -> str:
        if target_type == "all":
            accounts = DB.get_accounts(active_only=True)
        elif target_type == "single" and account_id:
            acc = DB.get_account(account_id)
            accounts = [acc] if acc else []
        else:
            return "Invalid target"

        if not accounts:
            return "No active accounts"

        task_id = f"join_{asyncio.get_event_loop().time():.0f}"
        db_task_id = DB.add_task("join", f"Join {len(links)} links with {len(accounts)} accounts")

        async def _do_join():
            success = 0
            total = 0
            for acc in accounts:
                for link in links:
                    ok = await telethon_mgr.join_group(acc["id"], link)
                    if ok:
                        success += 1
                    total += 1
                    await asyncio.sleep(delay)
                await asyncio.sleep(5)
            DB.finish_task(db_task_id, "done")
            logger.info(f"Join complete: {success}/{total}")

        await pool.submit(task_id, _do_join(), description=f"Join {len(links)} links")
        return f"Join started: {len(links)} link(s) with {len(accounts)} account(s)"

    async def join_folder(self, folder_id: int, target_type: str = "all",
                          account_id: int = None) -> str:
        folder = DB.get_folder(folder_id)
        if not folder:
            return "Folder not found"

        links_rows = DB.get_folder_links(folder_id)
        links = [r["link"] for r in links_rows]
        if not links:
            return "Folder is empty"

        return await self.join(links, target_type, account_id)


join_service = JoinService()
