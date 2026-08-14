"""
Project GODMODE — Agent Core (OpenClaw/Hermes Architecture)

The agent loop follows the OpenClaw 5-step pattern with Hermes' learning loop:
1. ORCHESTRATE — single agent
2. RESOLVE MODEL — pick the right model, with fallback chain
3. BUILD PROMPT — assemble SOUL.md + IDENTITY + USER + MEMORY + Skills + Episodic + History
4. GUARD CONTEXT — token budget, auto-compaction, trim history
5. ACT & REPEAT — reason, call tool, observe, loop until done
6. LEARNING CHECKPOINT — reflect, extract patterns, create skills, persist memory

Task 6: Tightened should_use_agent() triggers — only tool-shaped phrasing
Task 7: Native function calling via OpenRouter's tools parameter (with text fallback)
Task 11: Request ID threaded through all logging for observability
"""

import json
import logging
import time
import hashlib
from typing import Dict, List, Optional, Tuple, Any

from utils.openrouter import send_message
from utils.config import DEFAULT_MODEL, get_model_label

logger = logging.getLogger(__name__)

# ──────────────────────────── AGENT CONFIG ────────────────────────────

MAX_ITERATIONS = 6
TIME_BUDGET = 45  # seconds (leave 15s buffer for Vercel 60s limit)
MIN_TOOLS_FOR_LEARNING = 2


def generate_request_id(chat_id: int) -> str:
    """Generate a short request ID for observability (Task 11)."""
    ts = str(int(time.time()))
    raw = f"{chat_id}:{ts}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


# ──────────────────────────── AGENT STATE ────────────────────────────

class AgentState:
    """Tracks execution state across the agent loop."""

    def __init__(self, user_message: str, history: List[Dict], model: str, request_id: str = ""):
        self.user_message = user_message
        self.history = history
        self.model = model
        self.request_id = request_id
        self.iteration = 0
        self.tool_results: List[Dict] = []
        self.final_answer: Optional[str] = None
        self.finished = False
        self.start_time = time.time()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.used_native_tools = False  # Track whether native function calling was used

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def time_remaining(self) -> float:
        return TIME_BUDGET - self.elapsed

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def add_tool_result(self, tool_name: str, args: Dict, result: Any) -> None:
        """Record a tool execution result with full details for the reflector."""
        self.tool_results.append({
            "tool": tool_name,
            "args": args,
            "result": str(result)[:2000],
            "iteration": self.iteration,
        })

    def build_observations_text(self) -> str:
        """Format all tool results as observations for the LLM (text fallback mode)."""
        if not self.tool_results:
            return ""
        lines = ["## Tool Results (Observations)", ""]
        for tr in self.tool_results:
            args_str = json.dumps(tr["args"])
            lines.append(f"[{tr['tool']}({args_str})] -> {tr['result'][:500]}")
        lines.append("\nContinue based on these results. Either call another tool or provide your final answer.")
        return "\n".join(lines)

    def build_tool_result_messages(self) -> List[Dict]:
        """
        Build tool result messages for native function calling mode.
        Each tool call result is a message with role 'tool'.
        """
        messages = []
        for tr in self.tool_results:
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{tr['iteration']}",
                "name": tr["tool"],
                "content": tr["result"][:2000],
            })
        return messages


# ──────────────────────────── AGENT ────────────────────────────

