# handlers/admin_handlers.py
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import ContextTypes, ConversationHandler

from handlers.common import admin_only, paginate, STATUS_EMOJI
from services.product_service import (
    get_all_products,
    add_product,
    update_product,
    delete_product,
    toggle_product,
    get_product_by_id,
)
from services.plan_service import (  # type: ignore[import]
    get_plans_by_product,
    add_plan,
    update_plan,
    delete_plan,
    get_plan_by_id,
)
from services.order_service import (
    get_all_orders,
    get_orders_by_status,
    update_order_status,
    get_order_by_id,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
from services.user_service import (
    get_all_users,
    add_admin,
    remove_admin,
    get_all_admins,
    ban_user,
    unban_user,
)

logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
(
    AP_NAME, AP_DESC, AP_PRICE, AP_IMAGE, AP_VALIDITY,
    EP_FIELD, EP_VALUE,
    BROADCAST_MSG,
    MSG_USER_ID, MSG_USER_TEXT,
    ADD_ADMIN_ID,
    REMOVE_ADMIN_ID,
    # Plan management states
    PL_NAME, PL_PRICE, PL_VALIDITY,
    EPL_FIELD, EPL_VALUE,
) = range(17)

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📦 Products"),   KeyboardButton("🧾 Orders")],
        [KeyboardButton("👥 Users"),      KeyboardButton("📢 Broadcast")],
        [KeyboardButton("🔐 Admins"),     KeyboardButton("🏠 Home")],
    ],
    resize_keyboard=True,
)


# ── Shared helper (imported by user_handlers too) ─────────────────────────────

def validity_display(months: int) -> str:
    """Convert a month count to a human-readable string."""
    if not months or months <= 0:
        return "No expiry"
    if months == 1:
        return "1 month"
    if months % 12 == 0:
        years = months // 12
        return f"{years} year{'s' if years > 1 else ''}"
    if months > 12:
        years = months // 12
        rem   = months % 12
        return f"{years}y {rem}m"
    return f"{months} months"


def hours_to_display(hours: int) -> str:
    """Convert validity_hours to a human-readable string."""
    if not hours or hours <= 0:
        return "No expiry"
    days = hours / 24
    if days < 1:
        return f"{hours}h"
    if days % 30 == 0:
        months = int(days // 30)
        return validity_display(months)
    if days % 7 == 0:
        weeks = int(days // 7)
        return f"{weeks} week{'s' if weeks > 1 else ''}"
    return f"{int(days)} day{'s' if days != 1 else ''}"


# ── Admin panel entry ─────────────────────────────────────────────────────────

@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 *Admin Panel*\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=ADMIN_KEYBOARD,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_only
async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = await get_all_products()
    if not products:
        await update.message.reply_text("No products yet.")
    else:
        for p in products:
            status = "✅ Active" if p["is_active"] else "❌ Inactive"
            validity_str = validity_display(p.get("validity_hours") or 0)
            text = (
                f"*#{p['id']} — {p['name']}*\n"
                f"Price    : ₹{p['price']:.2f}\n"
                f"Status   : {status}\n"
                f"Validity : {validity_str}\n"
                f"Expires  : {p['expires_at'] or 'Never'}"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✏️ Edit",    callback_data=f"edit_prod_{p['id']}"),
                    InlineKeyboardButton("🗑️ Delete",  callback_data=f"del_prod_{p['id']}"),
                    InlineKeyboardButton("🔄 Toggle",  callback_data=f"tog_prod_{p['id']}"),
                ],
                [
                    InlineKeyboardButton("📋 Plans",   callback_data=f"view_plans_{p['id']}"),
                ],
            ])
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    await update.message.reply_text(
        "➕ Add a new product?",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("➕ Add Product", callback_data="add_product")]]
        ),
    )


# ── Add product conversation ──────────────────────────────────────────────────

@admin_only
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        await q.message.reply_text("📝 Enter product *name*:", parse_mode="Markdown")
    else:
        await update.message.reply_text("📝 Enter product *name*:", parse_mode="Markdown")
    return AP_NAME


async def ap_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"] = {"name": update.message.text.strip()}
    await update.message.reply_text("📝 Enter *description* (or /skip):", parse_mode="Markdown")
    return AP_DESC


async def ap_get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_product"]["description"] = "" if text == "/skip" else text
    await update.message.reply_text("💰 Enter *price* (₹):", parse_mode="Markdown")
    return AP_PRICE


