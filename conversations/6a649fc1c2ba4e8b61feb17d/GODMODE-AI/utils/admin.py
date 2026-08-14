"""
Project GODMODE — Admin Controls
Admin-only commands for bot management.
"""

import logging
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.config import ADMIN_IDS, CATEGORIES, MODELS, get_model_label
from utils.memory import get_global_stats, get_session_info, clear_session, get_user_stats

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Check if a user ID is in the admin list."""
    return user_id in ADMIN_IDS


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin control panel."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    stats = get_global_stats()
    text = (
        "🔐 **GODMODE Admin Panel**\n\n"
        f"📊 **Today's Stats:**\n"
        f"  • Messages: {stats.get('total_messages_today', 0)}\n"
        f"  • Tokens: {stats.get('total_tokens_today', 0)}\n\n"
        f"👥 Admins: {len(ADMIN_IDS)}\n\n"
        "Select an action:"
    )

    keyboard = [
        [InlineKeyboardButton("📊 Global Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔍 User Lookup", callback_data="admin_lookup")],
        [InlineKeyboardButton("🗑️ Clear User Session", callback_data="admin_clear")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
    ]
    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel button callbacks."""
    query = update.callback_query
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer("Not authorized.", show_alert=True)
        return

    await query.answer()

    if query.data == "admin_stats":
        stats = get_global_stats()
        text = (
            "📊 **Global Stats (Today)**\n\n"
            f"• Total Messages: {stats.get('total_messages_today', 0)}\n"
            f"• Total Tokens: {stats.get('total_tokens_today', 0)}\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "admin_lookup":
        await query.edit_message_text(
            "🔍 Send the Telegram user ID to look up.\n"
            "Format: `/lookup 123456789`",
            parse_mode="Markdown",
        )
        context.user_data["admin_action"] = "lookup"

    elif query.data == "admin_clear":
        await query.edit_message_text(
            "🗑️ Send the Telegram user ID to clear their session.\n"
            "Format: `/clearuser 123456789`",
            parse_mode="Markdown",
        )

    elif query.data == "admin_broadcast":
        await query.edit_message_text(
            "📢 Send the message to broadcast to all active users.\n"
            "Format: `/broadcast Your message here`",
            parse_mode="Markdown",
        )


async def lookup_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: look up a user's session info."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /lookup <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID. Must be a number.")
        return

    session_info = get_session_info(target_id)
    user_stats = get_user_stats(target_id)

    text = (
        f"🔍 **User {target_id}**\n\n"
        f"• Active: {session_info.get('active', False)}\n"
        f"• Messages in history: {session_info.get('message_count', 0)}\n"
        f"• Session expires: {session_info.get('expires_in', 'N/A')}\n\n"
        f"**Today's Usage:**\n"
        f"• Messages: {user_stats.get('messages_today', 0)}\n"
        f"• Tokens: {user_stats.get('tokens_today', 0)}\n"
        f"• Images: {user_stats.get('images_today', 0)}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def clear_user_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: clear a user's session."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /clearuser <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    if clear_session(target_id):
        await update.message.reply_text(f"✅ Session cleared for user {target_id}")
    else:
        await update.message.reply_text(f"❌ Failed to clear session for user {target_id}")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: broadcast a message (placeholder — needs active user tracking)."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)
    await update.message.reply_text(
        f"📢 Broadcast queued:\n\n{message}\n\n"
        "Note: Active user tracking is needed for full broadcast. "
        "This feature requires a registered users list in Redis."
    )