class Agent:
    """
    The core agent. Runs the OpenClaw/Hermes-style loop.
    Uses context.py for SOUL.md-anchored prompt assembly on every turn.
    Supports native function calling (Task 7) with text-parsed fallback.
    """

    def __init__(self, model: str = None, temperature: float = 0.5):
        self.model = model or DEFAULT_MODEL
        self.temperature = temperature

    def run(
        self,
        user_message: str,
        history: List[Dict],
        model: str = None,
        chat_id: int = 0,
        request_id: str = "",
        godmode: bool = False,
    ) -> Tuple[str, Dict]:
        """
        Execute the agent loop.
        Returns (final_answer, metadata) where metadata includes full tool_results.

        Task 7: Uses native function calling (OpenAI-compatible) as primary path.
        Falls back to text-parsed [TOOL_CALL] format for models that don't support it.
        """
        from utils.skills import (
            execute_skill,
            parse_tool_call,
            parse_native_tool_calls,
            build_tools_array,
            initialize_skills,
            find_skills_for_message,
        )
        from utils.context import build_context

        # Ensure skills are loaded
        initialize_skills()

        active_model = model or self.model

        # Generate request ID if not provided (Task 11)
        if not request_id:
            request_id = generate_request_id(chat_id)

        state = AgentState(user_message, history, active_model, request_id)

        # Build the tools array for native function calling (Task 7)
        tools_array = build_tools_array()
        state.used_native_tools = len(tools_array) > 0

        # Pre-match: find relevant skills for this message
        relevant_skills = find_skills_for_message(user_message)
        if relevant_skills:
            skill_names = [s.name for s in relevant_skills]
            logger.info(f"[{request_id}] Pre-matched skills: {skill_names}")

        logger.info(f"[{request_id}] Agent started: model={active_model}, msg={user_message[:80]}...")

        # ──── MAIN LOOP ────
        while not state.finished and state.iteration < MAX_ITERATIONS:
            state.iteration += 1

            # Time budget check
            if state.time_remaining < 5:
                logger.warning(f"[{request_id}] Agent time budget exceeded — forcing final answer")
                break

            # ──── STEP 3: BUILD PROMPT (SOUL.md-anchored) ────
            messages = build_context(
                chat_id=chat_id,
                history=state.history,
                user_message=state.user_message,
                include_skills=True,
                include_episodic=(state.iteration == 1),
                godmode=godmode,
            )

            # Add observations from previous tool calls
            if state.used_native_tools and state.tool_results:
                # Native mode: add tool result messages
                # We need to reconstruct the conversation with the assistant's tool_calls
                # and the tool results. For simplicity, we append them as user messages
                # with the observation text.
                obs_text = state.build_observations_text()
                if obs_text:
                    messages.append({"role": "user", "content": obs_text})
            else:
                # Text fallback mode: add observations as user message
                obs_text = state.build_observations_text()
                if obs_text:
                    messages.append({"role": "user", "content": obs_text})

            # ──── STEP 5: ACT & REPEAT ────
            try:
                # Send directly to OpenRouter API with our assembled messages
                from utils.openrouter import HEADERS, BASE_URL
                import requests as req

                payload = {
                    "model": active_model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": 4096,
                    "top_p": 0.95,
                }

                # Task 7: Include tools array for native function calling
                if state.used_native_tools and tools_array:
                    payload["tools"] = tools_array
                    payload["tool_choice"] = "auto"

                response_obj = req.post(
                    BASE_URL, headers=HEADERS, json=payload, timeout=50
                )
                response_obj.raise_for_status()
                data = response_obj.json()

                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]
                    response_msg = choice.get("message", {})
                    response = response_msg.get("content", "") or ""
                    usage = data.get("usage", {})

                    # Track token usage
                    state.total_prompt_tokens += usage.get("prompt_tokens", 0)
                    state.total_completion_tokens += usage.get("completion_tokens", 0)

                    # Task 7: Check for native tool calls first
                    native_calls = parse_native_tool_calls(response_msg)
                    if native_calls:
                        logger.info(f"[{request_id}] Native tool calls: {[c['tool'] for c in native_calls]}")
                        for tc in native_calls:
                            tool_name = tc["tool"]
                            tool_args = tc["args"]

                            logger.info(f"[{request_id}] Iteration {state.iteration}: calling {tool_name}({tool_args})")

                            try:
                                result = execute_skill(tool_name, tool_args)
                                state.add_tool_result(tool_name, tool_args, result)
                                logger.info(f"[{request_id}] Tool result: {str(result)[:200]}...")
                            except Exception as e:
                                error_msg = f"Tool '{tool_name}' failed: {str(e)}"
                                state.add_tool_result(tool_name, tool_args, error_msg)
                                logger.error(f"[{request_id}] {error_msg}")

                        # Loop back for next iteration
                        continue

                    # No native tool calls — try text-parsed fallback
                    if not response:
                        state.final_answer = "Agent received an empty response."
                        state.finished = True
                        break

                else:
                    state.final_answer = "Agent received an empty response."
                    state.finished = True
                    break

            except Exception as e:
                logger.error(f"[{request_id}] LLM call failed on iteration {state.iteration}: {e}")
                # Fallback to send_message with basic context
                try:
                    response, usage = send_message(
                        model=active_model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=4096,
                    )
                    state.total_prompt_tokens += (usage or {}).get("prompt_tokens", 0)
                    state.total_completion_tokens += (usage or {}).get("completion_tokens", 0)
                    state.used_native_tools = False  # Fallback doesn't support native tools
                except Exception as e2:
                    logger.error(f"[{request_id}] Fallback also failed: {e2}")
                    state.final_answer = f"Agent encountered an error: {str(e)[:200]}"
                    state.finished = True
                    break

            if not response or response.startswith("⚠️"):
                state.final_answer = response or "Agent failed to generate a response."
                state.finished = True
                break

            # Text-parsed tool call fallback (for models without native function calling)
            tool_call = parse_tool_call(response)

            if tool_call:
                # ACT: Execute the tool
                tool_name = tool_call.get("tool") or tool_call.get("skill")
                tool_args = tool_call.get("args", {})

                logger.info(f"[{request_id}] Iteration {state.iteration}: calling {tool_name}({tool_args}) [text mode]")

                try:
                    result = execute_skill(tool_name, tool_args)
                    state.add_tool_result(tool_name, tool_args, result)
                    logger.info(f"[{request_id}] Tool result: {str(result)[:200]}...")
                except Exception as e:
                    error_msg = f"Tool '{tool_name}' failed: {str(e)}"
                    state.add_tool_result(tool_name, tool_args, error_msg)
                    logger.error(f"[{request_id}] {error_msg}")

                # Loop back for next iteration (OBSERVE → THINK → ACT/ANSWER)
                continue
            else:
                # No tool call — this is the final answer
                state.final_answer = response
                state.finished = True
                break

        # ──── HANDLE ITERATION LIMIT ────
        if not state.finished:
            logger.warning(f"[{request_id}] Agent hit iteration limit ({MAX_ITERATIONS})")
            if state.tool_results:
                summary_prompt = (
                    f"You were working on: {user_message}\n\n"
                    f"You gathered these results:\n"
                    + "\n".join(f"- {tr['tool']}: {tr['result'][:500]}" for tr in state.tool_results)
                    + "\n\nProvide the best answer based on this information."
                )
                final, _ = send_message(
                    model=active_model,
                    messages=[{"role": "user", "content": summary_prompt}],
                    temperature=0.3,
                    max_tokens=4096,
                )
                state.final_answer = final or "Agent reached its reasoning limit. Try rephrasing."
            else:
                state.final_answer = "Agent reached its reasoning limit without using tools. Try rephrasing."

        metadata = {
            "iterations": state.iteration,
            "tools_used": [tr["tool"] for tr in state.tool_results],
            "tool_results": state.tool_results,  # Full details for the reflector
            "elapsed_seconds": round(state.elapsed, 2),
            "model": active_model,
            "agent_mode": True,
            "skills_matched": [s.name for s in relevant_skills] if relevant_skills else [],
            "request_id": request_id,
            "total_tokens": state.total_tokens,
            "prompt_tokens": state.total_prompt_tokens,
            "completion_tokens": state.total_completion_tokens,
            "used_native_tools": state.used_native_tools,
        }

        logger.info(
            f"[{request_id}] Agent finished: {metadata['iterations']} iters, "
            f"tools={metadata['tools_used']}, tokens={state.total_tokens}"
        )
        return state.final_answer, metadata