async def ap_get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
    except ValueError:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])
        await update.message.reply_text("❌ Invalid price. Enter a number:", reply_markup=kb)
        return AP_PRICE
    context.user_data["new_product"]["price"] = price
    await update.message.reply_text("🖼️ Send product *image* (or /skip):", parse_mode="Markdown")
    return AP_IMAGE


async def ap_get_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles photo upload. Any non-photo text is treated as skip."""
    if update.message.photo:
        context.user_data["new_product"]["image_file_id"] = update.message.photo[-1].file_id
    else:
        context.user_data["new_product"]["image_file_id"] = None
    await update.message.reply_text(
        "⏳ Enter *validity in months*\n_Enter 0 for no expiry:_",
        parse_mode="Markdown",
    )
    return AP_VALIDITY


async def ap_skip_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when user sends /skip at image step."""
    context.user_data["new_product"]["image_file_id"] = None
    await update.message.reply_text(
        "⏳ Enter *validity in months*\n_Enter 0 for no expiry:_",
        parse_mode="Markdown",
    )
    return AP_VALIDITY


async def ap_get_validity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        months = int(update.message.text.strip())
    except ValueError:
        months = 0
    p = context.user_data.pop("new_product", {})
    product_id = await add_product(
        name=p["name"],
        description=p.get("description", ""),
        price=p["price"],
        image_file_id=p.get("image_file_id"),
        validity_months=months,
    )
    await update.message.reply_text(
        f"✅ Product *{p['name']}* added! (ID: {product_id})\n"
        f"Validity: {validity_display(months)}\n\n"
        f"💡 Tip: Use the *📋 Plans* button on a product to add subscription plans.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def ap_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_product", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("❌ Cancelled.")
    else:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ── Edit product conversation ─────────────────────────────────────────────────

@admin_only
async def edit_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: show field-choice buttons."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await get_product_by_id(product_id)
    if not product:
        await query.message.reply_text("❌ Product not found.")
        return ConversationHandler.END

    context.user_data["edit_product_id"] = product_id
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📛 Name",        callback_data="ep_name"),
            InlineKeyboardButton("📝 Description", callback_data="ep_description"),
        ],
        [
            InlineKeyboardButton("💰 Price",       callback_data="ep_price"),
            InlineKeyboardButton("🖼️ Image",       callback_data="ep_image"),
        ],
        [
            InlineKeyboardButton("⏳ Validity",    callback_data="ep_validity"),
        ],
    ])
    await query.message.reply_text(
        f"✏️ Editing *{product['name']}*\nChoose a field to update:",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return EP_FIELD


async def ep_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store which field to edit and ask for the new value."""
    query = update.callback_query
    await query.answer()
    field = query.data[3:]  # strip "ep_" prefix
    context.user_data["edit_field"] = field

    prompts = {
        "name":        "📛 Enter new *name*:",
        "description": "📝 Enter new *description* (or /skip to clear):",
        "price":       "💰 Enter new *price* (₹):",
        "image":       "🖼️ Send new *image* (or /skip to keep current):",
        "validity":    "⏳ Enter new *validity in months* (0 = no expiry):",
    }
    await query.message.reply_text(prompts.get(field, "Enter value:"), parse_mode="Markdown")
    return EP_VALUE


async def ep_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply the edit."""
    field      = context.user_data.pop("edit_field", None)
    product_id = context.user_data.pop("edit_product_id", None)

    if not field or not product_id:
        await update.message.reply_text("❌ Something went wrong. Please start again.")
        return ConversationHandler.END

    text = update.message.text.strip() if update.message.text else None

    if field == "name":
        await update_product(product_id, name=text)
    elif field == "description":
        await update_product(product_id, description="" if text == "/skip" else text)
    elif field == "price":
        try:
            await update_product(product_id, price=float(text))
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid price.")
            return ConversationHandler.END
    elif field == "image":
        if update.message.photo:
            await update_product(product_id, image_file_id=update.message.photo[-1].file_id)
        elif text == "/skip":
            pass  # keep existing
        else:
            await update.message.reply_text("❌ Please send a photo or /skip.")
            return ConversationHandler.END
    elif field == "validity":
        try:
            months = int(text)
        except (ValueError, TypeError):
            months = 0
        await update_product(product_id, validity_hours=months)

    await update.message.reply_text(
        f"✅ Product #{product_id} *{field}* updated!", parse_mode="Markdown"
    )
    return ConversationHandler.END


# ── Delete with confirmation ──────────────────────────────────────────────────

@admin_only
async def delete_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for confirmation before deleting."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await get_product_by_id(product_id)
    name = product["name"] if product else f"#{product_id}"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, delete", callback_data=f"confirm_del_{product_id}"),
            InlineKeyboardButton("❌ Cancel",      callback_data="cancel_del"),
        ]
    ])
    await query.message.reply_text(
        f"⚠️ Delete *{name}*? This cannot be undone.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@admin_only
async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_del":
        await query.message.reply_text("❌ Delete cancelled.")
        return
    product_id = int(query.data.split("_")[-1])
    await delete_product(product_id)
    await query.message.reply_text(f"🗑️ Product #{product_id} deleted.")


# ── Toggle ────────────────────────────────────────────────────────────────────

@admin_only
async def toggle_product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    await toggle_product(product_id)
    product = await get_product_by_id(product_id)
    state = "Active ✅" if product["is_active"] else "Inactive ❌"
    await query.message.reply_text(
        f"Product #{product_id} is now *{state}*.", parse_mode="Markdown"
    )


# ── Quick edit commands ───────────────────────────────────────────────────────

@admin_only
async def editprice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /editprice <product_id> <new_price>")
        return
    await update_product(int(args[0]), price=float(args[1]))
    await update.message.reply_text(f"✅ Price updated for product #{args[0]}.")


@admin_only
async def editname_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /editname <product_id> <new name>")
        return
    await update_product(int(args[0]), name=" ".join(args[1:]))
    await update.message.reply_text(f"✅ Name updated for product #{args[0]}.")


@admin_only
async def editdesc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /editdesc <product_id> <description>")
        return
    await update_product(int(args[0]), description=" ".join(args[1:]))
    await update.message.reply_text(f"✅ Description updated.")


@admin_only
async def editvalidity_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /editvalidity <product_id> <months>")
        return
    try:
        months = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Months must be a whole number.")
        return
    await update_product(int(args[0]), validity_hours=months)
    await update.message.reply_text(
        f"✅ Validity updated to {validity_display(months)} for product #{args[0]}."
    )


# ══════════════════════════════════════════════════════════════════════════════
# PLAN MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_only
async def view_plans_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all plans for a product with edit/delete buttons."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    product = await get_product_by_id(product_id)
    if not product:
        await query.message.reply_text("❌ Product not found.")
        return

    plans = await get_plans_by_product(product_id)

    header = f"📋 *Plans for {product['name']}*\n"
    if not plans:
        header += "\n_No plans yet. Add one below!_"
        await query.message.reply_text(
            header,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Add Plan", callback_data=f"add_plan_{product_id}"),
            ]]),
        )
        return

    await query.message.reply_text(header, parse_mode="Markdown")

    for pl in plans:
        validity_str = hours_to_display(pl.get("validity_hours") or 0)
        text = (
            f"🏷️ *{pl['name']}*  (Plan #{pl['id']})\n"
            f"Price    : ₹{pl['price']:.2f}\n"
            f"Validity : {validity_str}"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✏️ Edit",   callback_data=f"edit_plan_{pl['id']}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"del_plan_{pl['id']}_{product_id}"),
        ]])
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    await query.message.reply_text(
        "➕ Add another plan?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Add Plan", callback_data=f"add_plan_{product_id}"),
        ]]),
    )


