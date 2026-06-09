import asyncio
import logging
import os
from typing import Dict, Optional, List
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, UserNotParticipantError,
    ChatAdminRequiredError, ChannelPrivateError
)
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantsRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, ChannelParticipantsSearch
from src.database import DB

logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")


class TelethonManager:
    def __init__(self):
        self._clients: Dict[int, TelegramClient] = {}
        self._lock = asyncio.Lock()
        self._pending_auth: Dict[str, dict] = {}

    async def get_client(self, account_id: int) -> Optional[TelegramClient]:
        async with self._lock:
            if account_id in self._clients:
                client = self._clients[account_id]
                if client.is_connected():
                    return client
                try:
                    await client.connect()
                    return client
                except Exception:
                    del self._clients[account_id]

            account = DB.get_account(account_id)
            if not account or not account.get("session_string"):
                return None

            try:
                client = TelegramClient(
                    StringSession(account["session_string"]),
                    API_ID, API_HASH,
                    connection_retries=3,
                    retry_delay=5,
                    request_retries=3,
                    flood_sleep_threshold=60
                )
                await client.connect()
                if await client.is_user_authorized():
                    self._clients[account_id] = client
                    logger.info(f"Client connected for account {account_id}")
                    return client
                else:
                    await client.disconnect()
                    return None
            except Exception as e:
                logger.error(f"Failed to connect account {account_id}: {e}")
                DB.log_error(f"account_{account_id}", type(e).__name__, str(e))
                return None

    async def disconnect_account(self, account_id: int):
        async with self._lock:
            client = self._clients.pop(account_id, None)
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    async def disconnect_all(self):
        async with self._lock:
            for client in self._clients.values():
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self._clients.clear()

    async def start_login(self, phone: str) -> str:
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            sent = await client.send_code_request(phone)
            self._pending_auth[phone] = {
                "client": client,
                "phone_code_hash": sent.phone_code_hash
            }
            return "code_sent"
        except Exception as e:
            logger.error(f"Login start failed for {phone}: {e}")
            raise

    async def complete_login(self, phone: str, code: str, password: str = None) -> Optional[str]:
        pending = self._pending_auth.get(phone)
        if not pending:
            raise ValueError("No pending login for this phone")

        client: TelegramClient = pending["client"]
        phone_code_hash = pending["phone_code_hash"]

        try:
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                if password:
                    await client.sign_in(password=password)
                else:
                    return "2fa_required"

            me = await client.get_me()
            session_string = client.session.save()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip() or phone

            account_id = DB.add_account(phone, name, session_string)
            async with self._lock:
                self._clients[account_id] = client

            del self._pending_auth[phone]
            logger.info(f"Account logged in: {phone} → ID {account_id}")
            return "success"
        except Exception as e:
            logger.error(f"Login completion failed for {phone}: {e}")
            raise

    async def join_group(self, account_id: int, link: str) -> bool:
        client = await self.get_client(account_id)
        if not client:
            return False

        try:
            if "t.me/+" in link or "t.me/joinchat" in link:
                hash_part = link.split("/+")[-1] if "/+" in link else link.split("joinchat/")[-1]
                await client(ImportChatInviteRequest(hash_part))
            else:
                username = link.split("t.me/")[-1].strip("/")
                entity = await client.get_entity(username)
                await client(JoinChannelRequest(entity))

            DB.add_join_log(account_id, link, "success")
            return True
        except FloodWaitError as e:
            logger.warning(f"FloodWait joining {link}: {e.seconds}s")
            DB.add_join_log(account_id, link, "flood_wait", str(e))
            return False
        except Exception as e:
            logger.error(f"Failed to join {link} with account {account_id}: {e}")
            DB.add_join_log(account_id, link, "failed", str(e))
            return False

    async def send_message(self, account_id: int, group_id: str, message: str) -> bool:
        client = await self.get_client(account_id)
        if not client:
            return False

        try:
            try:
                entity = await client.get_entity(int(group_id))
            except Exception:
                entity = await client.get_entity(group_id)

            await client.send_message(entity, message)
            return True
        except FloodWaitError as e:
            logger.warning(f"FloodWait sending to {group_id}: {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 60))
            return False
        except (ChatAdminRequiredError, ChannelPrivateError) as e:
            logger.warning(f"Cannot send to {group_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send message to {group_id} with account {account_id}: {e}")
            return False

    async def fetch_groups(self, account_id: int) -> List[Dict]:
        client = await self.get_client(account_id)
        if not client:
            return []

        groups = []
        try:
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    entity = dialog.entity
                    groups.append({
                        "id": str(dialog.id),
                        "title": dialog.title,
                        "username": getattr(entity, "username", None),
                        "invite_link": None,
                        "member_count": getattr(entity, "participants_count", 0)
                    })
            DB.save_groups(account_id, groups)
            logger.info(f"Fetched {len(groups)} groups for account {account_id}")
        except Exception as e:
            logger.error(f"Failed to fetch groups for account {account_id}: {e}")
            DB.log_error(f"account_{account_id}", type(e).__name__, str(e))

        return groups

    async def update_session(self, account_id: int) -> bool:
        client = await self.get_client(account_id)
        if not client:
            return False
        try:
            session_string = client.session.save()
            DB.update_account_session(account_id, session_string)
            return True
        except Exception as e:
            logger.error(f"Failed to update session for {account_id}: {e}")
            return False


# Global instance
telethon_mgr = TelethonManager()
