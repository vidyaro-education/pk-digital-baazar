"""
handlers/keyboards.py
Centralised keyboard builders for both reply and inline keyboards.
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton


# ── Main user menu ─────────────────────────────────────────────────────────────

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🛍️ Product List", "📦 My Orders"],
            ["🆘 Support"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# ── Product grid keyboard ──────────────────────────────────────────────────────

def product_grid_keyboard(products: list) -> InlineKeyboardMarkup:
    """Build a 2-column inline keyboard grid from a list of products."""
    buttons = []
    row = []
    for i, p in enumerate(products):
        label = f"{p['name']} ₹{p['price']:.0f}"
        row.append(InlineKeyboardButton(label, callback_data=f"buy_{p['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Bottom utility row
    buttons.append([
        InlineKeyboardButton("⚠️ HELP",    callback_data="help_btn"),
        InlineKeyboardButton("🤝 Resell",  callback_data="resell_btn"),
    ])

    return InlineKeyboardMarkup(buttons)


# ── Product detail buttons ─────────────────────────────────────────────────────

def product_detail_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Confirm Buy", callback_data=f"confirm_buy_{product_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="back_to_list")],
    ])


# ── Buy now button (single product card) ──────────────────────────────────────

def buy_now_button(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy_{product_id}")]]
    )


# ── Order approval buttons ─────────────────────────────────────────────────────

def order_action_buttons(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{order_id}"),
        ]
    ])


# ── Product management buttons ─────────────────────────────────────────────────

def product_manage_buttons(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Deactivate" if is_active else "🟢 Activate"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit",   callback_data=f"edit_{product_id}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{product_id}"),
        ],
        [InlineKeyboardButton(toggle_label,   callback_data=f"toggle_{product_id}")],
    ])


# ── Cancel keyboard ────────────────────────────────────────────────────────────

def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True, one_time_keyboard=True)