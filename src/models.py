"""Pydantic models for TechGear Customer Support Agent."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class PlanType(str, Enum):
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OrderStatus(str, Enum):
    DELIVERED = "delivered"
    SHIPPED = "shipped"
    PROCESSING = "processing"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class EscalationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    TRANSIENT = "transient"
    BUSINESS_RULE = "business_rule"


class Customer(BaseModel):
    customer_id: str = Field(pattern=r"^CUST-\d{4}$")
    first_name: str
    last_name: str
    email: str
    phone: str
    plan: PlanType
    account_status: AccountStatus
    satisfaction_score: float = Field(ge=0.0, le=5.0)
    created_at: str
    order_ids: list[str] = []


class OrderItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float


class Order(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{5}$")
    customer_id: str
    items: list[OrderItem]
    total_amount: float
    status: OrderStatus
    ordered_at: str
    delivered_at: Optional[str] = None
    return_eligible: bool = False


class RefundLogEntry(BaseModel):
    refund_id: str
    order_id: str
    customer_id: str
    amount: float
    reason: str
    processed_at: str


class EscalationLogEntry(BaseModel):
    escalation_id: str
    customer_id: Optional[str] = None
    priority: EscalationPriority
    reason: str
    context_summary: str
    created_at: str


class ToolError(BaseModel):
    """Structured error response for tool failures."""
    error: str
    errorCategory: ErrorCategory
    isRetryable: bool = False
    suggestedAction: str


class Product(BaseModel):
    product_id: str
    name: str
    price: float
    category: str
