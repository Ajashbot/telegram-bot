import asyncio
import logging
from typing import Optional, List
from src.database import DB
from src.telethon_manager import telethon_mgr
from src.worker_pool import pool

logger = logging.getLogger(__name__)


class PublishService:
    def __init__(self):
        self._active_publish_tasks = set()

    async def publish(self, ad_id: int, target_type: str = "all", account_id: int = None,
                      group_ids: List[str] = None) -> str:
        ad = DB.get_ad(ad_id)
        if not ad:
            return "Ad not found"

        if target_type == "all":
            accounts = DB.get_accounts(active_only=True)
        elif target_type == "single" and account_id:
            acc = DB.get_account(account_id)
            accounts = [acc] if acc else []
        else:
            return "Invalid target"

        if not accounts:
            return "No active accounts found"

        task_id = f"publish_{ad_id}_{asyncio.get_event_loop().time():.0f}"
        db_task_id = DB.add_task("publish", f"Publish ad '{ad['title']}' to {len(accounts)} accounts")

        async def _do_publish():
            total = 0
            success = 0
            for acc in accounts:
                if not group_ids:
                    groups = DB.get_groups(acc["id"])
                    g_ids = [(str(g["group_id"]), g.get("title", "Unknown")) for g in groups]
                else:
                    g_ids = [(gid, gid) for gid in group_ids]

                variant = DB.get_next_variant(ad_id)
                message = variant["content"] if variant else ad["content"]

                for gid, gtitle in g_ids:
                    try:
                        sent = await telethon_mgr.send_message(acc["id"], gid, message)
                        status = "success" if sent else "failed"
                        DB.add_publish_log(acc["id"], ad_id, variant["id"] if variant else None,
                                           gid, gtitle, status)
                        if sent:
                            success += 1
                        total += 1
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Publish error to {gid}: {e}")
                        DB.add_publish_log(acc["id"], ad_id, None, gid, gtitle, "failed", str(e))
                        total += 1

                await asyncio.sleep(5)

            DB.finish_task(db_task_id, "done")
            logger.info(f"Publish complete: {success}/{total} successful")

        await pool.submit(task_id, _do_publish(), description=f"Publish ad {ad_id}")
        return f"Publishing started: ad '{ad['title']}' to {len(accounts)} account(s)"

    async def publish_scheduled(self, ad_id: int, target_type: str, account_id: int = None):
        await self.publish(ad_id, target_type, account_id)


publish_service = PublishService()
