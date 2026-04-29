# handlers/common.py
import functools
import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ContextTypes
from services.user_service import is_admin, get_or_create_user

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 2
_last_action: dict[int, float] = {}

# ── Required channels ─────────────────────────────────────────────────────────
# Add as many as you need.
# Use the public username (e.g. "@mychannel") OR the numeric chat_id (e.g. -1001234567890).
# invite_link is shown to the user as a button; use a public link or an invite link.
REQUIRED_CHANNELS: list[dict] = [
    {
        "chat_id":    "-1003830790863",          # change to your channel
        "name":       "PK Premium Bazar",
        "invite_link": "https://t.me/pk_premium_bazar",
    },
    # Add more channels here, e.g.:
    # {
    #     "chat_id":    "@another_channel",
    #     "name":       "Another Channel",
    #     "invite_link": "https://t.me/another_channel",
    # },
]


async def check_membership(bot, user_id: int) -> list[dict]:
    """
    Returns list of channels the user has NOT joined.
    Empty list means the user is in all required channels.
    """
    not_joined = []
    for ch in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status in (
                ChatMember.LEFT,
                ChatMember.BANNED,
            ):
                not_joined.append(ch)
        except Exception as e:
            logger.warning("Could not check membership for %s: %s", ch["chat_id"], e)
            not_joined.append(ch)   # assume not joined if check fails
    return not_joined


async def send_join_prompt(update: Update, not_joined: list[dict]):
    """Send a message listing all channels the user must join."""
    text = (
        "👋 To use this bot, please join our channel"
        + ("s" if len(not_joined) > 1 else "")
        + " first:\n\n"
        + "\n".join(f"• {ch['name']}" for ch in not_joined)
        + "\n\nThen press ✅ *I've Joined* to continue."
    )
    buttons = [
        [InlineKeyboardButton(f"➡️ Join {ch['name']}", url=ch["invite_link"])]
        for ch in not_joined
    ]
    buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_membership")])
    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def require_membership(func):
    """
    Decorator – blocks any handler until the user has joined all REQUIRED_CHANNELS.
    Admins are exempt so they're never locked out.
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return await func(update, context, *args, **kwargs)

        # Admins bypass the check
        if await is_admin(user.id):
            return await func(update, context, *args, **kwargs)

        not_joined = await check_membership(context.bot, user.id)
        if not_joined:
            await send_join_prompt(update, not_joined)
            return

        return await func(update, context, *args, **kwargs)
    return wrapper


# ── "I've Joined" callback ────────────────────────────────────────────────────

async def check_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when user taps ✅ I've Joined — re-checks and lets them in."""
    query = update.callback_query
    await query.answer()

    not_joined = await check_membership(context.bot, update.effective_user.id)
    if not_joined:
        names = ", ".join(ch["name"] for ch in not_joined)
        await query.message.reply_text(
            f"❌ You haven't joined: *{names}*\n\nPlease join and try again.",
            parse_mode="Markdown",
        )
        return

    await query.message.reply_text(
        "✅ *Thank you for joining!*\n\nUse /start to continue.",
        parse_mode="Markdown",
    )


# ── Existing decorators (unchanged) ──────────────────────────────────────────

def admin_only(func):
    """Decorator – only lets admins through."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = update.effective_user.id
        if not await is_admin(uid):
            await update.effective_message.reply_text("⛔ Admin access required.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def register_user(func):
    """Decorator – upserts user, blocks banned accounts, enforces channel membership."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user:
            record = await get_or_create_user(
                user.id, user.full_name, user.username
            )
            if record.get("is_banned"):
                await update.effective_message.reply_text(
                    "🚫 You have been banned from this bot."
                )
                return

            # Channel membership check (admins are exempt inside check_membership)
            if not await is_admin(user.id):
                not_joined = await check_membership(context.bot, user.id)
                if not_joined:
                    await send_join_prompt(update, not_joined)
                    return

        return await func(update, context, *args, **kwargs)
    return wrapper


def rate_limit(func):
    """Decorator – simple per-user rate limiter."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = update.effective_user.id
        now = time.monotonic()
        if now - _last_action.get(uid, 0) < RATE_LIMIT_SECONDS:
            await update.effective_message.reply_text(
                "⏳ Please slow down a bit!"
            )
            return
        _last_action[uid] = now
        return await func(update, context, *args, **kwargs)
    return wrapper


def paginate(items: list, page: int, per_page: int = 5):
    """Return (page_items, total_pages)."""
    total = max(1, (len(items) + per_page - 1) // per_page)
    page  = max(0, min(page, total - 1))
    start = page * per_page
    return items[start : start + per_page], total


STATUS_EMOJI = {
    "PENDING":                       "🕐",
    "WAITING_PAYMENT_CONFIRMATION":  "💳",
    "APPROVED":                      "✅",
    "REJECTED":                      "❌",
}