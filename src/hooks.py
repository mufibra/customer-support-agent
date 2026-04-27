"""PreToolUse and PostToolUse hooks for business rule enforcement."""

import json
from datetime import datetime
from typing import Any

from claude_code_sdk import HookMatcher
from claude_code_sdk.types import HookContext, HookJSONOutput


# ---------------------------------------------------------------------------
# Session state — tracks what has been verified in this session
# ---------------------------------------------------------------------------
class SessionState:
    """Track tool call prerequisites and session limits."""

    def __init__(self):
        self.customer_verified: bool = False
        self.order_looked_up: bool = False
        self.verified_customer_id: str | None = None
        self.refund_count: int = 0
        self.max_refunds: int = 3
        self.audit_log: list[dict] = []

    def reset(self):
        self.__init__()


# Module-level session state (shared across hooks in a single agent run)
session = SessionState()


def get_session() -> SessionState:
    return session


def reset_session():
    session.reset()


# ---------------------------------------------------------------------------
# PreToolUse hook
# ---------------------------------------------------------------------------
async def pre_tool_use_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> HookJSONOutput:
    """Enforce prerequisite chains and business rules before tool execution."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Strip MCP server prefix for matching
    short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name

    # Rule: lookup_order requires get_customer first
    if short_name == "lookup_order":
        if not session.customer_verified:
            return {
                "decision": "block",
                "systemMessage": (
                    "BLOCKED: You must call get_customer before lookup_order. "
                    "Ask the customer for their ID first."
                ),
            }

    # Rule: process_refund requires get_customer AND lookup_order first
    if short_name == "process_refund":
        if not session.customer_verified:
            return {
                "decision": "block",
                "systemMessage": (
                    "BLOCKED: You must call get_customer before process_refund. "
                    "Verify the customer first."
                ),
            }
        if not session.order_looked_up:
            return {
                "decision": "block",
                "systemMessage": (
                    "BLOCKED: You must call lookup_order before process_refund. "
                    "Look up the order details first."
                ),
            }

        # Rule: Block refunds > $500 → force escalation
        order_id = tool_input.get("order_id", "")
        from src.mock_data import get_order

        order = get_order(order_id)
        if order and order.get("total_amount", 0) > 500:
            return {
                "decision": "block",
                "systemMessage": (
                    f"BLOCKED: Refund amount ${order['total_amount']:.2f} exceeds $500 limit. "
                    "You must use escalate_to_human with high priority instead."
                ),
            }

        # Rule: Max 3 refunds per session
        if session.refund_count >= session.max_refunds:
            return {
                "decision": "block",
                "systemMessage": (
                    f"BLOCKED: Maximum {session.max_refunds} refunds per session reached. "
                    "Escalate further refund requests to a human agent."
                ),
            }

    return {}


# ---------------------------------------------------------------------------
# PostToolUse hook
# ---------------------------------------------------------------------------
async def post_tool_use_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> HookJSONOutput:
    """Track session state, inject alerts, and audit log after tool execution."""
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_result = input_data.get("tool_result", "")

    short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
    timestamp = datetime.now().isoformat()

    # Parse tool result if it's JSON text
    result_data = {}
    if isinstance(tool_result, str):
        try:
            result_data = json.loads(tool_result)
        except (json.JSONDecodeError, TypeError):
            pass

    is_error = "error" in result_data

    # Audit logging
    audit_entry = {
        "timestamp": timestamp,
        "tool": short_name,
        "status": "error" if is_error else "success",
        "input": tool_input,
    }
    session.audit_log.append(audit_entry)
    print(f"[AUDIT] {timestamp} | {short_name} | {'ERROR' if is_error else 'OK'}")

    # Track state on success
    system_message = None

    if short_name == "get_customer" and not is_error:
        session.customer_verified = True
        session.verified_customer_id = tool_input.get("customer_id")

        # Check satisfaction score for low-satisfaction alert
        satisfaction = result_data.get("satisfaction_score", 5.0)
        if satisfaction < 2.0:
            system_message = (
                "⚠ LOW SATISFACTION ALERT: This customer has a satisfaction score of "
                f"{satisfaction}/5.0. Use extra empathy and consider proactive compensation. "
                "If they are an enterprise customer, escalate immediately."
            )

    elif short_name == "lookup_order" and not is_error:
        session.order_looked_up = True

    elif short_name == "process_refund" and not is_error:
        session.refund_count += 1
        remaining = session.max_refunds - session.refund_count
        if remaining <= 1:
            system_message = (
                f"Refund session limit warning: {remaining} refund(s) remaining in this session."
            )

    if system_message:
        return {"systemMessage": system_message}

    return {}


# ---------------------------------------------------------------------------
# Hook matchers for agent registration
# ---------------------------------------------------------------------------
def get_hook_matchers() -> dict[str, list[HookMatcher]]:
    """Return hook matchers configured for the support tools."""
    return {
        "PreToolUse": [
            HookMatcher(
                matcher="mcp__customer-support__",
                hooks=[pre_tool_use_hook],
            ),
        ],
        "PostToolUse": [
            HookMatcher(
                matcher="mcp__customer-support__",
                hooks=[post_tool_use_hook],
            ),
        ],
    }
