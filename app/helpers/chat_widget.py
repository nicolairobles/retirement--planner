"""
Sidebar chat widget for the retirement planner.

Renders a chat interface in the sidebar, above the input controls.
Chat can read and modify the user's retirement plan inputs.
"""

from __future__ import annotations

import json
import logging

import streamlit as st

from .llm_client import (
    TOOLS,
    DEFAULT_MODELS,
    _RETIRED_MODELS,
    chat_completion,
    format_tool_result,
)

# Available models per provider (keep default first in each list)
AVAILABLE_MODELS = {
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3-32b"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "ollama": ["qwen2.5:7b", "llama3.2", "llama3.1", "mistral"],
}

# Provider display names and help text
PROVIDER_LABELS = {
    "groq": "Groq (free, fast)",
    "gemini": "Gemini (free tier)",
    "openai": "OpenAI (requires key)",
    "ollama": "Ollama (local)",
}

API_KEY_HELP = {
    "groq": "Get a free key at [console.groq.com](https://console.groq.com)",
    "gemini": "Get a free key at [aistudio.google.com](https://aistudio.google.com/apikey)",
    "openai": "Get a key at [platform.openai.com](https://platform.openai.com/api-keys)",
    "ollama": "No key needed — just run `ollama serve` locally",
}

# Default provider — Gemini free tier is generous and doesn't require billing
DEFAULT_PROVIDER = "gemini"
from .local_storage import (
    load_chat_history,
    save_chat_history,
    clear_chat_history,
    load_chat_settings,
    save_chat_settings,
    get_remaining_free_messages,
    increment_message_count,
    is_free_tier_exhausted,
)
from .chat_tools import execute_tool

# Set up logging
logger = logging.getLogger(__name__)


# Base system prompt template - will be enhanced with dynamic context
BASE_SYSTEM_PROMPT = """You are a retirement planning assistant integrated into the "Retirement Planner" web application. You help users set up, understand, and optimize their retirement plans.

## How Retirement Age Works
Retirement age is calculated automatically — it is the age when liquid net worth reaches the retirement_target. You cannot set it directly. The levers that move it earlier are: higher income, higher savings, lower spending, or a lower target. When users say "I want to retire ASAP" or "as early as possible," call find_safe_target() to calculate the earliest safe retirement — do NOT lecture them about how the system works internally.

## About This Application
The Retirement Planner projects net worth year-by-year from current age to end_age. It models taxes, Social Security, 401(k), Roth conversions, property, healthcare, and more. It also runs Monte Carlo stress tests using historical market data (1928-2024). The user sees a sidebar with inputs on the left and charts/results on the right.

## Available Tools

### set_input(field, value)
Modifies a plan input. Changes take effect immediately and charts recalculate.

Available fields:
- current_age (int): User's current age
- end_age (int, 50-120): Life expectancy — when the plan ENDS (NOT retirement age)
- retirement_target (float): Net worth that TRIGGERS retirement. Lower = retire earlier.
- salary (float): Current annual salary
- salary_growth (float): Annual raise rate (decimal, e.g. 0.03 = 3%)
- annual_401k (float): Annual 401(k) contribution
- roth_percentage (float): Share of 401(k) going to Roth (0.0-1.0)
- monthly_spending (float): Monthly non-housing expenses
- monthly_rent (float): Monthly rent/mortgage
- starting_401k, starting_roth, starting_investments, starting_cash, starting_crypto (float): Current balances
- stock_return, bond_return (float): Expected returns (decimal)
- social_security_age (int, 62-70): Age to claim SS
- social_security_benefit (float): Monthly SS amount

### get_current_scenario()
Returns current inputs AND projection results (retirement age, net worth trajectory, whether portfolio survives). ALWAYS call this before giving advice.

### run_what_if(monthly_spending?, annual_401k_contribution?, retirement_target?)
Runs a hypothetical scenario WITHOUT saving. Compares baseline vs modified plan. Use this to show the impact of changes before committing.

### get_recommendations(top_n=3)
Returns the top actionable changes ranked by impact on retirement age and net worth.

### find_safe_target()
Finds the MINIMUM retirement target where: (1) deterministic projection survives to end_age, AND (2) 95%+ of historical market sequences (1928-2024) succeed. This effectively answers "What is the earliest I can safely retire?"

### lookup_glossary(term)
Returns definition of retirement terms (Roth, RMD, 4% rule, Monte Carlo, etc.)

## How to Help Users

### Setting up a plan (GUIDED FLOW):
Ask ONE question at a time in this order. After each answer, use set_input to save it.
1. Current age
2. Annual salary
3. Monthly spending (non-housing)
4. Monthly rent/mortgage
5. How much they save in their 401(k)
6. Current savings/investment balances
Do NOT ask for "retirement target" or "retirement age" — those confuse people. After the basics are set, call find_safe_target() to calculate their earliest safe retirement and present the results.

### "I want to retire at age X" / "ASAP" / "as early as possible":
- Call find_safe_target() — this answers the question directly
- Then call get_recommendations() to show what changes would help retire even earlier
- NEVER lecture the user about how the system works. Just give them the answer.

### Current plan questions:
Call get_current_scenario() first. Answer with specific numbers.

### "What if" questions:
Use run_what_if() to compare. Show the difference clearly. Don't save unless asked.

### Concept questions:
Use lookup_glossary(). Explain in plain English. Relate to their situation.

## Important Guidelines
1. ALWAYS call get_current_scenario() before giving advice — never guess numbers
2. Format currency with $ and commas: $1,250,000 not 1250000
3. Be concise — the user can see charts for details
4. After setting values, the UI updates automatically
5. This is educational, not financial advice
6. NEVER use backtick code formatting — write plain text only
7. Keep a professional, helpful tone

## Constraints
- You can only modify the fields listed above
- Do not auto-fill fields — ask the user first

## Current User Context
{current_context}
"""


