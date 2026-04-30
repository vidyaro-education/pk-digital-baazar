# handlers/user_handlers.py
import logging
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile,
)
from telegram.ext import ContextTypes

from handlers.common import register_user, rate_limit, STATUS_EMOJI
from handlers.admin_handlers import validity_display
from services.product_service import (
    get_active_products,
    get_product_by_id,
    get_plans_by_product,
    get_plan_by_id,
)
from services.order_service import (
    create_order,
    get_user_orders,
    get_latest_pending_order,
    attach_screenshot,
    get_order_by_id,
)
from services.user_service import get_user_by_telegram_id, get_all_admins
from services.qr_service import generate_payment_qr

logger = logging.getLogger(__name__)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🛍️ Product List"), KeyboardButton("📦 My Orders")],
        [KeyboardButton("🆘 Support")],
    ],
    resize_keyboard=True,
)


# ── /start ────────────────────────────────────────────────────────────────────

@register_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Welcome to *PK Bazar*, {name}!\n\n"
        "Use the menu below to browse products, check orders, or get support.",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ── Product List ──────────────────────────────────────────────────────────────

@register_user
@rate_limit
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = await get_active_products()
    if not products:
        await _reply(update, "😔 No products available right now.")
        return

    buttons = []
    row = []
    for p in products:
        label = f"{p['name']} ₹{p['price']:.0f}"
        row.append(InlineKeyboardButton(label, callback_data=f"buy_{p['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("⚠️ HELP",   callback_data="help_btn"),
        InlineKeyboardButton("✨ Resell", callback_data="resell_btn"),
    ])

    await _reply(
        update,
        "🛍️ *Select a product below:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ── Product clicked → show plans or confirm ───────────────────────────────────

@register_user
async def product_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        product_id = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.message.reply_text("❌ Invalid product selection.")
        return

    product = await get_product_by_id(product_id)
    if not product or not product.get("is_active"):
        await query.message.reply_text("❌ This product is no longer available.")
        return

    plans = await get_plans_by_product(product_id)

    if plans:
        # Show plan grid
        buttons = []
        row = []
        for pl in plans:
            label = f"{pl['name']} - ₹{pl['price']:.0f}"
            row.append(InlineKeyboardButton(label, callback_data=f"plan_{pl['id']}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_list")])

        text = f"📋 *{product['name']}*\n"
        if product.get("description"):
            text += f"📝 {product['description']}\n"
        text += "\n🔽 *Select a plan:*"

        if product.get("image_file_id"):
            await query.message.reply_photo(
                photo=product["image_file_id"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        else:
            await query.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
    else:
        # No plans — go straight to confirm
        text = (
            f"🛍️ *{product['name']}*\n"
            f"📝 {product['description'] or 'No description'}\n"
            f"💰 ₹{product['price']:.2f}\n"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Confirm Buy", callback_data=f"confirm_buy_{product_id}_0")],
            [InlineKeyboardButton("🔙 Back to List", callback_data="back_to_list")],
        ])

        if product.get("image_file_id"):
            await query.message.reply_photo(
                photo=product["image_file_id"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await query.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=kb,
            )


# ── Plan selected → confirm screen ───────────────────────────────────────────

@register_user
async def plan_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        plan_id = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.message.reply_text("❌ Invalid plan selection.")
        return

    plan = await get_plan_by_id(plan_id)
    if not plan or not plan.get("is_active"):
        await query.message.reply_text("❌ This plan is no longer available.")
        return

    product = await get_product_by_id(plan["product_id"])
    if not product:
        await query.message.reply_text("❌ Product not found.")
        return

    text = (
        f"🛍️ *{product['name']}*\n"
        f"📋 Plan    : {plan['name']}\n"
        f"💰 Price   : ₹{plan['price']:.2f}\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Confirm Buy", callback_data=f"confirm_buy_{plan['product_id']}_{plan_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"buy_{plan['product_id']}")],
    ])

    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Confirm buy → generate QR ─────────────────────────────────────────────────

@register_user
async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        parts      = query.data.split("_")  # confirm_buy_{product_id}_{plan_id}
        product_id = int(parts[2])
        plan_id    = int(parts[3]) if parts[3] != "0" else None
    except (ValueError, IndexError):
        await query.message.reply_text("❌ Invalid selection.")
        return

    product = await get_product_by_id(product_id)
    if not product or not product.get("is_active"):
        await query.message.reply_text("❌ This product is no longer available.")
        return

    if plan_id:
        plan = await get_plan_by_id(plan_id)
        if not plan or not plan.get("is_active"):
            await query.message.reply_text("❌ This plan is no longer available.")
            return
        price      = plan["price"]
        plan_label = plan["name"]
    else:
        plan       = None
        price      = product["price"]
        plan_label = None

    user = await get_user_by_telegram_id(update.effective_user.id)
    if not user:
        await query.message.reply_text("❌ Could not find your account. Please /start again.")
        return

    order_id = await create_order(user["id"], product_id, price, plan_id)
    if order_id is None:
        existing = await get_latest_pending_order(user["id"], plan_id)
        if existing:
            order_id = existing["id"]
            price    = existing["price"]
        else:
            await query.message.reply_text("❌ Something went wrong. Please try again.")
            return

    try:
        qr_bytes = generate_payment_qr(price, order_id)
    except Exception as e:
        logger.error("QR generation failed for order %s: %s", order_id, e)
        await query.message.reply_text("❌ Failed to generate payment QR. Please try again.")
        return

    caption = (
        f"🧾 *Order #{order_id} Created!*\n\n"
        f"Product : {product['name']}\n"
    )
    if plan_label:
        caption += f"Plan    : {plan_label}\n"
    caption += (
        f"Amount  : ₹{price:.2f}\n\n"
        "📲 Scan the QR code to pay via UPI.\n"
        "📸 After payment, send your *payment screenshot* here."
    )

    await query.message.reply_photo(
        photo=InputFile(BytesIO(qr_bytes), filename="payment_qr.png"),
        caption=caption,
        parse_mode="Markdown",
    )
    context.user_data["awaiting_screenshot_order"] = order_id


# ── Back to product list ───────────────────────────────────────────────────────

async def back_to_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await list_products(update, context)


# ── Help button ───────────────────────────────────────────────────────────────

async def help_btn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "💬 *Help*\n\nFor any issues, contact our admin @Padhai\\_karo\\_bot.",
        parse_mode="Markdown",
    )


