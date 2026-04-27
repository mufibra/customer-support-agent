"""Unit tests for customer support MCP tools."""

import asyncio
import json
import pytest
from pathlib import Path

from src.tools import (
    get_customer_tool,
    lookup_order_tool,
    process_refund_tool,
    escalate_to_human_tool,
)
from src.mock_data import load_db, reset_db

# Access the underlying async handler from each SdkMcpTool
get_customer_fn = get_customer_tool.handler
lookup_order_fn = lookup_order_tool.handler
process_refund_fn = process_refund_tool.handler
escalate_to_human_fn = escalate_to_human_tool.handler


@pytest.fixture(autouse=True)
def fresh_db():
    """Ensure fresh DB state for each test."""
    reset_db()
    yield
    reset_db()


def run(coro):
    """Helper to run async tool calls in sync tests."""
    return asyncio.run(coro)


def parse_result(result: dict) -> dict:
    """Extract parsed JSON from tool result."""
    text = result["content"][0]["text"]
    return json.loads(text)


# ---------------------------------------------------------------------------
# get_customer tests
# ---------------------------------------------------------------------------
class TestGetCustomer:
    def test_valid_customer(self):
        result = run(get_customer_fn({"customer_id": "CUST-0001"}))
        assert not result.get("is_error", False)
        data = parse_result(result)
        assert data["customer_id"] == "CUST-0001"
        assert "first_name" in data
        assert "plan" in data
        assert "satisfaction_score" in data

    def test_invalid_format_no_prefix(self):
        result = run(get_customer_fn({"customer_id": "1234"}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "validation"

    def test_invalid_format_wrong_digits(self):
        result = run(get_customer_fn({"customer_id": "CUST-ABC"}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "validation"

    def test_not_found(self):
        result = run(get_customer_fn({"customer_id": "CUST-9999"}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "not_found"

    def test_suspended_account_warning(self):
        """Suspended accounts should include a warning."""
        db = load_db()
        # Find a suspended customer
        suspended = None
        for cid, c in db["customers_by_id"].items():
            if c["account_status"] == "suspended":
                suspended = cid
                break
        if suspended is None:
            pytest.skip("No suspended customer in test data")
        result = run(get_customer_fn({"customer_id": suspended}))
        data = parse_result(result)
        assert data["account_status"] == "suspended"
        assert "warning" in data


# ---------------------------------------------------------------------------
# lookup_order tests
# ---------------------------------------------------------------------------
class TestLookupOrder:
    def test_by_order_id(self):
        result = run(lookup_order_fn({"order_id": "ORD-00001"}))
        assert not result.get("is_error", False)
        data = parse_result(result)
        assert len(data["orders"]) == 1
        assert data["orders"][0]["order_id"] == "ORD-00001"

    def test_by_customer_id(self):
        result = run(lookup_order_fn({"customer_id": "CUST-0001"}))
        assert not result.get("is_error", False)
        data = parse_result(result)
        assert data["total_orders"] >= 1

    def test_invalid_order_format(self):
        result = run(lookup_order_fn({"order_id": "ORDER-1"}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "validation"

    def test_order_not_found(self):
        result = run(lookup_order_fn({"order_id": "ORD-99999"}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "not_found"

    def test_no_ids_provided(self):
        result = run(lookup_order_fn({}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "validation"


# ---------------------------------------------------------------------------
# process_refund tests
# ---------------------------------------------------------------------------
class TestProcessRefund:
    def _find_eligible_order(self) -> str | None:
        db = load_db()
        for oid, o in db["orders_by_id"].items():
            if o["return_eligible"] and o["total_amount"] <= 500:
                return oid
        return None

    def _find_ineligible_order(self) -> str | None:
        db = load_db()
        for oid, o in db["orders_by_id"].items():
            if not o["return_eligible"] and o["status"] == "delivered":
                return oid
        return None

    def _find_non_delivered_order(self) -> str | None:
        db = load_db()
        for oid, o in db["orders_by_id"].items():
            if o["status"] != "delivered":
                return oid
        return None

    def test_valid_refund(self):
        oid = self._find_eligible_order()
        if not oid:
            pytest.skip("No eligible order in test data")
        result = run(process_refund_fn({"order_id": oid, "reason": "Defective product"}))
        assert not result.get("is_error", False)
        data = parse_result(result)
        assert data["status"] == "refund_processed"
        assert "refund_id" in data

    def test_invalid_order_format(self):
        result = run(process_refund_fn({"order_id": "BAD", "reason": "test"}))
        assert result["is_error"] is True
        data = parse_result(result)
        assert data["errorCategory"] == "validation"

    def test_order_not_found(self):
        result = run(process_refund_fn({"order_id": "ORD-99999", "reason": "test"}))
        assert result["is_error"] is True
        assert parse_result(result)["errorCategory"] == "not_found"

    def test_non_delivered_order(self):
        oid = self._find_non_delivered_order()
        if not oid:
            pytest.skip("No non-delivered order in test data")
        result = run(process_refund_fn({"order_id": oid, "reason": "test"}))
        assert result["is_error"] is True
        assert parse_result(result)["errorCategory"] == "business_rule"

    def test_ineligible_return_window(self):
        oid = self._find_ineligible_order()
        if not oid:
            pytest.skip("No ineligible order in test data")
        result = run(process_refund_fn({"order_id": oid, "reason": "test"}))
        assert result["is_error"] is True
        assert parse_result(result)["errorCategory"] == "business_rule"

    def test_empty_reason(self):
        result = run(process_refund_fn({"order_id": "ORD-00001", "reason": ""}))
        assert result["is_error"] is True
        assert parse_result(result)["errorCategory"] == "validation"


# ---------------------------------------------------------------------------
# escalate_to_human tests
# ---------------------------------------------------------------------------
class TestEscalateToHuman:
    def test_valid_escalation(self):
        result = run(escalate_to_human_fn({
            "customer_id": "CUST-0001",
            "priority": "high",
            "reason": "Refund exceeds $500",
            "context_summary": "Customer wants refund on order ORD-00001 totaling $600.",
        }))
        assert not result.get("is_error", False)
        data = parse_result(result)
        assert data["status"] == "escalated"
        assert data["priority"] == "high"
        assert "escalation_id" in data

    def test_all_priority_levels(self):
        for p in ("low", "medium", "high", "critical"):
            result = run(escalate_to_human_fn({
                "priority": p,
                "reason": f"Test {p}",
                "context_summary": "Test context.",
            }))
            assert not result.get("is_error", False)

    def test_invalid_priority(self):
        result = run(escalate_to_human_fn({
            "priority": "urgent",
            "reason": "test",
            "context_summary": "test",
        }))
        assert result["is_error"] is True
        assert parse_result(result)["errorCategory"] == "validation"

    def test_empty_reason(self):
        result = run(escalate_to_human_fn({
            "priority": "low",
            "reason": "",
            "context_summary": "test",
        }))
        assert result["is_error"] is True

    def test_invalid_customer_id_format(self):
        result = run(escalate_to_human_fn({
            "customer_id": "BAD-ID",
            "priority": "low",
            "reason": "test",
            "context_summary": "test",
        }))
        assert result["is_error"] is True
        assert parse_result(result)["errorCategory"] == "validation"