# ── Add plan conversation ─────────────────────────────────────────────────────

@admin_only
async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry: triggered by add_plan_<product_id> callback."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split("_")[-1])
    context.user_data["new_plan"] = {"product_id": product_id}

    product = await get_product_by_id(product_id)
    name = product["name"] if product else f"#{product_id}"
    await query.message.reply_text(
        f"📋 Adding plan for *{name}*\n\n📝 Enter plan *name*:\n_e.g. Monthly, 3 Months, Annual_",
        parse_mode="Markdown",
    )
    return PL_NAME


async def pl_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_plan"]["name"] = update.message.text.strip()
    await update.message.reply_text("💰 Enter plan *price* (₹):", parse_mode="Markdown")
    return PL_PRICE


async def pl_get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
    except ValueError:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])
        await update.message.reply_text("❌ Invalid price. Enter a number:", reply_markup=kb)
        return PL_PRICE
    context.user_data["new_plan"]["price"] = price
    await update.message.reply_text(
        "⏳ Enter *validity in hours*:\n"
        "_Common values: 720 = 1 month, 1440 = 2 months, 2160 = 3 months_\n"
        "_Enter 0 for no expiry._",
        parse_mode="Markdown",
    )
    return PL_VALIDITY


async def pl_get_validity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hours = int(update.message.text.strip())
    except ValueError:
        hours = 0
    pl = context.user_data.pop("new_plan", {})
    plan_id = await add_plan(
        product_id=pl["product_id"],
        name=pl["name"],
        price=pl["price"],
        validity_hours=hours,
    )
    await update.message.reply_text(
        f"✅ Plan *{pl['name']}* added! (ID: {plan_id})\n"
        f"Price    : ₹{pl['price']:.2f}\n"
        f"Validity : {hours_to_display(hours)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📋 View All Plans",
                callback_data=f"view_plans_{pl['product_id']}",
            )
        ]]),
    )
    return ConversationHandler.END