# ── Resell button ─────────────────────────────────────────────────────────────

async def resell_btn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "✨ *Resell*\n\nInterested in reselling? Contact @Padhai\\_karo\\_bot for details.",
        parse_mode="Markdown",
    )


# ── Screenshot handler ────────────────────────────────────────────────────────

@register_user
async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text(
            "❌ Please send a valid payment *screenshot* (photo).",
            parse_mode="Markdown",
        )
        return

    user = await get_user_by_telegram_id(update.effective_user.id)
    if not user:
        await update.message.reply_text("❌ Could not find your account. Please /start again.")
        return

    order_id = context.user_data.get("awaiting_screenshot_order")

    if order_id:
        order = await get_order_by_id(order_id)
        if not order or order.get("status") != "PENDING":
            order_id = None
            context.user_data.pop("awaiting_screenshot_order", None)

    if not order_id:
        order = await get_latest_pending_order(user["id"])
        if not order:
            await update.message.reply_text(
                "⚠️ No pending order found. Please buy a product first."
            )
            return
        order_id = order["id"]

    file_id = update.message.photo[-1].file_id

    try:
        await attach_screenshot(order_id, file_id)
    except Exception as e:
        logger.error("Failed to attach screenshot for order %s: %s", order_id, e)
        await update.message.reply_text("❌ Failed to save screenshot. Please try again.")
        return

    context.user_data.pop("awaiting_screenshot_order", None)

    await update.message.reply_text(
        f"✅ Screenshot received for *Order #{order_id}*!\n"
        "Our admin will verify and approve shortly. 🕐",
        parse_mode="Markdown",
    )

    order_detail = await get_order_by_id(order_id)
    if not order_detail:
        return

    notif = (
        f"📸 *New Payment Screenshot*\n\n"
        f"Order  : #{order_id}\n"
        f"User   : {order_detail['user_name']} (ID: {order_detail['telegram_id']})\n"
        f"Product: {order_detail['product_name']}\n"
    )
    if order_detail.get("plan_name"):
        notif += f"Plan   : {order_detail['plan_name']}\n"
    notif += f"Amount : ₹{order_detail['price']:.2f}"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{order_id}"),
        ]
    ])
    admins = await get_all_admins()
    for admin in admins:
        try:
            await context.bot.send_photo(
                chat_id=admin["telegram_id"],
                photo=file_id,
                caption=notif,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning("Could not notify admin %s: %s", admin["telegram_id"], e)


# ── My Orders ─────────────────────────────────────────────────────────────────

@register_user
async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_telegram_id(update.effective_user.id)
    if not user:
        await update.message.reply_text("❌ Could not find your account. Please /start again.")
        return

    orders = await get_user_orders(user["id"])

    if not orders:
        await update.message.reply_text(
            "📦 No orders to show yet.\n\n"
            "Once you make a payment and send your screenshot, "
            "your order will appear here. 🕐",
        )
        return

    text = "📦 *Your Orders:*\n\n"
    for o in orders[:10]:
        if o["status"] == "WAITING_PAYMENT_CONFIRMATION":
            status_label = "⏳ Under Review"
        elif o["status"] == "APPROVED":
            status_label = "✅ Approved"
        else:
            status_label = o["status"]

        text += f"🧾 *Order #{o['id']}*\n"
        text += f"   Product : {o['product_name']}\n"
        if o.get("plan_name"):
            text += f"   Plan    : {o['plan_name']}\n"
        text += f"   Amount  : ₹{o['price']:.2f}\n"
        text += f"   Status  : {status_label}\n"
        text += f"   Date    : {o['created_at'][:10]}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ── Support ───────────────────────────────────────────────────────────────────

@register_user
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 *Support*\n\n"
        "For any help, contact our admin @Padhai\\_karo\\_bot.",
        parse_mode="Markdown",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _reply(update: Update, text: str, **kwargs):
    if update.message:
        await update.message.reply_text(text, **kwargs)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    else:
        logger.warning("_reply: no message or callback_query on update %s", update.update_id)


# ── Forward User Replies ───────────────────────────────────────────────────────

@register_user
async def forward_to_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    if not text:
        return
        
    admins = await get_all_admins()
    msg = f"📩 *Message from* {user.first_name} (`{user.id}`):\n\n{text}"
    
    for admin in admins:
        try:
            await context.bot.send_message(
                chat_id=admin["telegram_id"],
                text=msg,
                parse_mode="Markdown"
            )
        except Exception:
            pass