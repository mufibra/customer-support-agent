"""Unit tests for PreToolUse and PostToolUse hooks."""

import asyncio
import json
import pytest

from src.hooks import (
    pre_tool_use_hook,
    post_tool_use_hook,
    session,
    reset_session,
)
from src.mock_data import load_db, reset_db
from claude_code_sdk.types import HookContext


@pytest.fixture(autouse=True)
def clean_state():
    """Reset session and DB state before each test."""
    reset_session()
    reset_db()
    yield
    reset_session()
    reset_db()


def run(coro):
    return asyncio.run(coro)


CTX = HookContext()
TOOL_PREFIX = "mcp__customer-support__"


# ---------------------------------------------------------------------------
# PreToolUse hook tests
# ---------------------------------------------------------------------------
class TestPreToolUseHook:
    def test_lookup_order_blocked_without_customer(self):
        """lookup_order must be blocked if get_customer wasn't called."""
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}lookup_order", "tool_input": {"customer_id": "CUST-0001"}},
            None, CTX,
        ))
        assert result.get("decision") == "block"
        assert "get_customer" in result["systemMessage"]

    def test_lookup_order_allowed_after_customer(self):
        """lookup_order allowed after get_customer is verified."""
        session.customer_verified = True
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}lookup_order", "tool_input": {"customer_id": "CUST-0001"}},
            None, CTX,
        ))
        assert result.get("decision") is None  # Not blocked

    def test_process_refund_blocked_without_customer(self):
        """process_refund blocked if customer not verified."""
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}process_refund", "tool_input": {"order_id": "ORD-00001", "reason": "test"}},
            None, CTX,
        ))
        assert result.get("decision") == "block"
        assert "get_customer" in result["systemMessage"]

    def test_process_refund_blocked_without_order(self):
        """process_refund blocked if order not looked up."""
        session.customer_verified = True
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}process_refund", "tool_input": {"order_id": "ORD-00001", "reason": "test"}},
            None, CTX,
        ))
        assert result.get("decision") == "block"
        assert "lookup_order" in result["systemMessage"]

    def test_process_refund_allowed_with_prerequisites(self):
        """process_refund allowed when all prerequisites met."""
        session.customer_verified = True
        session.order_looked_up = True
        # Find an eligible order <= $500
        db = load_db()
        eligible_oid = None
        for oid, o in db["orders_by_id"].items():
            if o["return_eligible"] and o["total_amount"] <= 500:
                eligible_oid = oid
                break
        if not eligible_oid:
            pytest.skip("No eligible order <= $500")
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}process_refund", "tool_input": {"order_id": eligible_oid, "reason": "test"}},
            None, CTX,
        ))
        assert result.get("decision") is None

    def test_refund_over_500_blocked(self):
        """Refunds > $500 must be blocked with escalation message."""
        session.customer_verified = True
        session.order_looked_up = True
        # Find or fabricate an order > $500
        db = load_db()
        big_oid = None
        for oid, o in db["orders_by_id"].items():
            if o["total_amount"] > 500:
                big_oid = oid
                break
        if not big_oid:
            # Patch one order to be > $500
            first_oid = list(db["orders_by_id"].keys())[0]
            db["orders_by_id"][first_oid]["total_amount"] = 750.00
            from src.mock_data import save_db
            save_db(db)
            big_oid = first_oid

        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}process_refund", "tool_input": {"order_id": big_oid, "reason": "test"}},
            None, CTX,
        ))
        assert result.get("decision") == "block"
        assert "500" in result["systemMessage"]
        assert "escalat" in result["systemMessage"].lower()

    def test_max_refunds_per_session(self):
        """Block after 3 refunds in a session."""
        session.customer_verified = True
        session.order_looked_up = True
        session.refund_count = 3  # Already at limit

        db = load_db()
        eligible_oid = None
        for oid, o in db["orders_by_id"].items():
            if o["return_eligible"] and o["total_amount"] <= 500:
                eligible_oid = oid
                break
        if not eligible_oid:
            pytest.skip("No eligible order")

        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}process_refund", "tool_input": {"order_id": eligible_oid, "reason": "test"}},
            None, CTX,
        ))
        assert result.get("decision") == "block"
        assert "3" in result["systemMessage"]

    def test_get_customer_always_allowed(self):
        """get_customer has no prerequisites — always allowed."""
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}get_customer", "tool_input": {"customer_id": "CUST-0001"}},
            None, CTX,
        ))
        assert result.get("decision") is None

    def test_escalate_always_allowed(self):
        """escalate_to_human has no prerequisites."""
        result = run(pre_tool_use_hook(
            {"tool_name": f"{TOOL_PREFIX}escalate_to_human", "tool_input": {
                "priority": "high", "reason": "test", "context_summary": "test"
            }},
            None, CTX,
        ))
        assert result.get("decision") is None


