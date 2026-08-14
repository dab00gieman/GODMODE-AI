# GODMODE-AI

> Multi-model AI Telegram bot with OpenClaw/Hermes-style agentic architecture.

## Architecture

GODMODE-AI implements a 4-layer agentic framework inspired by OpenClaw (the gateway) and Hermes (the self-improving learner).

### The 4 Layers

| Layer | Responsibility | Implementation |
|-------|---------------|----------------|
| **Gateway** | Webhook handling, routing, auth | `api/webhook.py` |
| **Execution** | Agent loop, tool dispatch, concurrency | `utils/agent.py` |
| **Integration** | Skill registry, SKILL.md parsing, native function calling | `utils/skills.py` |
| **Intelligence** | SOUL.md, memory, learning loop | `soul/`, `utils/context.py`, `utils/reflector.py` |

### SOUL.md — The Cognitive Anchor

`soul/SOUL.md` defines the agent's personality, values, boundaries, and communication style.
It is injected into the system prompt at the start of EVERY conversation — just like OpenClaw.
It survives context compaction and is the behavioral anchor across all sessions.

### Skills System

Each skill is a folder containing:
- `SKILL.md` — YAML frontmatter (name, description, triggers, arguments) + natural language instructions
- `run.py` — the executable function

Skills are auto-discovered from `skills/` on startup and injected into the system prompt.
The LLM sees both the tool descriptions and full instructions — Hermes-style injection.

**Native Function Calling:** Skills are also exposed as OpenAI-compatible `tools` in the API
request payload, so models that support function calling can invoke them natively (no text parsing).
A text-parsed `[TOOL_CALL]` fallback remains for models without function calling support.

**Bundled Skills (10):**
| Skill | Description | External API |
|-------|-------------|-------------|
| `web_search` | Search via DuckDuckGo | DuckDuckGo (free) |
| `calculator` | Math expression evaluator | None (local) |
| `code_runner` | Safe Python evaluation (AST-whitelisted) | None (local) |
| `summarize` | Extractive text summarization | None (local) |
| `weather` | Weather + forecast | wttr.in (free) |
| `fetch_url` | Web page content extractor | Direct HTTP |
| `get_time` | Time in any timezone | None (local) |
| `translate` | Language translation | Google Translate (free) |
| `memory_search` | Search MEMORY.md + episodic | Firestore |
| `episodic_recall` | Recall past interactions (semantic) | Firestore |

### The Agent Loop (OpenClaw Pattern)

```
1. ORCHESTRATE    — single agent (multi-agent is future)
2. RESOLVE MODEL  — pick model with fallback chain
3. BUILD PROMPT   — SOUL.md + IDENTITY + USER + MEMORY + Skills + Episodic + History
4. GUARD CONTEXT  — token budgeting, auto-trim history
5. ACT & REPEAT   — reason, call tool (native or text-parsed), observe, loop until done
6. LEARN          — reflect, extract patterns, create skills, persist memory
```

### The Learning Loop (Hermes Pattern)

After completing a complex multi-step task (2+ tools used), the agent enters a **Reflective Phase**:
1. Analyzes what tools were used and in what order
2. Determines if there's a reusable pattern
3. If yes: writes a new learned skill to Firestore (SKILL.md format)
4. Consolidates the interaction into MEMORY.md

Next time a similar task arrives, the agent uses the learned skill instead of reasoning from scratch.

### Memory System

Three layers — same architecture as both OpenClaw and Hermes:

| Layer | What | Where |
|-------|------|-------|
| **Session** | Current conversation context | Context window (auto-trimmed) |
| **Long-term** | Curated facts, preferences | `MEMORY.md` in Firestore |
| **Episodic** | Searchable interaction history (semantic search) | Firestore (embedding-based cosine similarity) |

## File Structure

