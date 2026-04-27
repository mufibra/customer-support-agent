"""Main agent runner for TechGear Customer Support Agent."""

import argparse
import asyncio
import sys
import os

from dotenv import load_dotenv

from claude_code_sdk import (
    ClaudeCodeOptions,
    ClaudeSDKClient,
    ResultMessage,
    AssistantMessage,
    query,
)

from src.tools import create_support_server
from src.hooks import get_hook_matchers, reset_session


ALLOWED_TOOLS = [
    "mcp__customer-support__get_customer",
    "mcp__customer-support__lookup_order",
    "mcp__customer-support__process_refund",
    "mcp__customer-support__escalate_to_human",
]


def build_options() -> ClaudeCodeOptions:
    """Build ClaudeCodeOptions with MCP server, hooks, and constraints."""
    support_server = create_support_server()
    hook_matchers = get_hook_matchers()

    return ClaudeCodeOptions(
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        max_turns=20,
        mcp_servers={"customer-support": support_server},
        hooks=hook_matchers,
        system_prompt=(
            "You are a TechGear Electronics customer support agent. "
            "Follow the workflow: greet → verify (get_customer) → investigate "
            "(lookup_order) → resolve (process_refund) → escalate if needed. "
            "Always verify the customer before looking up orders or processing refunds. "
            "Be empathetic, professional, and concise."
        ),
    )


async def run_single_query(prompt: str) -> None:
    """Run a single query and print the result."""
    options = build_options()

    print(f"\n{'='*60}")
    print(f"Query: {prompt}")
    print(f"{'='*60}\n")

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text"):
                    print(f"Agent: {block.text}")
        elif isinstance(message, ResultMessage):
            if message.is_error:
                print(f"\n[ERROR] {message.result}")
            else:
                print(f"\n[RESULT] {message.result}")
            if message.total_cost_usd:
                print(f"[COST] ${message.total_cost_usd:.4f} | Turns: {message.num_turns}")
            break


async def run_interactive() -> None:
    """Run an interactive multi-turn support session."""
    options = build_options()

    print("\n" + "=" * 60)
    print("TechGear Customer Support Agent")
    print("Type 'quit' or 'exit' to end the session.")
    print("=" * 60 + "\n")

    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\nSession ended.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                print("\nThank you for contacting TechGear support. Goodbye!")
                break

            client.query(prompt=user_input)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text"):
                            print(f"\nAgent: {block.text}")
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        print(f"\n[ERROR] {message.result}")
                    if message.total_cost_usd:
                        print(f"  [Cost: ${message.total_cost_usd:.4f}]")
                    break


def main():
    load_dotenv()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="TechGear Customer Support Agent")
    parser.add_argument(
        "-q", "--query",
        type=str,
        help="Single query mode — run one prompt and exit",
    )
    args = parser.parse_args()

    reset_session()

    if args.query:
        asyncio.run(run_single_query(args.query))
    else:
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