async def pl_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_plan", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("❌ Cancelled.")
    else:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ── Edit plan conversation ────────────────────────────────────────────────────

@admin_only
async def edit_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: show field-choice buttons for plan edit."""
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split("_")[-1])
    plan = await get_plan_by_id(plan_id)
    if not plan:
        await query.message.reply_text("❌ Plan not found.")
        return ConversationHandler.END

    context.user_data["edit_plan_id"] = plan_id
    validity_str = hours_to_display(plan.get("validity_hours") or 0)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📛 Name",     callback_data="epl_name"),
            InlineKeyboardButton("💰 Price",    callback_data="epl_price"),
        ],
        [
            InlineKeyboardButton("⏳ Validity", callback_data="epl_validity"),
        ],
    ])
    await query.message.reply_text(
        f"✏️ Editing plan *{plan['name']}*\n"
        f"Current price    : ₹{plan['price']:.2f}\n"
        f"Current validity : {validity_str}\n\n"
        f"Choose a field to update:",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    return EPL_FIELD


async def epl_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store which plan field to edit and prompt for new value."""
    query = update.callback_query
    await query.answer()
    field = query.data[4:]  # strip "epl_" prefix
    context.user_data["edit_plan_field"] = field

    prompts = {
        "name":     "📛 Enter new plan *name*:",
        "price":    "💰 Enter new *price* (₹):",
        "validity": (
            "⏳ Enter new *validity in hours*:\n"
            "_720 = 1 month · 1440 = 2 months · 2160 = 3 months · 0 = no expiry_"
        ),
    }
    await query.message.reply_text(prompts.get(field, "Enter value:"), parse_mode="Markdown")
    return EPL_VALUE


async def epl_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply the plan edit."""
    field   = context.user_data.pop("edit_plan_field", None)
    plan_id = context.user_data.pop("edit_plan_id", None)

    if not field or not plan_id:
        await update.message.reply_text("❌ Something went wrong. Please start again.")
        return ConversationHandler.END

    text = update.message.text.strip() if update.message.text else None

    if field == "name":
        await update_plan(plan_id, name=text)
    elif field == "price":
        try:
            await update_plan(plan_id, price=float(text))
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid price.")
            return ConversationHandler.END
    elif field == "validity":
        try:
            hours = int(text)
        except (ValueError, TypeError):
            hours = 0
        await update_plan(plan_id, validity_hours=hours)

    await update.message.reply_text(
        f"✅ Plan #{plan_id} *{field}* updated!", parse_mode="Markdown"
    )
    return ConversationHandler.END


async def epl_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("edit_plan_id", None)
    context.user_data.pop("edit_plan_field", None)
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ── Delete plan with confirmation ─────────────────────────────────────────────

@admin_only
async def delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """del_plan_<plan_id>_<product_id> — ask for confirmation."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")   # ["del", "plan", plan_id, product_id]
    plan_id    = int(parts[2])
    product_id = int(parts[3])
    plan = await get_plan_by_id(plan_id)
    name = plan["name"] if plan else f"#{plan_id}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Yes, delete", callback_data=f"confirm_del_plan_{plan_id}_{product_id}"
        ),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_del_plan"),
    ]])
    await query.message.reply_text(
        f"⚠️ Delete plan *{name}*? This cannot be undone.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@admin_only
async def confirm_delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_del_plan":
        await query.message.reply_text("❌ Delete cancelled.")
        return
    parts      = query.data.split("_")   # ["confirm", "del", "plan", plan_id, product_id]
    plan_id    = int(parts[3])
    product_id = int(parts[4])
    await delete_plan(plan_id)
    await query.message.reply_text(
        f"🗑️ Plan #{plan_id} deleted.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📋 View Remaining Plans", callback_data=f"view_plans_{product_id}"
            )
        ]]),
    )


