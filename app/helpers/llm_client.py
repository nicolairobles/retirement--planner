"""
Multi-provider LLM client for chat feature.

Supports Groq, OpenAI, and Ollama with tool calling.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Generator, Literal

import streamlit as st

# Provider type
Provider = Literal["groq", "openai", "ollama", "gemini"]

# Default models per provider
# Gemini: 1,000 req/day free tier - best for small apps
# Groq: 14,400 req/day but 30 RPM limit causes issues with concurrent users
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",  # Free tier, better reasoning than lite
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "ollama": "qwen2.5:7b",  # Qwen has best tool calling accuracy for local models
}

# Models that have been retired — map to their replacement
_RETIRED_MODELS = {
    "gemini-2.0-flash-lite": "gemini-2.5-flash-lite",
    "gemini-2.0-flash": "gemini-2.5-flash",
    "gemini-1.5-flash": "gemini-2.5-flash-lite",
    "mixtral-8x7b-32768": "llama-3.3-70b-versatile",
}


def _parse_malformed_tool_call(error_msg: str) -> dict | None:
    """Parse malformed tool calls from Llama models.

    Llama sometimes generates tool calls in XML-like format:
    <function=set_input{"field": "monthly_spending", "value": 1000}</function>
    <function=set_input({"field": "current_age", "value": 42})</function>

    Returns a properly formatted tool call dict, or None if parsing fails.
    """
    # Try to extract the failed_generation from the error
    # Various patterns Llama uses for tool calls
    patterns = [
        r'<function=(\w+)\((\{[^}]+\})\)</function>',  # <function=name({args})</function>
        r'<function=(\w+)\{([^}]+)\}</function>',  # <function=name{args}</function>
        r'<function=(\w+)>\{([^}]+)\}</function>',  # <function=name>{args}</function>
    ]

    for pattern in patterns:
        match = re.search(pattern, error_msg)
        if match:
            func_name = match.group(1)
            args_str = match.group(2)
            # Add braces if not present
            if not args_str.startswith("{"):
                args_str = "{" + args_str + "}"
            try:
                args = json.loads(args_str)
                return {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "arguments": json.dumps(args),
                    },
                }
            except json.JSONDecodeError:
                pass

    # Try extracting from the full error message with any format
    full_match = re.search(r'<function=(\w+)[\(\{]([^<]+)[\)\}]</function>', error_msg)
    if full_match:
        func_name = full_match.group(1)
        args_str = full_match.group(2).strip()
        # Clean up the args string
        if args_str.startswith("("):
            args_str = args_str[1:]
        if args_str.endswith(")"):
            args_str = args_str[:-1]
        if not args_str.startswith("{"):
            args_str = "{" + args_str + "}"
        try:
            args = json.loads(args_str)
            return {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": json.dumps(args),
                },
            }
        except json.JSONDecodeError:
            pass

    return None

# Tool definitions for the retirement simulation
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_input",
            "description": """Set a value in the user's retirement plan. The change takes effect immediately.

WHEN TO USE: When the user tells you a value they want to set, or answers a question about their situation.

EXAMPLES:
- User says "I'm 38" → set_input("current_age", 38)
- User says "I spend about $4000 a month" → set_input("monthly_spending", 4000)
- User says "I make $120k" → set_input("salary", 120000)
- User says "I put 10% in my 401k" → Calculate: if salary is $100k, that's $10k → set_input("annual_401k", 10000)

AVAILABLE FIELDS: current_age, end_age, retirement_target, salary, salary_growth, annual_401k, roth_percentage, monthly_spending, monthly_rent, starting_401k, starting_roth, starting_investments, starting_cash, starting_crypto, stock_return, bond_return, social_security_age, social_security_benefit

