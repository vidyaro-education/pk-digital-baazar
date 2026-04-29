# services/user_service.py
import logging
from database.db import get_connection

logger = logging.getLogger(__name__)


async def get_or_create_user(telegram_id: int, name: str = None, username: str = None) -> dict:
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name     = excluded.name,
                username = excluded.username
            """,
            (telegram_id, name, username),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else {}


async def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def ban_user(telegram_id: int):
    async with get_connection() as db:
        await db.execute(
            "UPDATE users SET is_banned = 1 WHERE telegram_id = ?", (telegram_id,)
        )
        await db.commit()


async def unban_user(telegram_id: int):
    async with get_connection() as db:
        await db.execute(
            "UPDATE users SET is_banned = 0 WHERE telegram_id = ?", (telegram_id,)
        )
        await db.commit()


# ── Admin helpers ────────────────────────────────────────────────────────────

async def is_admin(telegram_id: int) -> bool:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)
        )
        return await cursor.fetchone() is not None


async def add_admin(telegram_id: int, added_by: int) -> bool:
    try:
        async with get_connection() as db:
            await db.execute(
                "INSERT OR IGNORE INTO admins (telegram_id, added_by) VALUES (?, ?)",
                (telegram_id, added_by),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error("add_admin error: %s", e)
        return False


async def remove_admin(telegram_id: int) -> bool:
    try:
        async with get_connection() as db:
            await db.execute(
                "DELETE FROM admins WHERE telegram_id = ?", (telegram_id,)
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error("remove_admin error: %s", e)
        return False


async def get_all_admins() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM admins ORDER BY created_at")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]