# ── Quick plan commands ───────────────────────────────────────────────────────

@admin_only
async def addplan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /addplan <product_id> <price> <validity_hours> <name...>"""
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Usage: /addplan <product_id> <price> <validity_hours> <name>\n"
            "Example: /addplan 1 21 720 Monthly Plan"
        )
        return
    try:
        product_id     = int(args[0])
        price          = float(args[1])
        validity_hours = int(args[2])
        name           = " ".join(args[3:])
    except ValueError:
        await update.message.reply_text("❌ Invalid arguments.")
        return
    plan_id = await add_plan(
        product_id=product_id,
        name=name,
        price=price,
        validity_hours=validity_hours,
    )
    await update.message.reply_text(
        f"✅ Plan *{name}* added to product #{product_id}!\n"
        f"Plan ID  : {plan_id}\n"
        f"Price    : ₹{price:.2f}\n"
        f"Validity : {hours_to_display(validity_hours)}",
        parse_mode="Markdown",
    )


@admin_only
async def delplan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /delplan <plan_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /delplan <plan_id>")
        return
    plan_id = int(context.args[0])
    await delete_plan(plan_id)
    await update.message.reply_text(f"🗑️ Plan #{plan_id} deleted.")


@admin_only
async def listplans_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /listplans <product_id>"""
    if not context.args:
        await update.message.reply_text("Usage: /listplans <product_id>")
        return
    product_id = int(context.args[0])
    product    = await get_product_by_id(product_id)
    if not product:
        await update.message.reply_text("❌ Product not found.")
        return
    plans = await get_plans_by_product(product_id)
    if not plans:
        await update.message.reply_text(f"No plans for product #{product_id}.")
        return
    text = f"📋 *Plans for {product['name']}:*\n\n"
    for pl in plans:
        text += (
            f"• *{pl['name']}* (#{pl['id']}) — "
            f"₹{pl['price']:.2f} / {hours_to_display(pl.get('validity_hours') or 0)}\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_only
async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("All",      callback_data="orders_all"),
            InlineKeyboardButton("Pending",  callback_data="orders_PENDING"),
        ],
        [
            InlineKeyboardButton("Waiting",  callback_data="orders_WAITING_PAYMENT_CONFIRMATION"),
            InlineKeyboardButton("Approved", callback_data="orders_APPROVED"),
        ],
        [
            InlineKeyboardButton("Rejected", callback_data="orders_REJECTED"),
        ],
    ])
    await update.message.reply_text("🧾 Filter orders:", reply_markup=kb)