# ---------------------------------------------------------------------------
# PostToolUse hook tests
# ---------------------------------------------------------------------------
class TestPostToolUseHook:
    def test_get_customer_sets_verified(self):
        """Successful get_customer should set customer_verified."""
        assert session.customer_verified is False
        result = run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}get_customer",
                "tool_input": {"customer_id": "CUST-0001"},
                "tool_result": json.dumps({"customer_id": "CUST-0001", "satisfaction_score": 4.5}),
            },
            None, CTX,
        ))
        assert session.customer_verified is True
        assert session.verified_customer_id == "CUST-0001"

    def test_lookup_order_sets_looked_up(self):
        """Successful lookup_order should set order_looked_up."""
        assert session.order_looked_up is False
        run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}lookup_order",
                "tool_input": {"order_id": "ORD-00001"},
                "tool_result": json.dumps({"orders": [{"order_id": "ORD-00001"}]}),
            },
            None, CTX,
        ))
        assert session.order_looked_up is True

    def test_process_refund_increments_count(self):
        """Successful process_refund should increment refund_count."""
        assert session.refund_count == 0
        run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}process_refund",
                "tool_input": {"order_id": "ORD-00001", "reason": "test"},
                "tool_result": json.dumps({"status": "refund_processed", "refund_id": "REF-TEST"}),
            },
            None, CTX,
        ))
        assert session.refund_count == 1

    def test_low_satisfaction_alert(self):
        """Customer with satisfaction < 2.0 should trigger alert."""
        result = run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}get_customer",
                "tool_input": {"customer_id": "CUST-0001"},
                "tool_result": json.dumps({"customer_id": "CUST-0001", "satisfaction_score": 1.5}),
            },
            None, CTX,
        ))
        assert "systemMessage" in result
        assert "LOW SATISFACTION" in result["systemMessage"]
        assert "1.5" in result["systemMessage"]

    def test_no_alert_for_normal_satisfaction(self):
        """Customer with satisfaction >= 2.0 should not trigger alert."""
        result = run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}get_customer",
                "tool_input": {"customer_id": "CUST-0001"},
                "tool_result": json.dumps({"customer_id": "CUST-0001", "satisfaction_score": 3.5}),
            },
            None, CTX,
        ))
        assert result.get("systemMessage") is None

    def test_error_result_not_tracked(self):
        """Error results should not update session state."""
        run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}get_customer",
                "tool_input": {"customer_id": "CUST-9999"},
                "tool_result": json.dumps({"error": "Not found", "errorCategory": "not_found"}),
            },
            None, CTX,
        ))
        assert session.customer_verified is False

    def test_audit_log_entries(self):
        """Every tool call should produce an audit log entry."""
        assert len(session.audit_log) == 0
        run(post_tool_use_hook(
            {
                "tool_name": f"{TOOL_PREFIX}get_customer",
                "tool_input": {"customer_id": "CUST-0001"},
                "tool_result": json.dumps({"customer_id": "CUST-0001", "satisfaction_score": 4.0}),
            },
            None, CTX,
        ))
        assert len(session.audit_log) == 1
        assert session.audit_log[0]["tool"] == "get_customer"
        assert session.audit_log[0]["status"] == "success"