IMPORTANT: After calling this, confirm to the user what you set.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Field name from the available fields list",
                    },
                    "value": {
                        "type": "number",
                        "description": "The value. Use raw numbers (4000 not '$4,000'). For percentages use decimals (0.07 for 7%).",
                    },
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_scenario",
            "description": """Get the user's current retirement plan inputs and projection results.

WHEN TO USE:
- User asks about their current plan ("What's my retirement age?", "How much am I saving?")
- Before giving recommendations
- You need to know their current values to answer a question

RETURNS: Current age, retirement age, net worth projections, spending, savings rates, and more.""",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_what_if",
            "description": """Run a hypothetical projection WITHOUT saving changes. Shows comparison between current plan and modified scenario.

WHEN TO USE:
- User asks "What if I..." questions
- User wants to compare scenarios
- You want to show the impact of a potential change

IMPORTANT: This does NOT save changes. Use set_input to actually modify values.
NOTE: You CANNOT set retirement_age here — it is computed from retirement_target. To explore earlier retirement, lower the retirement_target or change spending/savings.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "monthly_spending": {
                        "type": "number",
                        "description": "Hypothetical monthly spending",
                    },
                    "annual_401k_contribution": {
                        "type": "number",
                        "description": "Annual 401(k) contribution amount",
                    },
                    "retirement_target": {
                        "type": "number",
                        "description": "Net worth target to trigger retirement (lower = retire earlier)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "Get the top 3 actionable recommendations to improve the retirement plan. Returns specific changes the user could make and their impact on retirement age and net worth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of recommendations to return (default 3)",
                        "default": 3,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_safe_target",
            "description": "Find the minimum retirement net worth target that passes both deterministic and historical (Monte Carlo) checks. Use this when users ask 'How much do I need to retire?' or 'What's a safe retirement number?'",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_glossary",
            "description": "Look up the definition of a retirement planning term. Use this for questions like 'What is a Roth IRA?' or 'What does RMD mean?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "The term to look up (e.g., 'Roth IRA', 'RMD', '4% rule', 'glide path')",
                    },
                },
                "required": ["term"],
            },
        },
    },
]


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "user", "assistant", or "system"
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None  # For tool responses


def get_client(provider: Provider, api_key: str | None = None, base_url: str | None = None):
    """Get the appropriate client for the provider.

    Args:
        provider: "groq", "openai", "ollama", or "gemini"
        api_key: API key (not needed for Ollama)
        base_url: Custom base URL (used for Ollama)

    Returns:
        Configured client instance
    """
    if provider == "groq":
        from groq import Groq
        return Groq(api_key=api_key)

    elif provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=api_key)

    elif provider == "gemini":
        from openai import OpenAI
        # Google provides OpenAI-compatible endpoint for Gemini
        return OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    elif provider == "ollama":
        from openai import OpenAI
        # Ollama uses OpenAI-compatible API
        return OpenAI(
            api_key="ollama",  # Dummy key, Ollama doesn't need auth
            base_url=base_url or "http://localhost:11434/v1",
        )

    else:
        raise ValueError(f"Unknown provider: {provider}")


def chat_completion(
    messages: list[dict],
    provider: Provider,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    tools: list[dict] | None = None,
    stream: bool = True,
) -> Generator[str, None, dict | None]:
    """Send a chat completion request and stream the response.

    Args:
        messages: List of message dicts with "role" and "content"
        provider: "groq", "openai", or "ollama"
        api_key: API key for the provider
        model: Model name (uses default if not specified)
        base_url: Custom base URL (for Ollama)
        tools: Tool definitions (optional)
        stream: Whether to stream the response

    Yields:
        Text chunks as they arrive

    Returns:
        Final message dict with tool_calls if any, or None if just text
    """
    client = get_client(provider, api_key, base_url)
    model = model or DEFAULT_MODELS.get(provider, "llama-3.3-70b-versatile")

    # Auto-migrate retired models
    if model in _RETIRED_MODELS:
        model = _RETIRED_MODELS[model]

    # Build request kwargs
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "temperature": 0.7,
    }

    # Reduce repetition (Gemini doesn't support frequency_penalty)
    if provider in ("openai", "groq"):
        kwargs["frequency_penalty"] = 0.3

    # Add tools if provided (all providers support OpenAI-compatible tool calling)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        if stream:
            response = client.chat.completions.create(**kwargs)

            collected_content = ""
            collected_tool_calls: list[dict] = []
            current_tool_call: dict | None = None

            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Handle text content
                if delta.content:
                    collected_content += delta.content
                    yield delta.content

                # Handle tool calls (streamed incrementally)
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index is not None:
                            # New tool call or continuation
                            while len(collected_tool_calls) <= tc.index:
                                collected_tool_calls.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                })
                            current_tool_call = collected_tool_calls[tc.index]

                        if current_tool_call:
                            if tc.id:
                                current_tool_call["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    current_tool_call["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    current_tool_call["function"]["arguments"] += tc.function.arguments

            # Yield tool calls if any were collected (use yield, not return, so it's captured)
            if collected_tool_calls and any(tc["id"] for tc in collected_tool_calls):
                yield {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls,
                }
            elif collected_content:
                yield {
                    "role": "assistant",
                    "content": collected_content,
                }

        else:
            # Non-streaming
            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # Yield content first if present
            if message.content:
                yield message.content

            # Yield tool calls or final message dict
            if hasattr(message, "tool_calls") and message.tool_calls:
                yield {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                }
            elif not message.content:
                # No content and no tool calls - yield empty response indicator
                yield {"role": "assistant", "content": None}

    except Exception as e:
        error_msg = str(e)

        # Handle malformed tool calls from Llama models
        if "tool_use_failed" in error_msg or "failed_generation" in error_msg:
            # Try to parse the malformed tool call
            parsed_tool_call = _parse_malformed_tool_call(error_msg)
            if parsed_tool_call:
                yield {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [parsed_tool_call],
                }
                return
            else:
                yield "I tried to update your plan but encountered a formatting issue. Please try rephrasing your request."
                return

        if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
            yield f"API key error: Please check your {provider.upper()} API key in Chat settings."
        elif "404" in error_msg and ("no longer available" in error_msg.lower() or "not found" in error_msg.lower()):
            # Model has been retired
            default = DEFAULT_MODELS.get(provider, "unknown")
            yield (
                f"The selected model is no longer available. "
                f"Please open **Chat settings** below and switch to **{default}**."
            )
        elif "rate" in error_msg.lower() and "limit" in error_msg.lower():
            yield "Rate limit reached. Please wait a moment and try again."
        elif "connection" in error_msg.lower():
            if provider == "ollama":
                yield "Cannot connect to Ollama. Make sure Ollama is running locally (`ollama serve`)."
            else:
                yield f"Connection error with {provider.upper()}. Please try again."
        else:
            # Strip verbose JSON from error messages for readability
            short = error_msg
            if len(short) > 200:
                short = short[:200] + "..."
            yield f"Error: {short}"


def format_tool_result(result: Any) -> str:
    """Format a tool result for the LLM."""
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    elif isinstance(result, list):
        return json.dumps(result, indent=2, default=str)
    else:
        return str(result)
