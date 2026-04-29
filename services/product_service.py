# services/product_service.py
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from database.db import get_connection

logger = logging.getLogger(__name__)


# ── Products ──────────────────────────────────────────────────────────────────

async def get_active_products() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT * FROM products
            WHERE is_active = 1
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY id
            """
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_product_by_id(product_id: int) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_products() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM products ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_product(
    name: str,
    description: str,
    price: float,
    image_file_id: str = None,
    validity_months: int = 0,
) -> int:
    expires_at = None
    if validity_months > 0:
        expires_at = (datetime.utcnow() + relativedelta(months=validity_months)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    async with get_connection() as db:
        cursor = await db.execute(
            """
            INSERT INTO products (name, description, price, image_file_id, validity_hours, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, price, image_file_id, validity_months, expires_at),
        )
        await db.commit()
        return cursor.lastrowid


async def update_product(product_id: int, **fields) -> bool:
    allowed = {"name", "description", "price", "image_file_id", "validity_hours", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [product_id]
    async with get_connection() as db:
        await db.execute(
            f"UPDATE products SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
    return True


async def delete_product(product_id: int) -> bool:
    async with get_connection() as db:
        await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await db.commit()
    return True


async def toggle_product(product_id: int) -> bool:
    async with get_connection() as db:
        await db.execute(
            "UPDATE products SET is_active = NOT is_active WHERE id = ?", (product_id,)
        )
        await db.commit()
    return True


# ── Plans ─────────────────────────────────────────────────────────────────────

async def get_plans_by_product(product_id: int) -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT * FROM plans
            WHERE product_id = ? AND is_active = 1
            ORDER BY price ASC
            """,
            (product_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_plan_by_id(plan_id: int) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM plans WHERE id = ?", (plan_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_plan(
    product_id: int,
    name: str,
    price: float,
    validity_hours: int = 0,
) -> int:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            INSERT INTO plans (product_id, name, price, validity_hours)
            VALUES (?, ?, ?, ?)
            """,
            (product_id, name, price, validity_hours),
        )
        await db.commit()
        return cursor.lastrowid


async def update_plan(plan_id: int, **fields) -> bool:
    allowed = {"name", "price", "validity_hours", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [plan_id]
    async with get_connection() as db:
        await db.execute(
            f"UPDATE plans SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
    return True


async def delete_plan(plan_id: int) -> bool:
    async with get_connection() as db:
        await db.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        await db.commit()
    return True