```
api/
  webhook.py              # Gateway — webhook handler, command routing, request ID observability

soul/
  SOUL.md                 # Personality, values, boundaries (injected every turn)
  IDENTITY.md             # Name, avatar, version
  USER.md                 # User profile template

skills/
  web_search/             # SKILL.md + run.py
  calculator/             # SKILL.md + run.py
  code_runner/            # SKILL.md + run.py (AST-whitelisted safe evaluator)
  weather/                # SKILL.md + run.py
  translate/              # SKILL.md + run.py
  fetch_url/              # SKILL.md + run.py
  time_tools/             # SKILL.md + run.py
  summarize/              # SKILL.md + run.py
  memory_search/          # SKILL.md + run.py
  episodic_recall/        # SKILL.md + run.py

utils/
  agent.py                # Agent loop (native function calling, request ID, smart routing)
  skills.py               # Skill registry, SKILL.md parser, auto-discovery, tool spec generation
  context.py              # Context builder (SOUL + MEMORY + Skills + History + token budgeting)
  reflector.py            # Learning loop (reflection → skill creation → memory consolidation)
  config.py               # Model catalog, env vars, agent config
  openrouter.py           # OpenRouter API client with fallback chains
  memory.py               # Firestore session management, prefs, stats, rate limiting, semantic episodic search
  formatter.py             # Telegram message formatting
  admin.py                # Admin commands and panel

tests/
  test_tool_call_parsing.py    # Unit tests for parse_tool_call() and native tool call parsing
  test_skill_matching.py       # Unit tests for find_skills_for_message() trigger matching
  test_should_use_agent.py     # Unit tests for should_use_agent() routing decisions
  test_reflector.py            # Unit tests for reflect_on_task() with mocked send_message()
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize bot & select engine |
| `/model` | Change AI engine |
| `/models` | List all engines |
| `/status` | Current engine, history, usage |
| `/agent` | Toggle agentic mode on/off |
| `/tools` | List all available skills |
| `/memory` | View long-term MEMORY.md |
| `/skills` | List bundled + learned skills |
| `/forgetskill` | Admin: remove a learned skill by name |
| `/clear` | Wipe conversation history |
| `/help` | Full help guide |
| `/settemp` | Set creativity (0.0-2.0) |
| `/settokens` | Set max response length |
| `/setmodel` | Quick model switch |
| `/reset` | Reset settings to defaults |

## Adding Custom Skills

1. Create `skills/my_skill/` directory
2. Write `SKILL.md` with YAML frontmatter
3. Write `run.py` with a `run()` function
4. Restart — it auto-registers

```yaml
# skills/my_skill/SKILL.md
---
name: my_skill
description: What this skill does
triggers:
  - trigger phrase 1
  - trigger phrase 2
arguments:
  - name: input
    type: string
    required: true
    description: What this argument is
---

# My Skill

Instructions for the LLM on how to use this skill.
```

```python
# skills/my_skill/run.py
def run(input: str) -> str:
    return f"Result: {input}"
```

## Setup

### Prerequisites
- Telegram bot token (from @BotFather)
- OpenRouter API key (from openrouter.ai)
- Firebase project with Firestore enabled (free tier works)
- Your Telegram user ID (from @userinfobot)

### Deploy to Vercel

```bash
npm i -g vercel
vercel

# Set environment variables
vercel env add OPENROUTER_API_KEY
vercel env add TELEGRAM_BOT_TOKEN
vercel env add FIREBASE_PROJECT_ID
vercel env add FIREBASE_CLIENT_EMAIL
vercel env add FIREBASE_PRIVATE_KEY
vercel env add ADMIN_IDS

vercel --prod
```

### Set Webhook

```bash
curl -s "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=https://YOUR_VERCEL_URL/webhook"
```

## Tech Stack

- **Runtime:** Python 3.12 on Vercel Serverless
- **Bot Framework:** python-telegram-bot 21.6
- **AI API:** OpenRouter (native function calling support)
- **Memory:** Firebase Firestore — session, long-term, episodic (semantic search)
- **Agent Pattern:** OpenClaw (gateway) + Hermes (learning loop)
- **Skills:** SKILL.md format with auto-discovery + OpenAI-compatible tool specs
- **Identity:** SOUL.md cognitive anchor
- **Security:** AST-whitelisted code execution (no exec()/eval())
- **Observability:** Request ID threading across all agent iterations
- **Tools:** DuckDuckGo, wttr.in, Google Translate (all free APIs)

## License

MIT
