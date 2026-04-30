"""
bot.py — Main entry point for PK Bazar Telegram Bot
"""

import os
import logging
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from database.db import init_db
from services.user_service import add_admin
from handlers.common import check_membership_callback

from handlers.user_handlers import (
    start,
    list_products,
    my_orders,
    support,
    handle_screenshot,
    buy_callback,
    product_detail_callback,
    plan_selected_callback,
    back_to_list_callback,
    help_btn_callback,
    resell_btn_callback,
    forward_to_admins,
)
from handlers.admin_handlers import (
    admin_panel,
    ADMIN_KEYBOARD,
    admin_products,
    add_product_start,
    ap_get_name, ap_get_desc, ap_get_price,
    ap_get_image, ap_skip_image, ap_get_validity, ap_cancel,
    edit_product_callback,
    ep_choose_field, ep_get_value,
    delete_product_callback, confirm_delete_callback,
    toggle_product_callback,
    # Plan management
    view_plans_callback,
    add_plan_start, pl_get_name, pl_get_price, pl_get_validity, pl_cancel,
    edit_plan_callback, epl_choose_field, epl_get_value, epl_cancel,
    delete_plan_callback, confirm_delete_plan_callback,
    addplan_cmd, delplan_cmd, listplans_cmd,
    admin_orders,
    orders_filter_callback,
    approve_order_callback,
    reject_order_callback,
    admin_users,
    ban_user_cmd, unban_user_cmd,
    broadcast_start, broadcast_send,
    msg_user_start, msg_user_get_id, msg_user_send,
    conv_cancel,
    manage_admins,
    add_admin_start, add_admin_do,
    remove_admin_start, remove_admin_do,
    AP_NAME, AP_DESC, AP_PRICE, AP_IMAGE, AP_VALIDITY,
    EP_FIELD, EP_VALUE,
    BROADCAST_MSG,
    MSG_USER_ID, MSG_USER_TEXT,
    ADD_ADMIN_ID, REMOVE_ADMIN_ID,
    PL_NAME, PL_PRICE, PL_VALIDITY,
    EPL_FIELD, EPL_VALUE,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def post_init(application):
    await init_db()
    await add_admin(8258290466, added_by=8258290466)
    print("✅ Database initialized.")


def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # ── Add product conversation ───────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_product_start, pattern="^add_product$"),
            CommandHandler("addproduct", add_product_start),
        ],
        states={
            AP_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_name)],
            AP_DESC:     [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_desc),
                CommandHandler("skip", ap_get_desc),
            ],
            AP_PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_price)],
            AP_IMAGE:    [
                MessageHandler(filters.PHOTO, ap_get_image),
                CommandHandler("skip", ap_skip_image),
            ],
            AP_VALIDITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_get_validity)],
        },
        fallbacks=[CommandHandler("cancel", ap_cancel)],
        allow_reentry=True,
    ))

    # ── Edit product conversation ──────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_product_callback, pattern="^edit_prod_\\d+$")],
        states={
            EP_FIELD: [CallbackQueryHandler(ep_choose_field, pattern="^ep_")],
            EP_VALUE: [
                MessageHandler(filters.PHOTO, ep_get_value),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ep_get_value),
                CommandHandler("skip", ep_get_value),
            ],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        allow_reentry=True,
    ))

    # ── Add plan conversation ──────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_plan_start, pattern="^add_plan_\\d+$")],
        states={
            PL_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, pl_get_name)],
            PL_PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, pl_get_price)],
            PL_VALIDITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, pl_get_validity)],
        },
        fallbacks=[CommandHandler("cancel", pl_cancel)],
        allow_reentry=True,
    ))

    # ── Edit plan conversation ─────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_plan_callback, pattern="^edit_plan_\\d+$")],
        states={
            EPL_FIELD: [CallbackQueryHandler(epl_choose_field, pattern="^epl_")],
            EPL_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, epl_get_value)],
        },
        fallbacks=[CommandHandler("cancel", epl_cancel)],
        allow_reentry=True,
    ))

    # ── Broadcast conversation ─────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📢 Broadcast$"), broadcast_start)],
        states={
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    ))

    # ── Message user conversation ──────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("msguser", msg_user_start),
            CallbackQueryHandler(msg_user_start, pattern="^prompt_msg_user$"),
        ],
        states={
            MSG_USER_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_user_get_id)],
            MSG_USER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_user_send)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    ))

    # ── Add admin conversation ─────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^prompt_add_admin$")],
        states={
            ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_do)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    ))

    # ── Remove admin conversation ──────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_admin_start, pattern="^prompt_remove_admin$")],
        states={
            REMOVE_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_do)],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
    ))

    # ── Commands ───────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("admin",      admin_panel))
    app.add_handler(CommandHandler("products",   admin_products))
    app.add_handler(CommandHandler("orders",     admin_orders))
    app.add_handler(CommandHandler("users",      admin_users))
    app.add_handler(CommandHandler("admins",     manage_admins))
    app.add_handler(CommandHandler("ban",        ban_user_cmd))
    app.add_handler(CommandHandler("unban",      unban_user_cmd))
    app.add_handler(CommandHandler("addplan",    addplan_cmd))
    app.add_handler(CommandHandler("delplan",    delplan_cmd))
    app.add_handler(CommandHandler("listplans",  listplans_cmd))

    # ── Admin reply keyboard ───────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Regex("^📦 Products$"),  admin_products))
    app.add_handler(MessageHandler(filters.Regex("^🧾 Orders$"),    admin_orders))
    app.add_handler(MessageHandler(filters.Regex("^👥 Users$"),     admin_users))
    app.add_handler(MessageHandler(filters.Regex("^🔐 Admins$"),    manage_admins))
    app.add_handler(MessageHandler(filters.Regex("^🏠 Home$"),      start))

    # ── User reply keyboard ────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Regex("^🛍️ Product List$"), list_products))
    app.add_handler(MessageHandler(filters.Regex("^📦 My Orders$"),     my_orders))
    app.add_handler(MessageHandler(filters.Regex("^🆘 Support$"),       support))

    # ── Inline callbacks ───────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(product_detail_callback,       pattern="^buy_\\d+$"))
    app.add_handler(CallbackQueryHandler(plan_selected_callback,        pattern="^plan_\\d+$"))
    app.add_handler(CallbackQueryHandler(buy_callback,                  pattern="^confirm_buy_\\d+_\\d+$"))
    app.add_handler(CallbackQueryHandler(back_to_list_callback,         pattern="^back_to_list$"))
    app.add_handler(CallbackQueryHandler(help_btn_callback,             pattern="^help_btn$"))
    app.add_handler(CallbackQueryHandler(resell_btn_callback,           pattern="^resell_btn$"))
    app.add_handler(CallbackQueryHandler(orders_filter_callback,        pattern="^orders_"))
    app.add_handler(CallbackQueryHandler(approve_order_callback,        pattern="^approve_\\d+$"))
    app.add_handler(CallbackQueryHandler(reject_order_callback,         pattern="^reject_\\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_product_callback,       pattern="^tog_prod_\\d+$"))
    app.add_handler(CallbackQueryHandler(view_plans_callback,           pattern="^view_plans_\\d+$"))
    app.add_handler(CallbackQueryHandler(delete_plan_callback,          pattern="^del_plan_\\d+_\\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_plan_callback,  pattern="^(confirm_del_plan_\\d+_\\d+|cancel_del_plan)$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_callback,       pattern="^(confirm_del_\\d+|cancel_del)$"))
    app.add_handler(CallbackQueryHandler(delete_product_callback,       pattern="^del_prod_\\d+$"))

    # ── Channel membership check ───────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(check_membership_callback, pattern="^check_membership$"))

    # ── Catch-all for user messages (Forwards replies to admins) ───────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admins))

    # ── Photo handler (must be last) ───────────────────────────────────────────
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_screenshot))

    print("🚀 PK Bazar Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()