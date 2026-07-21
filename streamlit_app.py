"""F1 Historical Intelligence Agent — Streamlit in Snowflake."""

import json
import logging
from typing import Any, Optional

import streamlit as st
from snowflake.snowpark.context import get_active_session


AGENT_NAME = "YOUR_DATABASE.YOUR_SCHEMA.F1_HISTORICAL_AGENT"
EXAMPLE_PROMPTS = (
    "Did it rain during the 1998 Belgian Grand Prix?",
    "Compare the careers of Michael Schumacher and Lewis Hamilton fairly.",
    "Was it a wet track at the 2023 Bahrain Grand Prix?",
    "Who won the 2023 Belgian Grand Prix and what was the weather like?",
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)
session = get_active_session()


def main() -> None:
    """Render the application and process one interaction per rerun."""
    st.set_page_config(
        page_title="F1 Historical Intelligence Agent",
        page_icon="🏎️",
        layout="wide",
    )
    initialize_state()
    show_header_and_sidebar()
    display_conversation()
    handle_user_input()


def initialize_state() -> None:
    """Create chat state on the first application run."""
    if "messages" not in st.session_state:
        st.session_state.messages = []


def reset_conversation() -> None:
    """Clear chat history and start a new conversation."""
    st.session_state.messages = []


def show_header_and_sidebar() -> None:
    """Render the title, project summary, examples, and controls."""
    st.title("🏎️ F1 Historical Intelligence Agent")
    st.markdown(
        "Ask about historical drivers, race results, circuit characteristics, "
        "era-normalized performance, or race-day weather."
    )

    with st.sidebar:
        st.markdown(f"**Active agent:** `{AGENT_NAME.split('.')[-1]}`")
        st.divider()
        st.markdown("**Try asking:**")
        for prompt in EXAMPLE_PROMPTS:
            st.markdown(f"- *{prompt}*")
        st.divider()
        st.caption(
            "Guardrail: broad all-time weather leaderboards are restricted to "
            "avoid expensive external API mapping loops."
        )
        if st.button("Clear chat history", use_container_width=True):
            reset_conversation()
            st.rerun()


def handle_user_input() -> None:
    """Send a new user prompt to the configured Cortex Agent."""
    prompt = st.chat_input("Ask about F1 history or race weather…")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consulting the historical data…"):
            response = call_agent()
        if response:
            st.session_state.messages.append(
                {"role": "assistant", "content": response}
            )
            render_message(response)
        else:
            st.error("The agent could not return a response. Please try again.")


def call_agent() -> Optional[str]:
    """Call a Snowflake Cortex Agent through DATA_AGENT_RUN."""
    request_body = {
        "messages": [
            {
                "role": message["role"],
                "content": [{"type": "text", "text": message["content"]}],
            }
            for message in st.session_state.messages
        ],
        "stream": False,
    }

    try:
        rows = session.sql(
            """
            SELECT TRY_PARSE_JSON(
                SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?)
            ) AS RESPONSE
            """,
            params=[AGENT_NAME, json.dumps(request_body)],
        ).collect()

        if not rows or rows[0]["RESPONSE"] is None:
            return None
        return extract_response_text(rows[0]["RESPONSE"])
    except Exception:
        LOGGER.exception("Cortex Agent request failed")
        return None


def extract_response_text(response: Any) -> str:
    """Extract user-facing text from current and legacy response shapes."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return response

    text_parts: list[str] = []
    collect_text_blocks(response, text_parts)
    unique_parts = list(dict.fromkeys(part.strip() for part in text_parts if part.strip()))
    return "\n\n".join(unique_parts) or "No response content was returned."


def collect_text_blocks(value: Any, output: list[str]) -> None:
    """Recursively collect text blocks while ignoring internal reasoning fields."""
    if isinstance(value, list):
        for item in value:
            collect_text_blocks(item, output)
        return

    if not isinstance(value, dict):
        return

    block_type = value.get("type")
    if block_type in {"text", "output_text"} and isinstance(value.get("text"), str):
        output.append(value["text"])

    for key in ("message", "content", "choices", "response", "output"):
        if key in value:
            collect_text_blocks(value[key], output)


def display_conversation() -> None:
    """Render all messages stored in the current Streamlit session."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            render_message(message["content"])


def render_message(content: str) -> None:
    """Render Markdown and collapse SQL snippets for readability."""
    segments = content.split("```sql")
    if len(segments) == 1:
        st.markdown(content)
        return

    if segments[0].strip():
        st.markdown(segments[0])

    for segment in segments[1:]:
        sql_code, separator, remainder = segment.partition("```")
        with st.expander("Pit wall data query (SQL)", expanded=False):
            st.code(sql_code.strip(), language="sql")
            st.caption("Displayed for transparency; not executed by the UI.")
        if separator and remainder.strip():
            st.markdown(remainder)


if __name__ == "__main__":
    main()