def _get_current_context_summary() -> str:
    """Build a summary of the user's current scenario for the system prompt."""
    try:
        inputs = st.session_state.get("inputs", {})
        current_age = st.session_state.get("current_age", 35)

        if not inputs:
            return "No scenario loaded yet. User needs to set up their plan."

        # Extract key values
        context_parts = [
            f"Current age: {current_age}",
            f"End age: {inputs.get('in_EndAge', 95)}",
            f"Retirement target: ${inputs.get('in_RetirementTarget', 0):,.0f}",
            f"Annual salary: ${inputs.get('in_Salary_Y1', 0):,.0f}",
            f"Monthly spending (non-housing): ${inputs.get('in_MonthlyNonHousing', 0):,.0f}",
            f"Monthly rent: ${inputs.get('in_MonthlyRent', 0):,.0f}",
            f"Annual 401(k) contribution: ${inputs.get('in_401kContrib', 0):,.0f}",
            f"Starting 401(k) balance: ${inputs.get('in_401kStart', 0):,.0f}",
            f"Starting investments: ${inputs.get('in_InvestStart', 0):,.0f}",
            f"Social Security age: {inputs.get('in_SSAge', 67)}",
            f"Social Security benefit: ${inputs.get('in_SSBenefit', 0):,.0f}/month",
        ]

        return "User's current plan:\n" + "\n".join(f"- {part}" for part in context_parts)

    except Exception as e:
        logger.error(f"Error getting context summary: {e}")
        return "Unable to load current scenario context."


def _build_system_prompt() -> str:
    """Build the full system prompt with current context injected."""
    context = _get_current_context_summary()
    return BASE_SYSTEM_PROMPT.format(current_context=context)


def _get_api_key(settings: dict) -> str | None:
    """Get the API key based on settings and tier."""
    provider = settings.get("provider", DEFAULT_PROVIDER)
    user_key = settings.get("api_key", "").strip()
    if user_key:
        return user_key

    # Try to get API key from secrets based on provider
    secret_keys = {
        "gemini": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
    }

    secret_name = secret_keys.get(provider)
    if secret_name:
        try:
            return st.secrets.get(secret_name)
        except (FileNotFoundError, KeyError):
            logger.debug(f"Secret '{secret_name}' not found for provider {provider}")
            return None
    return None


