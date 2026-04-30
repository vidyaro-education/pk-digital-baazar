"""
database/db.py
Core database module: connection management, table creation, migrations.
"""

import aiosqlite
import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "shop.db")


@asynccontextmanager
async def get_connection():
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")

        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                name        TEXT    NOT NULL DEFAULT '',
                username    TEXT,
                is_banned   INTEGER NOT NULL DEFAULT 0,
                is_admin    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS admins (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                added_by    INTEGER,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS products (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                description     TEXT    DEFAULT '',
                price           REAL    NOT NULL DEFAULT 0,
                image_file_id   TEXT,
                validity_hours  INTEGER NOT NULL DEFAULT 0,
                is_active       INTEGER NOT NULL DEFAULT 1,
                expires_at      TEXT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS plans (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id     INTEGER NOT NULL,
                name           TEXT    NOT NULL,
                price          REAL    NOT NULL,
                validity_hours INTEGER NOT NULL DEFAULT 0,
                is_active      INTEGER NOT NULL DEFAULT 1,
                created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS orders (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL,
                product_id          INTEGER NOT NULL,
                plan_id             INTEGER,
                price               REAL    NOT NULL DEFAULT 0,
                status              TEXT    NOT NULL DEFAULT 'PENDING',
                screenshot_file_id  TEXT,
                admin_note          TEXT,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(user_id)    REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id),
                FOREIGN KEY(plan_id)    REFERENCES plans(id)
            );
        """)
        await conn.commit()

        await _migrate(conn)
        logger.info("✅ Database ready at %s", DATABASE_PATH)


async def _migrate(conn: aiosqlite.Connection):
    migrations = {
        "users": [
            ("is_banned",  "INTEGER NOT NULL DEFAULT 0"),
            ("is_admin",   "INTEGER NOT NULL DEFAULT 0"),
            ("created_at", "TEXT NOT NULL DEFAULT (datetime('now'))"),
            ("last_seen",  "TEXT NOT NULL DEFAULT (datetime('now'))"),
        ],
        "admins": [
            ("added_by",   "INTEGER"),
            ("created_at", "TEXT NOT NULL DEFAULT (datetime('now'))"),
        ],
        "products": [
            ("image_file_id",  "TEXT"),
            ("validity_hours", "INTEGER NOT NULL DEFAULT 0"),
            ("expires_at",     "TEXT"),
            ("created_at",     "TEXT NOT NULL DEFAULT (datetime('now'))"),
        ],
        "orders": [
            ("plan_id",            "INTEGER"),
            ("price",              "REAL NOT NULL DEFAULT 0"),
            ("screenshot_file_id", "TEXT"),
            ("admin_note",         "TEXT"),
            ("updated_at",         "TEXT NOT NULL DEFAULT (datetime('now'))"),
        ],
    }

    for table, columns in migrations.items():
        for col_name, col_def in columns:
            try:
                await conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                )
                await conn.commit()
                logger.info("Migration: added column %s.%s", table, col_name)
            except Exception:
                pass

    for old_col, new_col, table in [
        ("image_url", "image_file_id", "products"),
        ("banned",    "is_banned",     "users"),
    ]:
        try:
            await conn.execute(
                f"UPDATE {table} SET {new_col} = {old_col} "
                f"WHERE {new_col} IS NULL OR {new_col} = 0"
            )
            await conn.commit()
        except Exception:
            pass