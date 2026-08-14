\# LISA — Omega Prompt v3: Real Code Execution, File Management, and Closing the Loose Wires

Paste into Claude Code inside the repo root. This assumes omega v1 and v2 are largely done — verified: access control gates `chat\_handler`, ClawHub has a working command, request-ID tracing exists, `code\_runner` uses real AST whitelisting (not string-blocklisting). This pass has three parts: wire five modules that were built but never connected, then the two capabilities you actually asked for — real code execution and file management — designed around what Vercel serverless can and can't do, then a short list of other agent-zero patterns worth stealing.

\---

\## PART A — Wire the five orphaned modules

Same failure mode as before, smaller scale: these files are substantial (146–200 lines each, no `TODO`/`NotImplementedError` stubs — they're written) but nothing outside their own file imports them.

\### Task 1 — `utils/permissions.py`

Not referenced anywhere. Given `utils/capabilities.py` already defines `permissions: list[str]` on every `Capability` and a `risk\_level`/`trust\_level` model, this file almost certainly implements the enforcement layer for that — check what it exports (likely something like `check\_permission(user\_id, capability)` or similar) and call it from wherever `Agent.run()` or `execute\_skill()` actually invokes a capability's `execution\_fn`, gated on the capability's declared `permissions` and the calling user's `get\_permission\_level()` (already imported from `utils.access` in `webhook.py`). This is the connective tissue between "we modeled risk levels" and "we actually enforce them" — right now nothing stops a low-permission user from triggering a `risk\_level=critical` capability.

\### Task 2 — `utils/planner.py`

Not referenced anywhere. Check whether this is meant to sit in front of `Agent.run()` — i.e., for a complex multi-step request, produce a plan (ordered sub-goals) before the ReAct loop starts iterating blindly. If so, wire it into `agent.py`: when `should\_use\_agent()` fires and the message looks multi-step (reuse/extend the same heuristic style as `should\_use\_agent`, or check iteration count needed historically for similar requests via episodic memory), call the planner first and feed its plan into the agent's initial context instead of just the raw user message.

\### Task 3 — `utils/parallel.py`

Not referenced anywhere. If this implements concurrent tool execution (running independent tool calls in the same iteration simultaneously rather than sequentially), wire it into `Agent.run()`'s tool-execution step: when the model requests multiple tool calls in one turn that don't depend on each other's output, dispatch them concurrently instead of one at a time. Check its actual function signature before assuming this — confirm what it does rather than guessing from the filename.

\### Task 4 — `utils/mcp.py`

Not referenced anywhere, and only 102 lines — likely a thin client/registration stub rather than a full implementation. This is your Model Context Protocol integration (letting Lisa call external MCP servers as tools, the same protocol Claude and other agents use for tool interop). Decide whether this is worth finishing now or deferring — if you want it live, it needs: a way to register MCP server endpoints (env var or Firestore-backed config), a client that lists and calls their tools, and a bridge that surfaces those tools through the same `Skill`/capability interface everything else uses so the agent doesn't need special-case logic for MCP vs. bundled vs. ClawHub tools.

\### Task 5 — `utils/clawhub\_adapter.py`

Not referenced anywhere — but `utils/clawhub.py` (477 lines, wired into `webhook.py`'s `/clawhub` command) presumably needs to translate whatever format ClawHub returns into Lisa's internal `Skill`/`Capability` shape. Check whether `clawhub.py` is already doing that translation inline, or whether it's supposed to delegate to `clawhub\_adapter.py` and currently doesn't. If the adapter logic is duplicated inside `clawhub.py` instead of using the dedicated adapter file, consolidate it into `clawhub\_adapter.py` and have `clawhub.py` call it — don't maintain two places that both know how to parse a ClawHub skill manifest.

\*\*Verify (all of Part A):\*\* `grep -rn "utils\.<module>" api/ utils/` for each of the five should return at least one call site outside the module's own file when you're done.

\---

\## PART B — Real code execution (not just AST-sandboxed math)

\### Task 6 — Understand why you can't just copy agent-zero's approach, and what the adapted version looks like

agent-zero runs code by opening a \*\*persistent interactive shell session inside an isolated Docker container\*\*, reached over SSH from the main process (`plugins/\_code\_execution/tools/code\_execution\_tool.py` → `SSHInteractiveSession`/`LocalInteractiveSession`). Sessions persist across multiple tool calls in a conversation — the agent can run a command, check on long-running output later, reset the session, all against the same live shell. That's how it gets real Python/Node/bash execution safely: the isolation boundary is the container and network, not string/AST filtering.

\*\*Lisa can't host that directly.\*\* Vercel serverless functions are stateless, ephemeral, and `vercel.json` currently caps `api/webhook.py` at `maxDuration: 60` — there's no persistent process to hold a shell session open between messages, and no Docker host to isolate it in even if there were.

\*\*The adapted design — use Vercel Sandbox, not a third-party provider:\*\*

Vercel has a first-party product for exactly this: \*\*Vercel Sandbox\*\* (`@vercel/sandbox` — Python and JS/TS SDKs both exist), isolated Firecracker microVMs purpose-built to run untrusted or AI-generated code. This is a better fit than a generic external sandbox API because it's on the same platform Lisa already deploys to — auth happens automatically via Vercel OIDC tokens in production, no separate API key/credential to manage for the execution layer itself.

- \*\*Persistence is built in, without you hosting a container.\*\* Sandboxes snapshot their filesystem on stop and restore it on resume — this is the direct equivalent of agent-zero's long-lived shell session, and it can double as the workspace from Task 7 (the sandbox's own filesystem can \*be\* the per-chat working directory, rather than maintaining a fully separate Firebase Storage workspace — see Task 7's note on this).
- \*\*Real Linux, not a restricted interpreter\*\* — Amazon Linux 2023 by default, sudo, package installs via `dnf`, network egress you can control per-sandbox, Docker-in-sandbox if ever needed.
- \*\*Duration limits differ by plan and the exact ceiling for Pro/Enterprise varies across Vercel's own docs (seen both 5-hour and 24-hour figures)\*\* — confirm the current number in your dashboard before relying on it for long jobs. Hobby tier: 45 minute sandbox max, 5 minute default (set via the `timeout` option on `Sandbox.create()`).
- \*\*This does not raise Lisa's own 60s function limit.\*\* The sandbox can run far longer than Lisa's webhook function is allowed to. That means `execute\_code` must be async by design: `chat\_handler` creates/resumes the sandbox, kicks off the command, and returns immediately with something like "Running that now, I'll follow up" — it cannot block waiting for a long job to finish. A separate mechanism (this is now a hard dependency on Task 10's background-task/scheduler work, not an optional nice-to-have) polls or gets notified when the sandbox command completes, then pushes the result back to the user via the Telegram Bot API directly, outside the normal webhook request/response cycle. Short, fast commands (well under Lisa's own function timeout, leaving real margin) can still run synchronously within `chat\_handler` — only long-running jobs need the async path.
- Add a new skill, `execute\_code` (distinct from the existing `code\_runner`, which stays as-is for fast in-process math/expressions — don't replace it, these serve different purposes and the AST-sandboxed one is strictly safer for the common case). `execute\_code` creates or resumes the chat's sandbox (one per `chat\_id`, tracked in Firestore — sandbox ID, last-used timestamp), runs the command via the SDK, and returns stdout/stderr/exit code (synchronously if fast, via the async path above if not). Register it in `utils/capabilities.py` with `risk\_level=critical` and real `permissions` required, enforced via Task 1's fix — this is genuinely the most dangerous capability in the whole skill set.
- Support Python and shell at minimum (matches agent-zero's `python`/`terminal` runtimes and Vercel Sandbox's own supported runtimes) — Node.js is available too if worth adding alongside.

\*\*Verify:\*\* Send an admin-authorized request that needs real code ("write and run a script that reads a CSV and computes column averages"), confirm it executes inside an actual Vercel Sandbox instance (check the sandbox in your Vercel dashboard, not just Lisa's own logs), confirm a non-admin/unauthorized-for-this-capability user is blocked by Task 1's permission check before any sandbox is even created, and confirm a deliberately long-running command (sleep + a slow loop) correctly takes the async path instead of timing out Lisa's own function.

\---

\## PART C — File management (Lisa's equivalent of agent-zero's `work\_dir`)

\### Task 7 — Pick the storage backend and build the workspace model

agent-zero's file APIs (`get\_work\_dir\_files`, `upload\_work\_dir\_files`, `edit\_work\_dir\_file`, `delete\_work\_dir\_file`, `rename\_work\_dir\_file`, `extract\_work\_dir\_archive`, `download\_work\_dir\_file`) all operate on a per-project directory on the container's actual filesystem. Lisa has no persistent filesystem to mirror that onto directly (Vercel functions get a fresh, empty, throwaway filesystem per invocation) — so the workspace needs to live somewhere durable.

\*\*Fix — now that Task 6 brings Vercel Sandbox into the picture, there are two reasonable designs; pick one deliberately rather than building both by accident:\*\*

- \*\*Option 1 (simpler, recommended if `execute\_code` from Task 6 is being built anyway):\*\* Use each chat's Vercel Sandbox filesystem itself as the workspace. Since sandboxes persist across stop/resume, files written in one turn are still there in the next. File-management skills (Task 8) then just call the same Sandbox SDK's file read/write/list methods instead of a separate storage API — one system instead of two, and code execution and file management are trivially consistent with each other since they're literally the same filesystem.
- \*\*Option 2 (needed regardless, for the Telegram bridge):\*\* Even with Option 1, you still want \*\*Firebase Storage\*\* as the landing zone for files coming in/out of Telegram (Task 9) — a user's uploaded document needs somewhere to live before/independent of whether a sandbox happens to exist for that chat, and it's a simpler place to keep outputs you want to persist long-term or serve back as a direct download link. Model it as one storage prefix per chat, `workspaces/{chat\_id}/...`.

A reasonable combined design: Firebase Storage is the durable inbox/outbox (Telegram ↔ Lisa), and the Sandbox filesystem is the working area code actually operates on — with `execute\_code` and `write\_file`/`read\_file` syncing between the two only when a file needs to cross that boundary (e.g. copy an uploaded file into the sandbox before running a script against it, copy a generated output back out to send to the user). Don't build a fully independent third storage layer beyond these two.

\### Task 8 — Build the file-management skill(s)

Add a new skill (or small family of skills, following the existing `skills/<name>/SKILL.md` + `run.py` pattern) covering the core operations the agent needs to reason about files mid-task:

- `list\_files` — list what's in the current chat's workspace.
- `read\_file` — read a file's content (text files inline; for anything binary/large, return metadata + a signed download URL rather than trying to inline it into the LLM context).
- `write\_file` — create or overwrite a file (this is what makes `execute\_code` from Task 6 actually useful together with this — a script can read input files and write output files that persist for the next turn).
- `delete\_file` — remove a file.
- Optionally `rename\_file` if the agent's workflows need it — don't build this speculatively if nothing calls for it yet.

Register all of these in `utils/capabilities.py` too, with `risk\_level=medium` (file writes/deletes are lower stakes than arbitrary code execution but still real user data) and appropriate `permissions`.

\### Task 9 — Wire Telegram's native file support into the same workspace

Telegram already lets users send/receive files directly — use that as the human-facing side of the same workspace instead of building a separate upload mechanism. Add a message handler for `filters.Document` (and `filters.PHOTO` if relevant) that, on receipt, downloads the file via the Bot API and writes it into that chat's `workspaces/{chat\_id}/` prefix in Firebase Storage — so a user can drop a file into the chat and the agent can immediately reference it via `read\_file`/`list\_files` in the same conversation. Symmetrically, when `write\_file` produces something the user should see (not just an intermediate working file), send it back via `update.message.reply\_document()`.

\*\*Verify (Tasks 7–9 together):\*\* Send a file to the bot via Telegram, ask the agent to do something with it (e.g. "summarize this CSV" via `execute\_code` reading it from the workspace), confirm the result is generated by real code touching the actual uploaded file, and confirm the workspace persists — sending a follow-up message in the same chat later should still see files from an earlier turn.

\---

\## PART D — Other agent-zero patterns worth taking, once B and C are stable

Don't start these until Parts A–C are working — they build on the workspace/execution foundation those establish.

\### Task 10 — Background/scheduled tasks

agent-zero has a full scheduler (`scheduler\_task\_create`, `scheduler\_tick`, etc.) for recurring or delayed work. Lisa currently has nothing like this — every action happens synchronously inside a single Telegram message's request/response cycle, which is a real limitation given Vercel's 60s cap (a long code-execution job or a "check on this every hour" request has nowhere to live). If this matters for how you're using Lisa, it needs an external trigger (a separate scheduled Vercel Cron job, or a lightweight worker on whatever service hosts Task 6's sandbox) that wakes up, checks Firestore for due tasks, executes them, and pushes results back to the user via the Telegram Bot API directly (not through the normal webhook request/response, since there's no live request to respond to at that point).

\### Task 11 — Confirm subagent delegation is actually good, not just wired

`utils/subagent\_manager.py` (248 lines) is referenced by `webhook.py`, unlike the five orphans in Part A — but "referenced" isn't the same as "matches agent-zero's model." agent-zero's `call\_subordinate` tool lets an agent spawn a subordinate with a narrower role/prompt and get a synthesized result back, with a clear hierarchy. Read through `subagent\_manager.py` and confirm it does the equivalent (spawn → scoped context → synthesized return → depth limit to avoid runaway delegation chains) rather than just being a registry that isn't actually invoked mid-loop. This was flagged as a "build later" item in omega v1's Task 9 — if it's already substantially there, this task is just verification; if it's a stub with real-looking code that never actually gets called from `agent.py`'s iteration loop, that's the same disconnected-module problem as Part A applied to a sixth file.

\---

\## Do-last checklist

1. All five Part A modules have a real call site outside their own file.
1. `execute\_code` runs real Python/shell against an external sandbox, is gated by enforced permissions (not just declared risk levels sitting unused in the registry), and is clearly separate from the still-in-process `code\_runner`.
1. A file sent via Telegram is retrievable by the agent in the same or a later turn in the same chat, and a file the agent writes can be sent back to the user.
1. `execute\_code` and the file skills both show up correctly in `/tools` / `/skills` / wherever the capability registry surfaces what's available, with accurate risk levels.
1. Test an unauthorized-for-code-exec user (if your permission model supports tiered access, not just admin/not-admin) and confirm they're blocked before reaching the sandbox — this is the one place in the whole system where a permission-check bug has real consequences.