def _get_tier(settings: dict) -> str:
    """Determine user's tier: 'free' or 'byok'."""
    if settings.get("api_key", "").strip():
        return "byok"
    return "free"


def _migrate_stale_settings(settings: dict) -> dict:
    """Auto-fix deprecated model names in saved settings."""
    model = settings.get("model", "")
    if model in _RETIRED_MODELS:
        settings["model"] = _RETIRED_MODELS[model]
        save_chat_settings(settings)
        logger.info(f"Migrated stale model {model} → {settings['model']}")
    # Also check if saved model is still in available list for the provider
    provider = settings.get("provider", DEFAULT_PROVIDER)
    available = AVAILABLE_MODELS.get(provider, [])
    if settings.get("model") and settings["model"] not in available and settings["model"] not in _RETIRED_MODELS:
        settings["model"] = DEFAULT_MODELS.get(provider, available[0] if available else "")
        save_chat_settings(settings)
        logger.info(f"Reset unavailable model to default for {provider}")
    return settings


def _init_chat_state():
    """Initialize chat-related session state."""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = load_chat_history()
    if "chat_settings" not in st.session_state:
        settings = load_chat_settings()
        st.session_state.chat_settings = _migrate_stale_settings(settings)
    if "chat_processing" not in st.session_state:
        st.session_state.chat_processing = False


def _handle_tool_calls(
    tool_calls: list[dict],
    messages: list[dict],
    provider: str,
    api_key: str,
    model: str | None,
    base_url: str | None,
) -> str:
    """Execute tool calls and get final response."""
    logger.info(f"Handling {len(tool_calls)} tool calls")

    messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})

    for tc in tool_calls:
        func_name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
        except json.JSONDecodeError:
            args = {}

        logger.info(f"Executing tool: {func_name} with args: {args}")
        result = execute_tool(func_name, args)
        logger.info(f"Tool result: {str(result)[:200]}...")

        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "name": func_name,
            "content": format_tool_result(result),
        })

    # Stream the final response after tool execution (pure text, no tools)
    final_response = ""
    try:
        for chunk in chat_completion(
            messages=messages,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            tools=None,
            stream=True,
        ):
            if isinstance(chunk, str):
                final_response += chunk
            elif isinstance(chunk, dict) and chunk.get("content"):
                final_response += chunk["content"]
    except Exception as e:
        logger.error(f"Error getting final response: {e}")
        final_response = f"I encountered an error processing the tool results: {str(e)}"

    return final_response


# Server-side session limit (not bypassable by clearing localStorage)
SESSION_MESSAGE_LIMIT = 100


def _check_session_limit() -> bool:
    """Check and increment server-side session counter. Returns True if allowed."""
    count = st.session_state.get("_chat_session_count", 0)
    if count >= SESSION_MESSAGE_LIMIT:
        return False
    st.session_state["_chat_session_count"] = count + 1
    return True


# --------------- Conversation memory management ---------------

# Rough token estimate: ~4 chars per token for English text
_CHARS_PER_TOKEN = 4
# Keep context window under this (leaves room for system prompt + response)
_MAX_CONTEXT_TOKENS = 6000
_SYSTEM_PROMPT_TOKENS = 2500  # estimated


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _trim_messages_for_context(messages: list[dict]) -> list[dict]:
    """Keep the system prompt + as many recent messages as fit in the token budget."""
    if not messages:
        return messages

    # System prompt is always messages[0]
    system = messages[:1]
    conversation = messages[1:]

    budget = _MAX_CONTEXT_TOKENS - _SYSTEM_PROMPT_TOKENS
    kept: list[dict] = []
    total = 0

    # Walk backwards (most recent first) and keep what fits
    for msg in reversed(conversation):
        tokens = _estimate_tokens(msg.get("content", "") or "")
        if total + tokens > budget:
            break
        kept.append(msg)
        total += tokens

    kept.reverse()
    return system + kept


