import sqlite3
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "bot_data.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                name TEXT,
                session_string TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                error_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS ad_variants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                used_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS folder_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER NOT NULL,
                link TEXT NOT NULL,
                link_type TEXT DEFAULT 'group',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                group_id TEXT,
                title TEXT,
                username TEXT,
                invite_link TEXT,
                member_count INTEGER,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS publish_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                ad_id INTEGER,
                variant_id INTEGER,
                group_id TEXT,
                group_title TEXT,
                status TEXT NOT NULL,
                error_msg TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
                FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS join_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                link TEXT NOT NULL,
                status TEXT NOT NULL,
                error_msg TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ad_id INTEGER,
                target_type TEXT DEFAULT 'all',
                account_id INTEGER,
                interval_hours REAL NOT NULL,
                next_run TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                run_count INTEGER DEFAULT 0,
                FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                error_msg TEXT
            );

            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                error_type TEXT,
                message TEXT,
                occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        logger.info("Database initialized successfully")
    finally:
        conn.close()


class DB:
    _lock = asyncio.Lock()

    @staticmethod
    def run(func, *args):
        conn = get_connection()
        try:
            return func(conn, *args)
        finally:
            conn.close()

    # ── Accounts ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_accounts(active_only=False) -> List[Dict]:
        def _q(conn):
            if active_only:
                rows = conn.execute("SELECT * FROM accounts WHERE is_active=1 AND status='active'").fetchall()
            else:
                rows = conn.execute("SELECT * FROM accounts").fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_account(account_id: int) -> Optional[Dict]:
        def _q(conn):
            row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            return dict(row) if row else None
        return DB.run(_q)

    @staticmethod
    def add_account(phone: str, name: str, session_string: str) -> int:
        def _q(conn):
            cur = conn.execute(
                "INSERT OR REPLACE INTO accounts (phone, name, session_string) VALUES (?,?,?)",
                (phone, name, session_string)
            )
            conn.commit()
            return cur.lastrowid
        return DB.run(_q)

    @staticmethod
    def update_account_status(account_id: int, is_active: int, status: str = None):
        def _q(conn):
            if status:
                conn.execute("UPDATE accounts SET is_active=?, status=? WHERE id=?", (is_active, status, account_id))
            else:
                conn.execute("UPDATE accounts SET is_active=? WHERE id=?", (is_active, account_id))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def update_account_session(account_id: int, session_string: str):
        def _q(conn):
            conn.execute("UPDATE accounts SET session_string=?, last_used=CURRENT_TIMESTAMP WHERE id=?",
                         (session_string, account_id))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def delete_account(account_id: int):
        def _q(conn):
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_account_stats() -> Dict:
        def _q(conn):
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM accounts WHERE is_active=1").fetchone()[0]
            return {"total": total, "active": active, "inactive": total - active}
        return DB.run(_q)

    # ── Ads ───────────────────────────────────────────────────────────────────

    @staticmethod
    def get_ads(active_only=False) -> List[Dict]:
        def _q(conn):
            if active_only:
                rows = conn.execute("SELECT * FROM ads WHERE is_active=1").fetchall()
            else:
                rows = conn.execute("SELECT * FROM ads").fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_ad(ad_id: int) -> Optional[Dict]:
        def _q(conn):
            row = conn.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
            return dict(row) if row else None
        return DB.run(_q)

    @staticmethod
    def add_ad(title: str, content: str) -> int:
        def _q(conn):
            cur = conn.execute("INSERT INTO ads (title, content) VALUES (?,?)", (title, content))
            conn.commit()
            return cur.lastrowid
        return DB.run(_q)

    @staticmethod
    def update_ad(ad_id: int, title: str, content: str):
        def _q(conn):
            conn.execute("UPDATE ads SET title=?, content=? WHERE id=?", (title, content, ad_id))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def delete_ad(ad_id: int):
        def _q(conn):
            conn.execute("DELETE FROM ads WHERE id=?", (ad_id,))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def add_ad_variants(ad_id: int, variants: List[str]):
        def _q(conn):
            conn.executemany(
                "INSERT INTO ad_variants (ad_id, content) VALUES (?,?)",
                [(ad_id, v) for v in variants]
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_ad_variants(ad_id: int) -> List[Dict]:
        def _q(conn):
            rows = conn.execute("SELECT * FROM ad_variants WHERE ad_id=?", (ad_id,)).fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_next_variant(ad_id: int) -> Optional[Dict]:
        def _q(conn):
            row = conn.execute(
                "SELECT * FROM ad_variants WHERE ad_id=? ORDER BY used_count ASC, id ASC LIMIT 1",
                (ad_id,)
            ).fetchone()
            if row:
                conn.execute("UPDATE ad_variants SET used_count=used_count+1 WHERE id=?", (row["id"],))
                conn.commit()
            return dict(row) if row else None
        return DB.run(_q)

    # ── Folders ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_folders() -> List[Dict]:
        def _q(conn):
            rows = conn.execute("SELECT * FROM folders").fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_folder(folder_id: int) -> Optional[Dict]:
        def _q(conn):
            row = conn.execute("SELECT * FROM folders WHERE id=?", (folder_id,)).fetchone()
            return dict(row) if row else None
        return DB.run(_q)

    @staticmethod
    def add_folder(name: str, description: str = "") -> int:
        def _q(conn):
            cur = conn.execute("INSERT INTO folders (name, description) VALUES (?,?)", (name, description))
            conn.commit()
            return cur.lastrowid
        return DB.run(_q)

    @staticmethod
    def delete_folder(folder_id: int):
        def _q(conn):
            conn.execute("DELETE FROM folders WHERE id=?", (folder_id,))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def add_folder_links(folder_id: int, links: List[str]):
        def _q(conn):
            conn.executemany(
                "INSERT OR IGNORE INTO folder_links (folder_id, link) VALUES (?,?)",
                [(folder_id, l) for l in links]
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_folder_links(folder_id: int) -> List[Dict]:
        def _q(conn):
            rows = conn.execute("SELECT * FROM folder_links WHERE folder_id=?", (folder_id,)).fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    # ── Groups ────────────────────────────────────────────────────────────────

    @staticmethod
    def save_groups(account_id: int, groups: List[Dict]):
        def _q(conn):
            conn.execute("DELETE FROM groups WHERE account_id=?", (account_id,))
            conn.executemany(
                "INSERT INTO groups (account_id, group_id, title, username, invite_link, member_count) VALUES (?,?,?,?,?,?)",
                [(account_id, g.get("id"), g.get("title"), g.get("username"), g.get("invite_link"), g.get("member_count", 0)) for g in groups]
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_groups(account_id: int = None) -> List[Dict]:
        def _q(conn):
            if account_id:
                rows = conn.execute("SELECT * FROM groups WHERE account_id=?", (account_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM groups").fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    # ── Publish Logs ──────────────────────────────────────────────────────────

    @staticmethod
    def add_publish_log(account_id, ad_id, variant_id, group_id, group_title, status, error_msg=None):
        def _q(conn):
            conn.execute(
                "INSERT INTO publish_logs (account_id, ad_id, variant_id, group_id, group_title, status, error_msg) VALUES (?,?,?,?,?,?,?)",
                (account_id, ad_id, variant_id, group_id, group_title, status, error_msg)
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_publish_logs(limit=50) -> List[Dict]:
        def _q(conn):
            rows = conn.execute(
                "SELECT pl.*, a.phone, ads.title as ad_title FROM publish_logs pl "
                "LEFT JOIN accounts a ON pl.account_id=a.id "
                "LEFT JOIN ads ON pl.ad_id=ads.id "
                "ORDER BY pl.published_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_publish_stats() -> Dict:
        def _q(conn):
            total = conn.execute("SELECT COUNT(*) FROM publish_logs").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM publish_logs WHERE status='success'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM publish_logs WHERE status='failed'").fetchone()[0]
            return {"total": total, "success": success, "failed": failed}
        return DB.run(_q)

    # ── Join Logs ─────────────────────────────────────────────────────────────

    @staticmethod
    def add_join_log(account_id, link, status, error_msg=None):
        def _q(conn):
            conn.execute(
                "INSERT INTO join_logs (account_id, link, status, error_msg) VALUES (?,?,?,?)",
                (account_id, link, status, error_msg)
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_join_logs(limit=50) -> List[Dict]:
        def _q(conn):
            rows = conn.execute(
                "SELECT jl.*, a.phone FROM join_logs jl "
                "LEFT JOIN accounts a ON jl.account_id=a.id "
                "ORDER BY jl.joined_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_join_stats() -> Dict:
        def _q(conn):
            total = conn.execute("SELECT COUNT(*) FROM join_logs").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM join_logs WHERE status='success'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM join_logs WHERE status='failed'").fetchone()[0]
            return {"total": total, "success": success, "failed": failed}
        return DB.run(_q)

    # ── Schedules ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_schedules(active_only=False) -> List[Dict]:
        def _q(conn):
            if active_only:
                rows = conn.execute("SELECT * FROM schedules WHERE is_active=1").fetchall()
            else:
                rows = conn.execute("SELECT * FROM schedules").fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def add_schedule(name, ad_id, target_type, account_id, interval_hours) -> int:
        def _q(conn):
            cur = conn.execute(
                "INSERT INTO schedules (name, ad_id, target_type, account_id, interval_hours, next_run) "
                "VALUES (?,?,?,?,?, datetime('now'))",
                (name, ad_id, target_type, account_id, interval_hours)
            )
            conn.commit()
            return cur.lastrowid
        return DB.run(_q)

    @staticmethod
    def update_schedule_run(schedule_id: int):
        def _q(conn):
            conn.execute(
                "UPDATE schedules SET run_count=run_count+1, "
                "next_run=datetime('now', '+' || CAST(interval_hours AS TEXT) || ' hours') "
                "WHERE id=?", (schedule_id,)
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def toggle_schedule(schedule_id: int, is_active: int):
        def _q(conn):
            conn.execute("UPDATE schedules SET is_active=? WHERE id=?", (is_active, schedule_id))
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def delete_schedule(schedule_id: int):
        def _q(conn):
            conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
            conn.commit()
        return DB.run(_q)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @staticmethod
    def add_task(task_type: str, description: str) -> int:
        def _q(conn):
            cur = conn.execute(
                "INSERT INTO tasks (task_type, description, status) VALUES (?,?,'running')",
                (task_type, description)
            )
            conn.commit()
            return cur.lastrowid
        return DB.run(_q)

    @staticmethod
    def finish_task(task_id: int, status: str = "done", error: str = None):
        def _q(conn):
            conn.execute(
                "UPDATE tasks SET status=?, finished_at=CURRENT_TIMESTAMP, error_msg=? WHERE id=?",
                (status, error, task_id)
            )
            conn.commit()
        return DB.run(_q)

    @staticmethod
    def get_running_tasks() -> List[Dict]:
        def _q(conn):
            rows = conn.execute("SELECT * FROM tasks WHERE status='running' ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def get_all_tasks(limit=30) -> List[Dict]:
        def _q(conn):
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        return DB.run(_q)

    @staticmethod
    def cancel_task(task_id: int):
        def _q(conn):
            conn.execute("UPDATE tasks SET status='cancelled', finished_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
            conn.commit()
        return DB.run(_q)

    # ── Errors ────────────────────────────────────────────────────────────────

    @staticmethod
    def log_error(source: str, error_type: str, message: str):
        def _q(conn):
            conn.execute(
                "INSERT INTO errors (source, error_type, message) VALUES (?,?,?)",
                (source, error_type, message)
            )
            conn.commit()
        return DB.run(_q)