# ──────────────────────────── SMART ROUTER (Task 6 — tightened) ────────────────────────────

# Task 6: Tightened triggers — only tool-shaped phrasing, not loose keywords.
# Removed: "code", "plan", "compare", "analyze", "the current", "what's the"
# These were catching plain conversation that needs no tools.
AGENT_TRIGGERS = [
    # Explicit tool requests (verb + object pairs)
    "search for", "search the web", "look up", "google",
    "what is the weather", "weather in", "forecast",
    "calculate", "compute", "how much is", "math:",
    "translate to", "translate this",
    "fetch this url", "fetch url", "get this page",
    "summarize this", "summarize this article", "tl;dr",
    "run this code", "execute this code", "python code",
    "convert", "convert celsius", "convert fahrenheit",
    "what time is it", "time in",
    # Research/investigation with tool-shaped phrasing
    "research this topic", "investigate this",
    "find information about",
    "current price of", "stock price",
    # Explicit agent/step-by-step requests
    "step by step analysis", "help me decide with data",
    "break down this problem",
]


def should_use_agent(message: str) -> bool:
    """
    Determine if a message should be handled by the agent loop.
    Heuristic-based for speed — checks tool-shaped phrasing, URLs, math, code blocks.

    Task 6: Tightened to avoid false positives on plain conversation.
    """
    msg_lower = message.lower().strip()

    # Direct triggers (tool-shaped phrasing only)
    for trigger in AGENT_TRIGGERS:
        if trigger in msg_lower:
            return True

    # URLs — might want to fetch
    if "http://" in msg_lower or "https://" in msg_lower:
        return True

    # Math expressions (more specific — requires an operator between numbers)
    import re
    if re.search(r'\d+\s*[+\-*/^]\s*\d+', message):
        return True

    # Code execution requests (must have actual code blocks, not just the word "code")
    if "```" in message:
        return True

    # Explicit "run/execute/eval" prefix (not just the word appearing anywhere)
    if msg_lower.startswith(("run ", "execute ", "eval ")):
        return True

    # Check if any skill triggers match
    try:
        from utils.skills import find_skills_for_message, initialize_skills
        initialize_skills()
        if find_skills_for_message(message):
            return True
    except Exception:
        pass

    return False
