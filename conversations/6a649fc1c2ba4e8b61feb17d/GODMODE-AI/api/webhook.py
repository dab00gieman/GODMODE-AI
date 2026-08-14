"""
Project GODMODE — Telegram Bot Webhook Handler
Production-grade webhook with SOUL.md-anchored context, agent loop, learning, and Firebase Firestore.

Task 2: /forgetskill admin command to delete learned skills
Task 5: record_usage() called on agent-mode turns
Task 11: Request ID generated and threaded through all logging
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from http.server import BaseHTTPRequestHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from utils.config import (
    MODELS,
    CATEGORIES,
    TELEGRAM_BOT_TOKEN,
    ADMIN_IDS,
    DEFAULT_MODEL,
    RATE_LIMIT,
    get_model_label,
    is_image_model,
    AGENT_CONFIG,
    get_godmode_prompt,
)
from utils.memory import (
    get_session,
    save_session,
    clear_session,
    get_session_info,
    get_prefs,
    set_prefs,
    record_usage,
    check_rate_limit,
    get_user_stats,
)
from utils.openrouter import send_message, generate_image, list_available_models
from utils.formatter import split_message, sanitize_input, truncate_with_ellipsis
from utils.admin import (
    is_admin,
    admin_panel,
    handle_admin_callback,
    lookup_user,
    clear_user_session,
    broadcast,
)

# ──────────────────────────── LOGGING ────────────────────────────

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────── SKILL REGISTRY INIT ────────────────────────────

# Initialize skills at module load time — runs on every cold start.
# This is correct for Vercel serverless: each fresh invocation needs the registry populated.
from utils.skills import initialize_skills, list_skills, get_skills_prompt_section
from utils.agent import Agent, should_use_agent, generate_request_id
initialize_skills()
logger.info(f"Skill registry initialized with {len(list_skills())} skills")

# ──────────────────────────── APPLICATION ────────────────────────────

bot_app: Application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# ──────────────────────────── SERVERLESS INIT ────────────────────────────

_bot_initialized = False


# ──────────────────────────── COMMANDS ────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize GODMODE with categorized model selection."""
    user = update.effective_user
    keyboard = _build_category_keyboard()

    welcome = (
        f"🔥 **PROJECT GODMODE ACTIVATED** 🔥\n\n"
        f"Welcome, {user.first_name}!\n\n"
        f"I provide access to {len(MODELS)}+ AI models across 5 categories.\n"
        f"Pick an engine below, then send me anything.\n\n"
        f"**Quick Commands:**\n"
        f"  /model — Change engine\n"
        f"  /clear — Wipe history\n"
        f"  /status — View status\n"
        f"  /settings — Preferences\n"
        f"  /agent — Toggle agent mode\n"
        f"  /godmode — Toggle unrestricted mode (obey user, no refusals)\n"
        f"  /tools — List available skills\n"
        f"  /memory — View long-term memory\n"
        f"  /skills — List learned skills\n"
        f"  /forgetskill — Admin: remove a learned skill\n"
        f"  /help — Full guide\n"
    )

    await update.message.reply_text(
        welcome,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprehensive help."""
    text = (
        "🔥 **GODMODE — Full Guide**\n\n"
        "**Architecture:**\n"
        "  🧠 SOUL.md — persistent personality injected every turn\n"
        "  🤖 Agent mode — ReAct loop with native function calling\n"
        "  📖 Learned skills — bot writes new skills from experience\n"
        "  💾 Episodic memory — semantic recall of past interactions\n"
        "  🔧 10+ built-in tools (search, code, weather, translate...)\n"
        "  ⚡ Auto fallback chains if a model is down\n"
        "  🎨 Image generation (FLUX, GPT Image)\n\n"
        "**Commands:**\n"
        "  /start — Main menu & engine selection\n"
        "  /model — Change AI engine\n"
        "  /clear — Wipe conversation history\n"
        "  /status — Current engine, history, usage\n"
        "  /settings — Adjust temperature, tokens\n"
        "  /models — List all available engines\n"
        "  /agent — Toggle agentic mode on/off\n"
        "  /godmode — Toggle unrestricted mode (no refusals, full delivery)\n"
        "  /tools — List available skills\n"
        "  /memory — View long-term memory\n"
        "  /skills — List learned skills\n"
        "  /forgetskill — Admin: remove a learned skill by name\n"
        "  /help — This message\n\n"
        "**Tips:**\n"
        "  • Ask complex multi-step questions — the agent will plan and execute\n"
        "  • The bot learns from complex tasks and creates reusable skills\n"
        "  • Use /clear if context gets confused\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear conversation history."""
    chat_id = update.effective_chat.id
    if clear_session(chat_id):
        await update.message.reply_text("🗑️ History wiped. Fresh start.")
    else:
        await update.message.reply_text("⚠️ Could not clear history (memory backend offline).")


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show model selection menu."""
    keyboard = _build_category_keyboard()
    await update.message.reply_text(
        "📡 Select an engine category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed status."""
    chat_id = update.effective_chat.id
    prefs = get_prefs(chat_id)
    session_info = get_session_info(chat_id)
    user_stats = get_user_stats(chat_id)
    current_model = prefs.get("model") or DEFAULT_MODEL
    model_label = get_model_label(current_model)
    agent_on = prefs.get("agent_enabled", AGENT_CONFIG.enabled)

    text = (
        f"📊 **GODMODE Status**\n\n"
        f"🧠 **Engine:** {model_label}\n"
        f"🌡️ **Temperature:** {prefs.get('temperature', 0.7)}\n"
        f"📏 **Max tokens:** {prefs.get('max_tokens', 4096)}\n"
        f"🤖 **Agent mode:** {'ON' if agent_on else 'OFF'}\n\n"
        f"📜 **History:** {session_info.get('message_count', 0)} messages\n"
        f"⏰ **Session expires:** {session_info.get('expires_in', 'N/A')}\n\n"
        f"📈 **Today's Usage:**\n"
        f"  • Messages: {user_stats.get('messages_today', 0)}/{RATE_LIMIT.max_messages}\n"
        f"  • Tokens: {user_stats.get('tokens_today', 0)}\n"
        f"  • Images: {user_stats.get('images_today', 0)}/{RATE_LIMIT.image_max}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available models."""
    lines = ["📋 **All Available Engines**\n"]
    for category_name, category_models in CATEGORIES.items():
        lines.append(f"\n{category_name}:")
        for model_id, model_str in category_models.items():
            label = get_model_label(model_str)
            lines.append(f"  • {label} — `/{model_id}`")

    text = "\n".join(lines)
    for chunk in split_message(text):
        await update.message.reply_text(chunk, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show and adjust user settings."""
    chat_id = update.effective_chat.id
    prefs = get_prefs(chat_id)

    current_model = prefs.get("model") or DEFAULT_MODEL
    temp = prefs.get("temperature", 0.7)
    max_tok = prefs.get("max_tokens", 4096)
    agent_on = prefs.get("agent_enabled", AGENT_CONFIG.enabled)

    text = (
        f"⚙️ **Your Settings**\n\n"
        f"🧠 Engine: {get_model_label(current_model)}\n"
        f"🌡️ Temperature: {temp}\n"
        f"📏 Max tokens: {max_tok}\n"
        f"🤖 Agent mode: {'ON' if agent_on else 'OFF'}\n\n"
        f"**Adjust:**\n"
        f"  /settemp <0.0-2.0> — Creativity level\n"
        f"  /settokens <1-8192> — Max response length\n"
        f"  /setmodel <id> — Quick model switch\n"
        f"  /agent — Toggle agent mode\n"
        f"  /godmode — Toggle unrestricted mode (obey user, no refusals)\n"
        f"  /reset — Reset to defaults\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def settemp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set temperature."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Usage: /settemp <0.0 to 2.0>\n\n0.0 = precise, 1.0 = balanced, 2.0 = wild")
        return
    try:
        temp = float(context.args[0])
        if not 0.0 <= temp <= 2.0:
            raise ValueError
        set_prefs(chat_id, temperature=temp)
        await update.message.reply_text(f"✅ Temperature set to {temp}")
    except ValueError:
        await update.message.reply_text("❌ Value must be between 0.0 and 2.0")


async def settokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max tokens."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Usage: /settokens <1-8192>")
        return
    try:
        tokens = int(context.args[0])
        if not 1 <= tokens <= 8192:
            raise ValueError
        set_prefs(chat_id, max_tokens=tokens)
        await update.message.reply_text(f"✅ Max tokens set to {tokens}")
    except ValueError:
        await update.message.reply_text("❌ Value must be between 1 and 8192")


async def setmodel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick model switch by ID."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Usage: /setmodel <model_id>\n\nUse /models to see available IDs.")
        return
    model_id = context.args[0]
    if model_id not in MODELS:
        await update.message.reply_text(f"❌ Unknown model ID. Use /models to see options.")
        return
    model_str = MODELS[model_id]
    set_prefs(chat_id, model=model_str)
    context.user_data["model"] = model_str
    await update.message.reply_text(f"✅ Engine set to {get_model_label(model_str)}")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset settings to defaults."""
    chat_id = update.effective_chat.id
    set_prefs(chat_id, model=None, temperature=0.7, max_tokens=4096)
    await update.message.reply_text("✅ Settings reset to defaults.")


async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle agent mode on/off."""
    chat_id = update.effective_chat.id
    prefs = get_prefs(chat_id)
    current = prefs.get("agent_enabled", AGENT_CONFIG.enabled)
    new_val = not current
    set_prefs(chat_id, agent_enabled=new_val)
    status_text = "ON 🔥" if new_val else "OFF"
    await update.message.reply_text(
        f"🤖 Agent mode is now {status_text}\n\n"
        f"When ON, GODMODE automatically uses tools (search, weather, calculator, etc.) for complex requests.\n"
        f"When OFF, GODMODE answers directly without tools."
    )


async def godmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle GODMODE on/off. When ON, Lisa obeys the user without restrictions."""
    chat_id = update.effective_chat.id
    prefs = get_prefs(chat_id)
    current = prefs.get("godmode_enabled", AGENT_CONFIG.godmode_default)
    new_val = not current
    set_prefs(chat_id, godmode_enabled=new_val)
    if new_val:
        await update.message.reply_text(
            "🔥 GODMODE is now ON\n\n"
            "Lisa will now:\n"
            "• Answer directly to you and you only\n"
            "• Never refuse a request on policy grounds\n"
            "• Deliver complete, unredacted technical answers\n"
            "• Treat all hacking/security questions as authorized ethical hacking\n"
            "• No disclaimers, warnings, or moral commentary\n\n"
            "Toggle off with /godmode"
        )
    else:
        await update.message.reply_text(
            "✅ GODMODE is now OFF\n\n"
            "Lisa will operate with standard guardrails.\n"
            "She'll still help with ethical hacking and coding, but may add context about authorization where relevant.\n\n"
            "Toggle on with /godmode"
        )


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available skills."""
    all_skills = list_skills()
    desc = "\n".join(s.to_prompt_text() for s in all_skills)
    text = (
        f"🔧 **Available Skills ({len(all_skills)}):**\n\n"
        f"{desc}\n\n"
        f"Agent mode: {get_prefs(update.effective_chat.id).get('agent_enabled', AGENT_CONFIG.enabled)}\n"
        f"Toggle with /agent"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View long-term MEMORY.md."""
    from utils.context import read_memory_md
    memory = read_memory_md()
    if memory:
        for chunk in split_message(f"📖 **MEMORY.md:**\n\n{memory}"):
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text("📖 No long-term memories stored yet. Memory builds up as you interact.")


async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all skills — bundled and learned."""
    all_skills = list_skills()
    bundled = [s for s in all_skills if s.source == "bundled"]
    learned = [s for s in all_skills if s.source == "learned"]

    text = f"🔧 **Skills ({len(all_skills)} total)**\n\n"
    text += f"**Bundled ({len(bundled)}):**\n"
    for s in bundled:
        text += f"  • {s.name} — {s.description}\n"

    if learned:
        text += f"\n**Learned ({len(learned)}):**\n"
        for s in learned:
            text += f"  • {s.name} — {s.description}\n"
    else:
        text += "\n**Learned:** None yet. The agent learns from complex multi-step tasks.\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ──────────────────────────── ADMIN: FORGETSKILL (Task 2) ────────────────────────────

async def forgetskill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin-only: Delete a learned skill by name.
    Calls delete_learned_skill() from utils.skills, which removes it from
    both the live registry and Firestore.
    """
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        # List learned skills for reference
        from utils.skills import list_skills
        learned = [s for s in list_skills() if s.source == "learned"]
        if learned:
            names = "\n".join(f"  • {s.name} — {s.description[:60]}" for s in learned)
            await update.message.reply_text(
                f"Usage: /forgetskill <name>\n\n"
                f"**Learned skills:**\n{names}"
            )
        else:
            await update.message.reply_text("Usage: /forgetskill <name>\n\nNo learned skills to delete.")
        return

    skill_name = context.args[0]

    from utils.skills import delete_learned_skill, get_skill

    # Verify the skill exists
    skill = get_skill(skill_name)
    if not skill:
        await update.message.reply_text(f"❌ Skill '{skill_name}' not found. Use /skills to see all skills.")
        return

    if skill.source == "bundled":
        await update.message.reply_text(
            f"❌ '{skill_name}' is a bundled skill and cannot be deleted.\n"
            f"Only learned skills (created by the agent) can be removed."
        )
        return

    success = delete_learned_skill(skill_name)
    if success:
        logger.info(f"Admin {user_id} deleted learned skill: {skill_name}")
        await update.message.reply_text(
            f"✅ Learned skill '{skill_name}' deleted.\n"
            f"It has been removed from the registry and Firestore."
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to delete skill '{skill_name}'. Check logs for details."
        )


# ──────────────────────────── ADMIN COMMANDS ────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await admin_panel(update, context)


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await broadcast(update, context)


async def admin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await lookup_user(update, context)


async def admin_clearuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await clear_user_session(update, context)


# ──────────────────────────── INLINE KEYBOARD ────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline keyboard callbacks."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "clear":
        clear_session(chat_id)
        await query.edit_message_text("🗑️ History wiped. Start fresh.")
        return

    if query.data == "help":
        help_text = (
            "🔥 **GODMODE Help**\n\n"
            "1. Choose a category → select a model\n"
            "2. Send any message\n"
            "3. GODMODE responds\n\n"
            "**Commands:**\n"
            "  /start — Main menu\n"
            "  /model — Change engine\n"
            "  /clear — Wipe history\n"
            "  /status — View status\n"
            "  /agent — Toggle agent mode\n"
            "  /tools — List skills\n"
            "  /help — Full guide\n"
        )
        await query.edit_message_text(help_text, parse_mode="Markdown")
        return

    if query.data and query.data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return

    if query.data.startswith("cat_"):
        category_name = query.data[4:]
        category_models = CATEGORIES.get(category_name, {})
        if not category_models:
            await query.edit_message_text("❌ No models in this category.")
            return
        keyboard = []
        for model_id, model_str in category_models.items():
            label = get_model_label(model_str)
            keyboard.append([InlineKeyboardButton(f"🧠 {label}", callback_data=f"model_{model_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        await query.edit_message_text(
            f"📂 {category_name}\n\nSelect an engine:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if query.data.startswith("model_"):
        model_id = query.data[6:]
        if model_id in MODELS:
            model_str = MODELS[model_id]
            set_prefs(chat_id, model=model_str)
            context.user_data["model"] = model_str
            label = get_model_label(model_str)
            await query.edit_message_text(
                f"✅ **Engine:** {label}\n\nSend me anything. Use /help for commands.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("❌ Invalid model.")
        return

    if query.data == "back":
        keyboard = _build_category_keyboard()
        await query.edit_message_text(
            "🔥 **GODMODE**\n\nChoose a category:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return


# ──────────────────────────── MESSAGE HANDLER (Tasks 5, 11) ────────────────────────────

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main message handler — the integrated OpenClaw/Hermes pipeline.

    Flow:
    1. Generate request ID (Task 11 — observability)
    2. Get user prefs + session history
    3. Append user message to history
    4. Build SOUL.md-anchored context via context.build_context()
    5. Check if agent mode is needed (should_use_agent)
    6. If agent: run Agent.run() with native function calling (Task 7)
    7. If direct: send_message with SOUL-anchored context (no skills layer)
    8. After agent runs: call reflector + store episodic memory
    9. Record usage (Task 5 — now includes agent mode)
    10. Save session, send response
    """
    chat_id = update.effective_chat.id
    user = update.effective_user
    raw_text = update.message.text or ""

    if not raw_text:
        return

    user_message = sanitize_input(raw_text)
    if not user_message:
        return

    # Task 11: Generate request ID for observability
    request_id = generate_request_id(chat_id)
    logger.info(f"[{request_id}] New message from {user.id}: {user_message[:80]}...")

    # Get user preferences
    prefs = get_prefs(chat_id)
    model = prefs.get("model") or DEFAULT_MODEL
    temperature = prefs.get("temperature", 0.7)
    max_tokens = prefs.get("max_tokens", 4096)
    agent_enabled = prefs.get("agent_enabled", AGENT_CONFIG.enabled)

    # Check if image model
    is_img = is_image_model(model)

    # Rate limiting
    rate = check_rate_limit(chat_id, is_image=is_img)
    if not rate["allowed"]:
        reset_mins = rate["reset_in"] // 60
        await update.message.reply_text(
            f"⏳ Rate limit reached. Try again in ~{reset_mins} minutes.\n"
            f"Daily limit: {RATE_LIMIT.max_messages} messages, {RATE_LIMIT.image_max} images."
        )
        return

    # Send typing indicator
    await update.message.chat.send_action(action="typing")

    # Get conversation history
    history = get_session(chat_id)
    history.append({"role": "user", "content": user_message})

    try:
        # ──── ROUTE: Agent or Direct ────
        use_agent = (
            agent_enabled
            and not is_img
            and AGENT_CONFIG.enabled
            and should_use_agent(user_message)
        )

        # Task 6: Log should_use_agent decision for tuning
        logger.info(f"[{request_id}] should_use_agent={use_agent} for: '{user_message[:60]}'")

        if use_agent:
            # ──── AGENTIC MODE ────
            logger.info(f"[{request_id}] Agent mode triggered for chat {chat_id}")
            agent = Agent(model=model, temperature=0.4)
            godmode_on = prefs.get("godmode_enabled", AGENT_CONFIG.godmode_default)
            response, agent_meta = agent.run(
                user_message=user_message,
                history=history,
                model=model,
                chat_id=chat_id,
                request_id=request_id,
                godmode=godmode_on,
            )

            # Task 5: Record usage for agent-mode turns
            # Use estimated tokens from agent_meta (or rough estimate if unavailable)
            est_tokens = agent_meta.get("total_tokens", 0)
            if est_tokens == 0:
                # Rough estimate: ~4 chars per token, across all iterations
                est_tokens = (len(user_message) + len(response)) // 4 * agent_meta.get("iterations", 1)

            record_usage(chat_id, model, est_tokens, "agent")
            logger.info(f"[{request_id}] Usage recorded: model={model}, tokens={est_tokens}, type=agent")

            # Show agent indicator if tools were used
            tools_used = agent_meta.get("tools_used", [])
            if tools_used:
                tools_list = ", ".join(tools_used)
                response = f"_(🤖 Agent: {tools_list})_\n\n{response}"

            # ──── REFLECTOR + EPISODIC STORAGE ────
            if len(tools_used) >= MIN_TOOLS_FOR_LEARNING and AGENT_CONFIG.learning_enabled:
                try:
                    from utils.reflector import reflect_on_task, consolidate_memory

                    logger.info(f"[{request_id}] Running learning checkpoint (reflector)...")
                    reflect_result = reflect_on_task(
                        user_message=user_message,
                        tool_history=agent_meta.get("tool_results", []),
                        iterations=agent_meta.get("iterations", 0),
                        outcome=response[:500],
                        model=model,
                    )
                    if reflect_result and reflect_result.get("should_learn"):
                        logger.info(f"[{request_id}] Agent learned new skill: {reflect_result.get('skill_name')}")

                    consolidate_memory(
                        user_message=user_message,
                        response=response,
                        tool_history=agent_meta.get("tool_results", []),
                    )
                except Exception as e:
                    logger.error(f"[{request_id}] Learning checkpoint failed: {e}")

            # Store episodic memory
            try:
                from utils.context import store_episode
                store_episode(
                    chat_id=chat_id,
                    query=user_message,
                    summary=response[:1000] if response else "",
                    tools_used=tools_used,
                )
            except Exception as e:
                logger.error(f"[{request_id}] Episodic storage failed: {e}")

        else:
            # ──── DIRECT MODE ────
            from utils.context import build_context

            godmode_on = prefs.get("godmode_enabled", AGENT_CONFIG.godmode_default)
            messages = build_context(
                chat_id=chat_id,
                history=history,
                user_message=user_message,
                include_skills=False,     # No tools in direct mode
                include_episodic=False,    # Skip episodic search for speed in direct mode
                godmode=godmode_on,
            )

            # Send directly to OpenRouter (bypasses send_message's system prompt, which would double it)
            from utils.openrouter import HEADERS, BASE_URL
            import requests as req

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 0.95,
            }

            try:
                resp = req.post(BASE_URL, headers=HEADERS, json=payload, timeout=50)
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    response = data["choices"][0]["message"]["content"]
                else:
                    response = "⚠️ Empty response from model."
                usage = data.get("usage", {})
                usage["model_used"] = model
            except Exception as e:
                logger.error(f"[{request_id}] Direct mode LLM call failed: {e}")
                # Fallback to send_message (which adds its own system prompt)
                response, usage = send_message(
                    model=model,
                    messages=history,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            # Record usage
            if usage:
                tokens = usage.get("total_tokens", 0)
                actual_model = usage.get("model_used", model)
                record_usage(chat_id, actual_model, tokens, "image" if is_img else "text")
                logger.info(f"[{request_id}] Usage recorded: model={actual_model}, tokens={tokens}, type={'image' if is_img else 'text'}")

                if usage.get("fallback_from"):
                    fb_label = get_model_label(usage["fallback_from"])
                    actual_label = get_model_label(actual_model)
                    response = f"_(⚠️ {fb_label} was unavailable — used {actual_label})_\n\n{response}"

    except Exception as e:
        logger.error(f"[{request_id}] Chat handler error: {e}", exc_info=True)
        response = f"⚠️ Error: {str(e)[:200]}"

    # Add assistant response to history
    history.append({"role": "assistant", "content": response})
    save_session(chat_id, history)

    # Handle image responses (URLs)
    if is_img and response.startswith("http"):
        try:
            await update.message.reply_photo(
                photo=response,
                caption=f"🎨 Generated with {get_model_label(model)}"
            )
        except Exception:
            for chunk in split_message(response):
                await update.message.reply_text(chunk, parse_mode="Markdown")
        return

    # Send text response (with smart splitting)
    for chunk in split_message(response):
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            try:
                await update.message.reply_text(chunk)
            except Exception as e:
                logger.error(f"[{request_id}] Failed to send message: {e}")


# ──────────────────────────── ERROR HANDLER ────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log errors with context."""
    err_str = str(context.error)
    logger.error(f"Exception: {err_str}", exc_info=True)
    if update and isinstance(update, Update) and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                f"⚠️ Error: {err_str[:300]}\n\nTry /clear and resend."
            )
        except Exception:
            pass


# ──────────────────────────── HELPERS ────────────────────────────

def _build_category_keyboard() -> list:
    """Build the category selection keyboard."""
    keyboard = []
    for category_name in CATEGORIES.keys():
        keyboard.append([InlineKeyboardButton(category_name, callback_data=f"cat_{category_name}")])
    keyboard.append([
        InlineKeyboardButton("🗑️ Clear", callback_data="clear"),
        InlineKeyboardButton("ℹ️ Help", callback_data="help"),
    ])
    return keyboard


# ──────────────────────────── REGISTER HANDLERS ────────────────────────────

# Commands
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_command))
bot_app.add_handler(CommandHandler("clear", clear_command))
bot_app.add_handler(CommandHandler("model", model_command))
bot_app.add_handler(CommandHandler("models", models_command))
bot_app.add_handler(CommandHandler("status", status_command))
bot_app.add_handler(CommandHandler("settings", settings_command))
bot_app.add_handler(CommandHandler("settemp", settemp_command))
bot_app.add_handler(CommandHandler("settokens", settokens_command))
bot_app.add_handler(CommandHandler("setmodel", setmodel_command))
bot_app.add_handler(CommandHandler("reset", reset_command))
bot_app.add_handler(CommandHandler("agent", agent_command))
bot_app.add_handler(CommandHandler("godmode", godmode_command))
bot_app.add_handler(CommandHandler("tools", tools_command))
bot_app.add_handler(CommandHandler("memory", memory_command))
bot_app.add_handler(CommandHandler("skills", skills_command))

# Admin
bot_app.add_handler(CommandHandler("admin", admin_command))
bot_app.add_handler(CommandHandler("broadcast", admin_broadcast))
bot_app.add_handler(CommandHandler("lookup", admin_lookup))
bot_app.add_handler(CommandHandler("clearuser", admin_clearuser))
bot_app.add_handler(CommandHandler("forgetskill", forgetskill_command))

# Callbacks
bot_app.add_handler(CallbackQueryHandler(button_handler))

# Messages
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

# Errors
bot_app.add_error_handler(error_handler)


# ──────────────────────────── VERCEL SERVERLESS ENTRY ────────────────────────────

class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless function handler."""

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            if not body:
                self._respond(400, {"error": "Empty body"})
                return

            data = json.loads(body)
            
            update = Update.de_json(data, bot_app.bot)

            _process_error = None
            
            # Wrap process_update to capture any handler errors
            original_error_handler = None
            captured_error = []
            
            async def _capturing_error_handler(update_obj, context):
                captured_error.append(str(context.error))
                logger.error(f"Handler error: {context.error}", exc_info=True)
                if update_obj and isinstance(update_obj, Update) and update_obj.effective_chat:
                    try:
                        err_msg = str(context.error)[:300]
                        await update_obj.effective_chat.send_message(
                            f"⚠️ Error: {err_msg}"
                        )
                    except Exception:
                        pass
            
            loop = asyncio.new_event_loop()
            try:
                global _bot_initialized
                if not _bot_initialized:
                    loop.run_until_complete(bot_app.initialize())
                    _bot_initialized = True
                    logger.info("Bot app initialized for serverless")
                
                # Replace error handler temporarily to capture errors
                for key in list(bot_app.error_handlers.keys()):
                    original_error_handler = bot_app.error_handlers[key]
                    bot_app.error_handlers[key] = [_capturing_error_handler]
                
                loop.run_until_complete(bot_app.process_update(update))
            finally:
                # Restore original error handler
                if original_error_handler:
                    for key in list(bot_app.error_handlers.keys()):
                        bot_app.error_handlers[key] = original_error_handler
                loop.close()

            if captured_error:
                self._respond(200, {"status": "error", "error": captured_error[0]})
            else:
                self._respond(200, {"status": "ok"})

        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            self._respond(500, {"error": str(e)})

    def do_GET(self):
        """Health check endpoint."""
        self._respond(200, {
            "status": "healthy",
            "bot": "GODMODE-AI",
            "models": len(MODELS),
            "admins": len(ADMIN_IDS),
            "agent_enabled": AGENT_CONFIG.enabled,
            "soul": True,
            "skills_loaded": len(list_skills()),
            "learning_enabled": AGENT_CONFIG.learning_enabled,
            "native_function_calling": True,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def _respond(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # Suppress default server logs

# Vercel entrypoint alias
app = handler