# --------------- Analytics tracking ---------------

from .analytics import track_event as _track_event  # noqa: E402


# --------------- Message processing ---------------

def _process_message(prompt: str, settings: dict, api_key: str) -> str | None:
    """Process a user message and get response. Returns the response text."""
    # Note: User message is already added by render_chat_in_sidebar before calling this

    tier = _get_tier(settings)

    # Rate limits only apply to free tier (shared API key)
    if tier == "free":
        if not _check_session_limit():
            msg = "You've reached the session limit. Please refresh the page or add your own API key for unlimited access."
            st.session_state.chat_messages.append({"role": "assistant", "content": msg})
            save_chat_history(st.session_state.chat_messages)
            return msg
        increment_message_count()

    provider = settings.get("provider", DEFAULT_PROVIDER)
    model = settings.get("model") or DEFAULT_MODELS.get(provider)
    base_url = settings.get("ollama_url") if provider == "ollama" else None

    # Build messages with dynamic system prompt, then trim for context window
    system_prompt = _build_system_prompt()
    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.chat_messages:
        if msg["role"] in ("user", "assistant") and msg.get("content"):
            api_messages.append({"role": msg["role"], "content": msg["content"]})
    api_messages = _trim_messages_for_context(api_messages)

    response_text = ""
    tool_calls_result = None
    clean_messages = list(api_messages)

    _track_event("message", provider=provider, model=model, role="user")

    try:
        # Non-streaming for tool parsing; post-tool follow-up uses streaming
        for chunk in chat_completion(
            messages=api_messages,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            tools=TOOLS,
            stream=False,  # First call with tools must be non-streaming for tool parsing
        ):
            if isinstance(chunk, str):
                response_text += chunk
            elif isinstance(chunk, dict):
                if chunk.get("tool_calls"):
                    tool_calls_result = chunk
                elif chunk.get("content"):
                    response_text += chunk["content"]

        # Handle tool calls if present
        if tool_calls_result and tool_calls_result.get("tool_calls"):
            for tc in tool_calls_result["tool_calls"]:
                _track_event("tool_call", tool=tc["function"]["name"])
            response_text = _handle_tool_calls(
                tool_calls=tool_calls_result["tool_calls"],
                messages=api_messages,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

    except Exception as e:
        logger.error(f"Error in _process_message: {e}", exc_info=True)
        _track_event("error", error=str(e)[:200])
        response_text = f"Sorry, I encountered an error: {str(e)}"

    # Fallback: retry without tools using clean (un-mutated) messages
    if not response_text:
        logger.warning("Empty response — retrying without tools")
        try:
            for chunk in chat_completion(
                messages=clean_messages,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                tools=None,
                stream=False,
            ):
                if isinstance(chunk, str):
                    response_text += chunk
                elif isinstance(chunk, dict) and chunk.get("content"):
                    response_text += chunk["content"]
        except Exception as e:
            logger.error(f"Retry also failed: {e}")
            _track_event("error", error=f"retry_failed: {e}")
            response_text = f"Sorry, I'm having trouble connecting to {provider}. Please try again."

    # Clean up repetition artifacts from LLM output, then save
    if response_text:
        response_text = _dedup_sentences(response_text)
    if response_text:
        st.session_state.chat_messages.append({"role": "assistant", "content": response_text})
        save_chat_history(st.session_state.chat_messages)
        _track_event("message", provider=provider, model=model, role="assistant")
        return response_text
    else:
        error_msg = "I didn't receive a response. Please try again."
        st.session_state.chat_messages.append({"role": "assistant", "content": error_msg})
        save_chat_history(st.session_state.chat_messages)
        _track_event("error", error="empty_response")
        return error_msg


def _dedup_sentences(text: str) -> str:
    """Remove consecutively repeated sentences from LLM output.

    Conservative approach: only catches exact consecutive duplicate chunks
    of 5+ words.  Does NOT try to normalize punctuation, so abbreviations
    like 'U.S.' or 'Dr. Smith' are never mangled.
    """
    import re
    # Match a sentence-like chunk (5+ words ending in punctuation) that is
    # immediately repeated — with or without whitespace between copies.
    # The backreference \\1 catches exact duplicates.
    text = re.sub(
        r'((?:\S+\s+){4,}\S+[.!?])\s*\1',
        r'\1',
        text,
    )
    return text


def _md_to_html(text: str) -> str:
    """Convert basic markdown to HTML, escaping everything else for safety."""
    import html as _html
    import re

    # Escape HTML entities first
    text = _html.escape(text)
    # Bold: **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Line breaks
    text = text.replace("\n", "<br>")
    return text


def _render_message(label: str, content: str, *, is_user: bool) -> None:
    """Render a single chat message as styled HTML — no avatars, full width."""
    body = _md_to_html(content)
    if is_user:
        label_color = "#64748B"
        bg = "#F1F5F9"
        border_color = "#CBD5E1"
    else:
        label_color = "#2563EB"
        bg = "#FFFFFF"
        border_color = "#BFDBFE"

    st.markdown(
        f'<div style="margin-bottom:0.625rem; padding:0.5rem 0.625rem;'
        f'background:{bg}; border:1px solid {border_color}; border-radius:6px;">'
        f'<div style="font-size:0.7rem; font-weight:600; color:{label_color};'
        f'text-transform:uppercase; letter-spacing:0.04em; margin-bottom:0.25rem;">'
        f'{label}</div>'
        f'<div style="font-size:0.85rem; line-height:1.5; color:#1E293B;">'
        f'{body}</div></div>',
        unsafe_allow_html=True,
    )


def render_chat_in_sidebar():
    """Render the chat interface in the sidebar.

    Call this at the TOP of the sidebar, before other inputs.
    """
    _init_chat_state()

    settings = st.session_state.chat_settings
    tier = _get_tier(settings)
    api_key = _get_api_key(settings)

    # Chat styling + sidebar scroll anchor
    st.markdown("""
    <style>
        /* Clean chat input border */
        [data-testid="stSidebar"] [data-testid="stChatInput"] > div {
            border-color: #E2E8F0;
        }
        [data-testid="stSidebar"] [data-testid="stChatInput"]:focus-within > div {
            border-color: #2563EB;
        }
        /* Shrink chat container on mobile */
        @media (max-width: 768px) {
            [data-testid="stSidebar"] .stVerticalBlockBorderWrapper
            > div[style*="overflow"] {
                max-height: 200px !important;
            }
        }
        /* Force sidebar to stay scrolled to top on re-render */
        [data-testid="stSidebarContent"] {
            scroll-snap-type: y mandatory;
        }
        [data-testid="stSidebarUserContent"] > div:first-child {
            scroll-snap-align: start;
        }
    </style>
    """, unsafe_allow_html=True)

    # Determine if chat can send (needed before rendering messages for onboarding buttons)
    can_send = True
    warning_msg = None
    session_count = st.session_state.get("_chat_session_count", 0)

    if not api_key:
        provider = settings.get("provider", DEFAULT_PROVIDER)
        if provider == "ollama":
            warning_msg = "Can't reach Ollama — is it running?"
        else:
            warning_msg = "Add an API key in settings below to get started"
        can_send = False
    elif tier == "free" and session_count >= SESSION_MESSAGE_LIMIT:
        warning_msg = "Session limit reached — refresh or add your own key"
        can_send = False
    elif tier == "free" and is_free_tier_exhausted():
        warning_msg = "Daily limit reached — add your own key for unlimited"
        can_send = False

    # Header with clear button
    header_col1, header_col2 = st.sidebar.columns([5, 1])
    with header_col1:
        st.markdown(
            '<p style="font-weight: 600; font-size: 0.9rem; color: #0F172A; '
            'margin: 0; padding-bottom: 0.5rem; border-bottom: 1px solid #E2E8F0;">'
            'Planning Advisor</p>',
            unsafe_allow_html=True,
        )
    with header_col2:
        if st.button("×", key="clear_chat_btn", help="Clear conversation"):
            _track_event("button_click", button="chat_cleared")
            clear_chat_history()
            st.session_state.chat_messages = []
            st.rerun()

    # Messages container
    with st.sidebar.container(height=320):
        if not st.session_state.chat_messages:
            st.markdown(
                '<div style="color: #475569; font-size: 0.85rem; padding: 0.5rem 0;'
                'line-height: 1.6;">'
                '<strong style="color: #0F172A;">Welcome</strong><br><br>'
                'I can help you build and optimize your retirement plan.'
                '</div>',
                unsafe_allow_html=True,
            )
            # Quick-start buttons for common first actions
            if can_send:
                if st.button("Set up my plan", key="onboard_setup", use_container_width=True):
                    _track_event("button_click", button="onboard_setup")
                    onboard_prompt = "Help me set up my retirement plan. Ask me one question at a time, starting with the basics."
                    st.session_state.chat_messages.append({"role": "user", "content": onboard_prompt})
                    save_chat_history(st.session_state.chat_messages)
                    _process_message(onboard_prompt, settings, api_key)
                    st.rerun()
                if st.button("Review my current plan", key="onboard_review", use_container_width=True):
                    _track_event("button_click", button="onboard_review")
                    review_prompt = "Review my current retirement plan and tell me how it looks."
                    st.session_state.chat_messages.append({"role": "user", "content": review_prompt})
                    save_chat_history(st.session_state.chat_messages)
                    _process_message(review_prompt, settings, api_key)
                    st.rerun()
        else:
            for msg in st.session_state.chat_messages:
                if msg["role"] == "user":
                    _render_message("You", msg["content"], is_user=True)
                elif msg["role"] == "assistant" and msg.get("content"):
                    _render_message("Advisor", msg["content"], is_user=False)

        # Scroll chat container to bottom (CSS-only, no iframe)
        if st.session_state.chat_messages:
            st.markdown(
                '<div style="height:0;overflow:hidden;" id="chat-bottom"></div>'
                '<style>#chat-bottom { scroll-margin-top: 9999px; }</style>',
                unsafe_allow_html=True,
            )

    if warning_msg:
        st.sidebar.caption(f"⚠️ {warning_msg}")

    # Chat input
    prompt = st.sidebar.chat_input(
        placeholder="Ask about your plan...",
        disabled=not can_send,
        key="sidebar_chat_input",
    )

    # Single-phase: process immediately, then rerun once to show response
    if prompt and prompt.strip():
        st.session_state.chat_messages.append({"role": "user", "content": prompt.strip()})
        save_chat_history(st.session_state.chat_messages)
        _process_message(prompt.strip(), settings, api_key)
        st.rerun()

    # Visual separator between chat section and actions
    st.sidebar.markdown(
        '<div style="border-top: 2px solid #E2E8F0; margin: 0.5rem 0;"></div>',
        unsafe_allow_html=True,
    )

    # Prominent CTA button
    with st.sidebar.container():
        if st.button(
            "Find my earliest safe retirement",
            key="chat_safe_target_btn",
            use_container_width=True,
            help=(
                "Runs a stress test to find the earliest age you can retire "
                "where your money lasts through your full plan — checks both "
                "your specific situation AND 95%+ of historical market conditions "
                "(1928–2024)."
            ),
        ):
            from .chat_tools import find_safe_target as _chat_find_safe_target
            from .widgets import format_money

            _track_event("button_click", button="find_safe_target_chat")
            with st.spinner("Running stress tests..."):
                result = _chat_find_safe_target()

            if result.get("found"):
                target_fmt = result.get("recommended_target_formatted", "")
                msg = (
                    f"Based on your current inputs, the earliest you could safely retire is "
                    f"**age {result['retirement_age_at_target']}** with a target of "
                    f"**{target_fmt}**.\n\n"
                    f"This passes both a deterministic projection with your specific "
                    f"healthcare and tax assumptions, and **{result['monte_carlo_success_rate']:.0%}** "
                    f"of all historical market sequences from 1928–2024.\n\n"
                    f"Would you like me to explain what this means or explore ways to retire earlier?"
                )
                # Also update the actual retirement target in the plan
                if result.get("recommended_target"):
                    st.session_state.inputs["in_RetirementTarget"] = result["recommended_target"]
                    st.session_state["retirement_target"] = float(result["recommended_target"])
            else:
                msg = result.get("note", "Could not find a safe retirement target in the search range.")

            st.session_state.chat_messages.append({"role": "assistant", "content": msg})
            save_chat_history(st.session_state.chat_messages)
            st.rerun()

    # Auto-expand settings when chat can't work (no key, exhausted, etc.)
    settings_expanded = not can_send

    # Settings expander
    with st.sidebar.expander("Chat settings", expanded=settings_expanded):
        # Tier info
        if tier == "free":
            remaining_daily = get_remaining_free_messages()
            remaining_session = max(0, SESSION_MESSAGE_LIMIT - session_count)
            remaining = min(remaining_daily, remaining_session)
            st.caption(f"Free tier: {remaining} messages remaining")
        else:
            st.caption("Using your API key (unlimited)")

        # Provider selection with friendly labels
        provider_options = ["groq", "gemini", "openai", "ollama"]
        provider_labels = [PROVIDER_LABELS.get(p, p) for p in provider_options]
        current_provider = settings.get("provider", DEFAULT_PROVIDER)
        current_idx = provider_options.index(current_provider) if current_provider in provider_options else 0

        new_provider_label = st.selectbox(
            "Provider",
            options=provider_labels,
            index=current_idx,
            key="chat_provider_select",
        )
        new_provider = provider_options[provider_labels.index(new_provider_label)]

        # Model selection based on provider
        available_models = AVAILABLE_MODELS.get(new_provider, [])
        current_model = settings.get("model") or DEFAULT_MODELS.get(new_provider)
        model_index = 0
        if current_model in available_models:
            model_index = available_models.index(current_model)

        new_model = st.selectbox(
            "Model",
            options=available_models,
            index=model_index,
            key="chat_model_select",
        )

        # API key input with provider-specific guidance
        key_label = "API Key" if new_provider != "ollama" else "API Key (not needed)"
        new_api_key = st.text_input(
            key_label,
            value=settings.get("api_key", ""),
            type="password",
            key="chat_api_key_input",
            help="Add your own API key for unlimited messages",
        )
        # Show where to get a key
        help_text = API_KEY_HELP.get(new_provider, "")
        if help_text:
            st.caption(help_text)

        new_ollama_url = None
        if new_provider == "ollama":
            new_ollama_url = st.text_input(
                "Ollama URL",
                value=settings.get("ollama_url", "http://localhost:11434"),
                key="chat_ollama_url_input",
            )

        if st.button("Save settings", key="chat_save_settings", use_container_width=True):
            _track_event("button_click", button="chat_settings_saved",
                         provider=new_provider, model=new_model,
                         has_api_key=bool(new_api_key))
            new_settings = {
                "provider": new_provider,
                "model": new_model,
                "api_key": new_api_key,
            }
            if new_provider == "ollama" and new_ollama_url:
                new_settings["ollama_url"] = new_ollama_url
            save_chat_settings(new_settings)
            st.session_state.chat_settings = new_settings
            st.rerun()

    # Divider after chat section
    st.sidebar.markdown("---")


# Keep the old function name for backwards compatibility during transition
def render_chat_widget():
    """Legacy function - now renders in sidebar instead of floating."""
    render_chat_in_sidebar()
