# Customer Support Resolution Agent — Claude Agent SDK

Production-grade customer support agent built with the Claude Agent SDK (Python). Handles returns, billing disputes, account issues, and escalations for "TechGear," a fictional electronics company. Features 4 custom MCP tools, programmatic hook-based business rule enforcement, and structured error handling.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      src/agent.py                           │
│              ClaudeSDKClient (Agentic Loop)                 │
│          max_turns: 20 | budget: $0.50 | medium             │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                 src/hooks.py                           │  │
│  │                                                       │  │
│  │  PreToolUse                  PostToolUse               │  │
│  │  ├─ Prerequisite chain       ├─ Session state tracking │  │
│  │  ├─ $500 refund cap          ├─ Low-satisfaction alert │  │
│  │  └─ 3-refund session limit   └─ Audit logging         │  │
│  └──────────────────────┬────────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼────────────────────────────────┐  │
│  │           src/tools.py (In-Process MCP Server)        │  │
│  │                                                       │  │
│  │  get_customer    lookup_order                         │  │
│  │  process_refund  escalate_to_human                    │  │
│  └──────────────────────┬────────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼────────────────────────────────┐  │
│  │       src/mock_data.py (Faker + JSON DB)              │  │
│  │       50 customers | ~160 orders | seed 42            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key design decision**: Business rules are enforced via deterministic Python hooks, not via LLM prompting. The model cannot bypass prerequisite checks, refund caps, or session limits. Hooks execute before and after every tool call regardless of what the model attempts — if a prerequisite isn't met, the hook returns `{"decision": "block"}` and the tool call never executes.

## Custom MCP Tools

All four tools are registered as an in-process MCP server using `@tool` decorator + `create_sdk_mcp_server()`. Each tool returns structured error responses with `errorCategory`, `isRetryable`, and `suggestedAction` so the agent can make informed recovery decisions rather than guessing.

### `get_customer`
Looks up a customer by ID (`CUST-XXXX` format). Returns profile data including name, email, plan tier, account status, and satisfaction score. Flags suspended accounts with a warning directing the agent to escalate.

- **Errors**: Invalid ID format → `validation` | Customer not found → `not_found`
- **Edge cases**: Suspended accounts return success with a `warning` field — the agent sees the data but is told to escalate

### `lookup_order`
Retrieves orders by order ID (`ORD-XXXXX`) or customer ID (`CUST-XXXX`). Returns items, total amount, delivery status, and a `return_eligible` flag that is `true` only for delivered orders within the 30-day return window.

- **Errors**: Invalid format → `validation` | Not found → `not_found`
- **Edge cases**: `shipped`, `processing`, `cancelled`, and `returned` orders are never return-eligible

### `process_refund`
Processes a refund for a delivered, eligible order. Validates status, return window, and amount. Logs the refund with a unique ID to the database.

- **Errors**: Format → `validation` | Missing → `not_found` | Wrong status, expired window, or amount over $500 → `business_rule`
- **Edge cases**: Empty reason rejected, non-delivered orders rejected, amounts over $500 rejected with guidance to escalate instead

### `escalate_to_human`
Escalates an issue to a human agent with priority level and context summary. Used for refunds over $500, suspended accounts, frustrated customers, or anything outside automated scope.

- **Priority levels**: `low` (general questions), `medium` (billing disputes), `high` (large refunds, angry customers), `critical` (account security)
- **Errors**: Invalid priority or customer ID format → `validation`

## Hook-Based Business Rules

### PreToolUse (blocks tool execution when rules are violated)

| Rule | What Happens |
|------|-------------|
| Customer verification required | `lookup_order` is blocked if `get_customer` hasn't been called yet |
| Customer + order verification required | `process_refund` is blocked if either `get_customer` or `lookup_order` hasn't been called |
| $500 refund cap | `process_refund` is blocked for orders over $500 — the hook reads the order amount directly from the DB and forces escalation |
| Session refund limit | After 3 successful refunds in a session, further `process_refund` calls are blocked |

### PostToolUse (tracks state and injects context after execution)

| Behavior | How It Works |
|----------|-------------|
| Session state tracking | Sets `customer_verified` / `order_looked_up` flags on success, increments `refund_count` after each refund — error results are ignored |
| Low-satisfaction alert | When `get_customer` returns a satisfaction score below 2.0, injects a system message telling the agent to use extra empathy and consider proactive compensation |
| Audit logging | Every tool call is logged with timestamp, tool name, and success/error status |

These are Python functions registered via `HookMatcher`. They are not suggestions to the model — they are code that runs unconditionally. The prerequisite chain, refund cap, and session limit cannot be prompt-injected away.

## Skills Demonstrated

- **Agentic loop orchestration** — `ClaudeSDKClient` with `allowed_tools`, `permission_mode: bypassPermissions`, turn limits, and budget constraints
- **Custom MCP tool design** — In-process server via `create_sdk_mcp_server()`, typed input schemas, descriptive tool descriptions with edge case documentation
- **Programmatic enforcement via hooks** — `PreToolUse` for blocking, `PostToolUse` for state tracking and context injection, registered with `HookMatcher` regex patterns
- **Structured error propagation** — Every tool error includes category, retryability, and a suggested next action for the agent
- **Context management** — `CLAUDE.md` with workflow instructions, `system_prompt` for agent persona, budget and turn limits as hard stops
- **Session state management** — Module-level `SessionState` class tracks prerequisites and limits across tool calls within a single agent run
- **System message injection** — Hooks dynamically inject `systemMessage` to steer agent behavior based on runtime data

## Tech Stack

- **Claude Agent SDK** (`claude-code-sdk`) — Agent loop, tool registration, hook system
- **Anthropic API** — LLM backing the agent
- **Faker** — Reproducible mock data generation (seed 42)
- **Pydantic** — Data validation models
- **python-dotenv** — Environment variable management

## Setup & Run

```bash
git clone https://github.com/mufibra23/customer-support-agent.git
cd customer-support-agent
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

python scripts/generate_data.py
```

### Run the agent

```bash
# Interactive mode (multi-turn conversation)
python -m src.agent

# Single query mode
python -m src.agent -q "I'm customer CUST-0001 and I need a refund on my last order"
```

### Run tests

```bash
python -m pytest tests/test_tools.py tests/test_hooks.py -v
```

## Test Results

```
tests/test_tools.py    — 21 passed
tests/test_hooks.py    — 16 passed
───────────────────────────────
Total                  — 37 passed in ~1s
```

Tool tests cover valid inputs, invalid ID formats, not-found cases, ineligible refunds, non-delivered orders, empty required fields, all escalation priority levels, and suspended account warnings. Hook tests cover prerequisite blocking and allowing, $500 cap enforcement, session limit enforcement, state tracking on success vs. error, low-satisfaction alert injection, and audit log creation.

## Project Structure

```
customer-support-agent/
├── CLAUDE.md                  # Agent persona and workflow instructions
├── requirements.txt
├── .env.example
├── data/
│   └── mock_db.json           # Generated at runtime (not committed)
├── src/
│   ├── agent.py               # ClaudeSDKClient runner (interactive + CLI)
│   ├── tools.py               # 4 MCP tools + in-process server
│   ├── hooks.py               # PreToolUse + PostToolUse + SessionState
│   ├── mock_data.py           # JSON DB loader/writer
│   └── models.py              # Pydantic data models
├── tests/
│   ├── test_tools.py          # 21 tool unit tests
│   ├── test_hooks.py          # 16 hook enforcement tests
│   └── test_scenarios.py      # Example prompts for manual testing
└── scripts/
    └── generate_data.py       # Faker data generator (seed 42)
```