@admin_only
async def orders_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filter_key = query.data.split("_", 1)[1]

    orders = await get_all_orders() if filter_key == "all" else await get_orders_by_status(filter_key)

    if not orders:
        await query.message.reply_text("No orders found.")
        return

    items, total = paginate(orders, 0, per_page=5)

    for o in items:
        emoji = STATUS_EMOJI.get(o["status"], "❓")
        text = (
            f"{emoji} *Order #{o['id']}*\n"
            f"User    : {o['user_name']} (`{o['telegram_id']}`)\n"
            f"Product : {o['product_name']}\n"
            f"Amount  : ₹{o['price']:.2f}\n"
            f"Status  : {o['status']}\n"
            f"Date    : {o['created_at'][:16]}"
        )
        buttons = []
        if o["status"] == "WAITING_PAYMENT_CONFIRMATION":
            buttons = [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{o['id']}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{o['id']}"),
            ]
        kb = InlineKeyboardMarkup([buttons]) if buttons else None

        if o.get("screenshot_file_id"):
            await query.message.reply_photo(
                photo=o["screenshot_file_id"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


@admin_only
async def approve_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    await update_order_status(order_id, STATUS_APPROVED)
    order = await get_order_by_id(order_id)
    await query.message.reply_text(f"✅ Order #{order_id} *approved*.", parse_mode="Markdown")
    try:
        await context.bot.send_message(
            chat_id=order["telegram_id"],
            text=(
                f"🎉 *Your order has been approved!*\n\n"
                f"Order  : #{order_id}\n"
                f"Product: {order['product_name']}\n\n"
                "Thank you for shopping at PK Bazar! 🛒"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Could not notify user: %s", e)


@admin_only
async def reject_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[1])
    await update_order_status(order_id, STATUS_REJECTED, note="Rejected by admin")
    order = await get_order_by_id(order_id)
    await query.message.reply_text(f"❌ Order #{order_id} *rejected*.", parse_mode="Markdown")
    try:
        await context.bot.send_message(
            chat_id=order["telegram_id"],
            text=(
                f"😔 *Your order has been rejected.*\n\n"
                f"Order  : #{order_id}\n"
                f"Product: {order['product_name']}\n\n"
                "If you believe this is an error, please contact support."
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Could not notify user: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_only
async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    if not users:
        await update.message.reply_text("No users yet.")
        return
    text = f"👥 *Total users: {len(users)}*\n\n"
    for u in users[:20]:
        banned = " 🚫" if u["is_banned"] else ""
        text += f"• {u['name'] or 'Unknown'} (`{u['telegram_id']}`){banned}\n"
    if len(users) > 20:
        text += f"\n_...and {len(users) - 20} more._"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Message User", callback_data="prompt_msg_user")]])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


@admin_only
async def ban_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /ban <telegram_id>")
        return
    await ban_user(int(context.args[0]))
    await update.message.reply_text(f"🚫 User `{context.args[0]}` banned.", parse_mode="Markdown")


@admin_only
async def unban_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unban <telegram_id>")
        return
    await unban_user(int(context.args[0]))
    await update.message.reply_text(
        f"✅ User `{context.args[0]}` unbanned.", parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGING
# ══════════════════════════════════════════════════════════════════════════════

@admin_only
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 Enter broadcast message:")
    return BROADCAST_MSG


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    users = await get_all_users()
    success = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["telegram_id"], text=f"📢 {text}")
            success += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {success}/{len(users)} users.")
    return ConversationHandler.END


@admin_only
async def msg_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    await msg.reply_text("👤 Enter the user's Telegram ID:")
    return MSG_USER_ID


async def msg_user_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["msg_target"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")
        return MSG_USER_ID
    await update.message.reply_text("✍️ You are now chatting with this user. Type your messages below.\nType /stopchat to end.")
    return MSG_USER_TEXT


async def msg_user_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get("msg_target")
    if not target:
        return ConversationHandler.END

    try:
        await context.bot.send_message(
            chat_id=target,
            text=f"💬 *Message from Admin:*\n\n{update.message.text}",
            parse_mode="Markdown",
        )
        await update.message.reply_text("✅ Message sent.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")
    return MSG_USER_TEXT


async def stop_msg_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("msg_target", None)
    await update.message.reply_text("🛑 Chat session ended.")
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_only
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await get_all_admins()
    text = "🔐 *Current Admins:*\n\n"
    for a in admins:
        text += f"• `{a['telegram_id']}` (added {a['created_at'][:10]})\n"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Admin",    callback_data="prompt_add_admin"),
            InlineKeyboardButton("➖ Remove Admin", callback_data="prompt_remove_admin"),
        ]
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


@admin_only
async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Enter Telegram ID to *add* as admin:", parse_mode="Markdown")
    return ADD_ADMIN_ID


async def add_admin_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")
        return ADD_ADMIN_ID
    ok = await add_admin(new_id, update.effective_user.id)
    await update.message.reply_text(
        f"✅ `{new_id}` added as admin." if ok else "❌ Failed.", parse_mode="Markdown"
    )
    return ConversationHandler.END


@admin_only
async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "Enter Telegram ID to *remove* from admins:", parse_mode="Markdown"
    )
    return REMOVE_ADMIN_ID


async def remove_admin_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rem_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")
        return REMOVE_ADMIN_ID
    ok = await remove_admin(rem_id)
    await update.message.reply_text(
        f"✅ `{rem_id}` removed from admins." if ok else "❌ Failed.", parse_mode="Markdown"
    )
    return ConversationHandler.END