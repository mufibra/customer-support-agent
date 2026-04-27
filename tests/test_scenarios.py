"""Integration test scenarios — example prompts for manual and automated testing.

These scenarios demonstrate the agent's expected behavior for common
customer support workflows. Run manually with:
    python -m src.agent -q "<prompt>"
"""

# Scenario 1: Happy path — customer lookup → order lookup → refund
SCENARIO_HAPPY_PATH = (
    "Hi, I'm customer CUST-0001. I'd like a refund on my most recent order. "
    "The product was defective."
)

# Scenario 2: Prerequisite violation — try refund without customer lookup
SCENARIO_SKIP_CUSTOMER = (
    "Process a refund for order ORD-00001 please."
)

# Scenario 3: Suspended account
SCENARIO_SUSPENDED = (
    "I need help with my account. My customer ID is CUST-0005."
    # Note: CUST-0005 may or may not be suspended — depends on seed.
    # Check mock_db.json for an actual suspended account.
)

# Scenario 4: High-value refund requiring escalation
SCENARIO_HIGH_VALUE = (
    "I'm customer CUST-0002 and I want a refund on an order that cost over $500."
)

# Scenario 5: Low satisfaction customer
SCENARIO_LOW_SATISFACTION = (
    "My ID is CUST-0010. I've been having terrible experiences with your products."
)

# Scenario 6: Multiple refund requests (tests session limit)
SCENARIO_MULTIPLE_REFUNDS = (
    "I'm CUST-0001. I want refunds on ALL my orders. Every single one."
)

# Scenario 7: Invalid customer ID
SCENARIO_INVALID_ID = (
    "My customer number is 12345. Can you look me up?"
)

# Scenario 8: Escalation request
SCENARIO_ESCALATION = (
    "I want to speak to a manager. This is unacceptable. My ID is CUST-0003."
)
