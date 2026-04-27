"""Custom MCP tools for TechGear Customer Support Agent."""

import json
import re
import uuid
from datetime import datetime
from typing import Any

from claude_code_sdk import tool, create_sdk_mcp_server

from src.mock_data import (
    get_customer,
    get_order,
    get_orders_by_customer,
    add_refund_log,
    add_escalation_log,
)


def _error_response(
    error: str,
    category: str,
    retryable: bool = False,
    suggested_action: str = "",
) -> dict[str, Any]:
    """Build a structured error response."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "error": error,
                        "errorCategory": category,
                        "isRetryable": retryable,
                        "suggestedAction": suggested_action,
                    }
                ),
            }
        ],
        "is_error": True,
    }


def _success_response(data: dict) -> dict[str, Any]:
    """Build a structured success response."""
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


# ---------------------------------------------------------------------------
# Tool 1: get_customer
# ---------------------------------------------------------------------------
@tool(
    "get_customer",
    "Look up a customer by their ID (format: CUST-XXXX where X is a digit). "
    "Returns customer profile including name, email, plan, account status, and "
    "satisfaction score. Must be called before lookup_order or process_refund. "
    "Edge cases: returns error if ID format is invalid, customer not found, or "
    "account is suspended (flags it for the agent to escalate).",
    {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer ID in CUST-XXXX format (e.g. CUST-0001)",
            }
        },
        "required": ["customer_id"],
    },
)
async def get_customer_tool(args: dict[str, Any]) -> dict[str, Any]:
    customer_id = args.get("customer_id", "")

    # Validate format
    if not re.match(r"^CUST-\d{4}$", customer_id):
        return _error_response(
            f"Invalid customer ID format: '{customer_id}'. Expected CUST-XXXX.",
            "validation",
            suggested_action="Ask the customer for their correct ID in CUST-XXXX format.",
        )

    customer = get_customer(customer_id)
    if not customer:
        return _error_response(
            f"Customer {customer_id} not found.",
            "not_found",
            suggested_action="Verify the customer ID and try again.",
        )

    result = {
        "customer_id": customer["customer_id"],
        "first_name": customer["first_name"],
        "last_name": customer["last_name"],
        "email": customer["email"],
        "phone": customer["phone"],
        "plan": customer["plan"],
        "account_status": customer["account_status"],
        "satisfaction_score": customer["satisfaction_score"],
        "order_count": len(customer.get("order_ids", [])),
    }

    if customer["account_status"] == "suspended":
        result["warning"] = (
            "This account is SUSPENDED. No transactions can be processed. "
            "Please escalate to a human agent."
        )

    return _success_response(result)


# ---------------------------------------------------------------------------
# Tool 2: lookup_order
# ---------------------------------------------------------------------------
@tool(
    "lookup_order",
    "Look up orders by order ID (ORD-XXXXX) or customer ID (CUST-XXXX). "
    "Returns order details including items, total, status, and return eligibility. "
    "Prerequisite: get_customer must be called first. "
    "Edge cases: invalid ID format, order/customer not found, shows return_eligible "
    "flag (True only if delivered within 30 days).",
    {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "Order ID in ORD-XXXXX format (optional if customer_id provided)",
            },
            "customer_id": {
                "type": "string",
                "description": "Customer ID in CUST-XXXX format to list all orders (optional if order_id provided)",
            },
        },
    },
)
async def lookup_order_tool(args: dict[str, Any]) -> dict[str, Any]:
    order_id = args.get("order_id")
    customer_id = args.get("customer_id")

    if not order_id and not customer_id:
        return _error_response(
            "Either order_id or customer_id must be provided.",
            "validation",
            suggested_action="Provide an order_id (ORD-XXXXX) or customer_id (CUST-XXXX).",
        )

    # Lookup by order_id
    if order_id:
        if not re.match(r"^ORD-\d{5}$", order_id):
            return _error_response(
                f"Invalid order ID format: '{order_id}'. Expected ORD-XXXXX.",
                "validation",
                suggested_action="Ask for the correct order ID in ORD-XXXXX format.",
            )
        order = get_order(order_id)
        if not order:
            return _error_response(
                f"Order {order_id} not found.",
                "not_found",
                suggested_action="Verify the order ID and try again.",
            )
        return _success_response({"orders": [order]})

    # Lookup by customer_id
    if not re.match(r"^CUST-\d{4}$", customer_id):
        return _error_response(
            f"Invalid customer ID format: '{customer_id}'. Expected CUST-XXXX.",
            "validation",
            suggested_action="Ask for the correct customer ID.",
        )
    orders = get_orders_by_customer(customer_id)
    if not orders:
        return _error_response(
            f"No orders found for customer {customer_id}.",
            "not_found",
            suggested_action="Confirm the customer ID or check if they have any orders.",
        )
    return _success_response({"orders": orders, "total_orders": len(orders)})


# ---------------------------------------------------------------------------
# Tool 3: process_refund
# ---------------------------------------------------------------------------
@tool(
    "process_refund",
    "Process a refund for a specific order. Prerequisites: get_customer AND "
    "lookup_order must be called first. Validates: order must be 'delivered' status, "
    "return_eligible must be True, refund amount must not exceed $500 (otherwise "
    "escalate to human). Edge cases: order not found, not eligible, amount exceeds "
    "cap, already returned/cancelled.",
    {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "Order ID to refund (ORD-XXXXX format)",
            },
            "reason": {
                "type": "string",
                "description": "Reason for the refund",
            },
        },
        "required": ["order_id", "reason"],
    },
)
async def process_refund_tool(args: dict[str, Any]) -> dict[str, Any]:
    order_id = args.get("order_id", "")
    reason = args.get("reason", "")

    if not re.match(r"^ORD-\d{5}$", order_id):
        return _error_response(
            f"Invalid order ID format: '{order_id}'. Expected ORD-XXXXX.",
            "validation",
            suggested_action="Provide the correct order ID.",
        )

    if not reason.strip():
        return _error_response(
            "Refund reason is required.",
            "validation",
            suggested_action="Ask the customer for the reason for their refund.",
        )

    order = get_order(order_id)
    if not order:
        return _error_response(
            f"Order {order_id} not found.",
            "not_found",
            suggested_action="Verify the order ID.",
        )

    if order["status"] != "delivered":
        return _error_response(
            f"Order {order_id} has status '{order['status']}'. "
            "Only delivered orders can be refunded.",
            "business_rule",
            suggested_action=f"Inform the customer that {order['status']} orders cannot be refunded.",
        )

    if not order.get("return_eligible", False):
        return _error_response(
            f"Order {order_id} is outside the 30-day return window.",
            "business_rule",
            suggested_action="Inform the customer the return window has passed. Escalate if they insist.",
        )

    amount = order["total_amount"]
    if amount > 500:
        return _error_response(
            f"Refund amount ${amount:.2f} exceeds the $500 limit. Must be escalated.",
            "business_rule",
            suggested_action="Use escalate_to_human with high priority for this refund.",
        )

    # Process the refund
    refund_entry = {
        "refund_id": f"REF-{uuid.uuid4().hex[:8].upper()}",
        "order_id": order_id,
        "customer_id": order["customer_id"],
        "amount": amount,
        "reason": reason,
        "processed_at": datetime.now().isoformat(),
    }
    add_refund_log(refund_entry)

    return _success_response(
        {
            "status": "refund_processed",
            "refund_id": refund_entry["refund_id"],
            "order_id": order_id,
            "amount": amount,
            "message": f"Refund of ${amount:.2f} has been processed for order {order_id}.",
        }
    )


# ---------------------------------------------------------------------------
# Tool 4: escalate_to_human
# ---------------------------------------------------------------------------
@tool(
    "escalate_to_human",
    "Escalate the current issue to a human support agent. Use when: refund > $500, "
    "customer is very upset, account is suspended, or issue is outside automated scope. "
    "Priority levels: low (general questions), medium (billing disputes), "
    "high (refunds > $500, angry customers), critical (account security, data issues).",
    {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer ID if available (CUST-XXXX format)",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Escalation priority level",
            },
            "reason": {
                "type": "string",
                "description": "Why this needs human attention",
            },
            "context_summary": {
                "type": "string",
                "description": "Summary of the interaction so far for the human agent",
            },
        },
        "required": ["priority", "reason", "context_summary"],
    },
)
async def escalate_to_human_tool(args: dict[str, Any]) -> dict[str, Any]:
    customer_id = args.get("customer_id")
    priority = args.get("priority", "medium")
    reason = args.get("reason", "")
    context_summary = args.get("context_summary", "")

    if priority not in ("low", "medium", "high", "critical"):
        return _error_response(
            f"Invalid priority '{priority}'. Must be low, medium, high, or critical.",
            "validation",
            suggested_action="Use a valid priority level.",
        )

    if not reason.strip():
        return _error_response(
            "Escalation reason is required.",
            "validation",
            suggested_action="Provide a reason for the escalation.",
        )

    if customer_id and not re.match(r"^CUST-\d{4}$", customer_id):
        return _error_response(
            f"Invalid customer ID format: '{customer_id}'.",
            "validation",
            suggested_action="Provide a valid CUST-XXXX customer ID.",
        )

    escalation_entry = {
        "escalation_id": f"ESC-{uuid.uuid4().hex[:8].upper()}",
        "customer_id": customer_id,
        "priority": priority,
        "reason": reason,
        "context_summary": context_summary,
        "created_at": datetime.now().isoformat(),
    }
    add_escalation_log(escalation_entry)

    return _success_response(
        {
            "status": "escalated",
            "escalation_id": escalation_entry["escalation_id"],
            "priority": priority,
            "message": (
                f"Issue has been escalated with {priority} priority. "
                f"A human agent will review this shortly."
            ),
        }
    )


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
def create_support_server():
    """Create the in-process MCP server with all support tools."""
    return create_sdk_mcp_server(
        name="customer-support",
        version="1.0.0",
        tools=[
            get_customer_tool,
            lookup_order_tool,
            process_refund_tool,
            escalate_to_human_tool,
        ],
    )
