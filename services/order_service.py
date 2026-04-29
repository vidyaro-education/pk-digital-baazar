# services/order_service.py
import logging
from database.db import get_connection

logger = logging.getLogger(__name__)

STATUS_PENDING  = "PENDING"
STATUS_WAITING  = "WAITING_PAYMENT_CONFIRMATION"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"


async def create_order(
    user_id: int,
    product_id: int,
    price: float,
    plan_id: int = None,
) -> int | None:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id FROM orders
            WHERE user_id = ? AND product_id = ?
              AND (plan_id = ? OR (plan_id IS NULL AND ? IS NULL))
              AND status IN (?, ?)
            """,
            (user_id, product_id, plan_id, plan_id, STATUS_PENDING, STATUS_WAITING),
        )
        if await cursor.fetchone():
            return None

        cursor = await db.execute(
            """
            INSERT INTO orders (user_id, product_id, plan_id, price)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, product_id, plan_id, price),
        )
        await db.commit()
        return cursor.lastrowid


async def get_order_by_id(order_id: int) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT o.*, u.telegram_id, u.name as user_name, u.username,
                   p.name as product_name, p.validity_hours,
                   pl.name as plan_name
            FROM orders o
            JOIN users    u  ON u.id  = o.user_id
            JOIN products p  ON p.id  = o.product_id
            LEFT JOIN plans pl ON pl.id = o.plan_id
            WHERE o.id = ?
            """,
            (order_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_user_orders(user_id: int) -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT o.id, o.status, o.price, o.screenshot_file_id,
                   o.created_at, o.updated_at, o.admin_note,
                   p.name as product_name, p.validity_hours,
                   pl.name as plan_name
            FROM orders o
            JOIN products  p  ON p.id  = o.product_id
            LEFT JOIN plans pl ON pl.id = o.plan_id
            WHERE o.user_id = ?
              AND o.status IN (?, ?)
            ORDER BY o.created_at DESC
            """,
            (user_id, STATUS_WAITING, STATUS_APPROVED),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_orders_by_status(status: str) -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT o.*, u.telegram_id, u.name as user_name,
                   p.name as product_name, p.validity_hours,
                   pl.name as plan_name
            FROM orders o
            JOIN users    u  ON u.id  = o.user_id
            JOIN products p  ON p.id  = o.product_id
            LEFT JOIN plans pl ON pl.id = o.plan_id
            WHERE o.status = ?
            ORDER BY o.created_at DESC
            """,
            (status,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_orders() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT o.*, u.telegram_id, u.name as user_name,
                   p.name as product_name, p.validity_hours,
                   pl.name as plan_name
            FROM orders o
            JOIN users    u  ON u.id  = o.user_id
            JOIN products p  ON p.id  = o.product_id
            LEFT JOIN plans pl ON pl.id = o.plan_id
            ORDER BY o.created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def attach_screenshot(order_id: int, file_id: str) -> bool:
    async with get_connection() as db:
        await db.execute(
            """
            UPDATE orders
            SET screenshot_file_id = ?,
                status             = ?,
                updated_at         = datetime('now')
            WHERE id = ?
            """,
            (file_id, STATUS_WAITING, order_id),
        )
        await db.commit()
    return True


async def update_order_status(order_id: int, status: str, note: str = None) -> bool:
    async with get_connection() as db:
        await db.execute(
            """
            UPDATE orders
            SET status     = ?,
                admin_note = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, note, order_id),
        )
        await db.commit()
    return True


async def get_latest_pending_order(user_id: int, plan_id: int = None) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT o.*, p.name as product_name, p.validity_hours,
                   pl.name as plan_name
            FROM orders o
            JOIN products  p  ON p.id  = o.product_id
            LEFT JOIN plans pl ON pl.id = o.plan_id
            WHERE o.user_id = ? AND o.status = ?
              AND (o.plan_id = ? OR ? IS NULL)
            ORDER BY o.created_at DESC
            LIMIT 1
            """,
            (user_id, STATUS_PENDING, plan_id, plan_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_order_count_by_status() -> dict:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT status, COUNT(*) as count FROM orders GROUP BY status"
        )
        rows = await cursor.fetchall()
        return {r["status"]: r["count"] for r in rows}