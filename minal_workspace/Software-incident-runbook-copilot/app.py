from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from incident_copilot.config import Settings
from incident_copilot.chat_history import ChatHistoryStore
from incident_copilot.conversation import build_incident_context
from incident_copilot.models import Citation, CitedStatement, TriageResponse
from incident_copilot.runtime import build_agent


SETTINGS = Settings.from_environment()
CHAT_HISTORY = ChatHistoryStore(Path(os.getenv(
    "INCIDENT_CHAT_HISTORY_DIR", str(SETTINGS.corpus_path.parent / "artifacts" / "chats")
)))
st.set_page_config(page_title="Incident Copilot", page_icon="🛟", layout="centered")


def telemetry_cache_version() -> tuple[tuple[str, int], ...]:
    return tuple(sorted(
        (path.name, path.stat().st_mtime_ns)
        for path in (SETTINGS.corpus_path / "telemetry").glob("*.json")
    ))


@st.cache_resource
def get_agent(cache_version: tuple[tuple[str, int], ...]):
    # Snapshot file changes rebuild the cached agent without discarding open chats.
    return build_agent(SETTINGS)


def render_statement(statement: CitedStatement, *, emphasize_summary: bool = False) -> None:
    if not statement.text:
        return
    text = statement.text
    if emphasize_summary:
        text = text.replace("Likely root cause:", "**Likely root cause:**", 1)
        text = text.replace("Possible fix:", "**Possible fix:**", 1)
    st.markdown(text)
    for citation in statement.citations:
        st.caption(f"Source: {citation.reference} · `{citation.source_path}`")


def render_response(response: TriageResponse) -> None:
    render_statement(response.summary, emphasize_summary=True)

    if response.clarifying_questions:
        st.markdown("**To continue, tell me:**")
        for question in response.clarifying_questions:
            st.markdown(f"- {question}")

    has_details = any((
        response.observations, response.likely_causes, response.missing_evidence,
        response.recommended_checks, response.recovery_options, response.escalation.text,
    ))
    if has_details:
        with st.expander("Evidence and next steps"):
            _render_statements("Observed evidence", response.observations)
            _render_statements("Possible causes", response.likely_causes)
            if response.missing_evidence:
                st.markdown("**Evidence gaps**")
                for gap in response.missing_evidence:
                    st.markdown(f"- {gap}")
            _render_statements("Recommended checks", response.recommended_checks)
            _render_statements("Possible recovery options", response.recovery_options)
            if response.escalation.text:
                st.markdown("**Escalation**")
                render_statement(response.escalation)


def _render_statements(title: str, statements: list[CitedStatement]) -> None:
    if statements:
        st.markdown(f"**{title}**")
        for statement in statements:
            render_statement(statement)


def response_from_dict(data: dict) -> TriageResponse:
    return TriageResponse(
        summary=_statement_from_dict(data["summary"]),
        observations=[_statement_from_dict(item) for item in data["observations"]],
        likely_causes=[_statement_from_dict(item) for item in data["likely_causes"]],
        missing_evidence=data["missing_evidence"],
        recommended_checks=[_statement_from_dict(item) for item in data["recommended_checks"]],
        recovery_options=[_statement_from_dict(item) for item in data["recovery_options"]],
        escalation=_statement_from_dict(data["escalation"]),
        clarifying_questions=data["clarifying_questions"],
        needs_clarification=data["needs_clarification"],
    )


def _statement_from_dict(data: dict) -> CitedStatement:
    return CitedStatement(
        text=data.get("text", ""),
        citations=[Citation(**item) for item in data.get("citations", [])],
    )


def render_chat_sidebar() -> None:
    st.session_state.setdefault("pending_chat_delete", None)
    chats = CHAT_HISTORY.list_chats()
    with st.sidebar:
        st.header("Chats")
        if st.button("New chat", use_container_width=True):
            st.session_state["active_chat_id"] = None
            st.session_state["messages"] = []
            st.session_state["pending_chat_delete"] = None
            st.rerun()

        for chat in chats:
            title_column, delete_column = st.columns([5, 1], gap="small")
            with title_column:
                if st.button(chat["title"], key=f"chat_{chat['id']}", use_container_width=True,
                             type="primary" if chat["id"] == st.session_state["active_chat_id"] else "secondary"):
                    saved_chat = CHAT_HISTORY.load_chat(chat["id"])
                    st.session_state["active_chat_id"] = chat["id"]
                    st.session_state["messages"] = saved_chat["messages"]
                    st.session_state["pending_chat_delete"] = None
                    st.rerun()
            with delete_column:
                if st.button("🗑", key=f"delete_{chat['id']}", help=f"Delete {chat['title']}"):
                    st.session_state["pending_chat_delete"] = chat["id"]
                    st.rerun()

        if chats:
            with st.expander("Manage history"):
                if st.button("Delete all chats", use_container_width=True):
                    st.session_state["pending_chat_delete"] = "all"
                    st.rerun()

        pending = st.session_state["pending_chat_delete"]
        if pending:
            title = next((chat["title"] for chat in chats if chat["id"] == pending), None)
            if pending == "all":
                st.warning("Delete all saved chats? This cannot be undone.")
            elif title:
                st.warning(f"Delete ‘{title}’? This cannot be undone.")
            else:
                st.session_state["pending_chat_delete"] = None
                st.rerun()

            confirm_column, cancel_column = st.columns(2)
            with confirm_column:
                if st.button("Confirm delete", use_container_width=True):
                    if pending == "all":
                        CHAT_HISTORY.delete_all_chats()
                        st.session_state["active_chat_id"] = None
                        st.session_state["messages"] = []
                    else:
                        CHAT_HISTORY.delete_chat(pending)
                        if st.session_state["active_chat_id"] == pending:
                            st.session_state["active_chat_id"] = None
                            st.session_state["messages"] = []
                    st.session_state["pending_chat_delete"] = None
                    st.rerun()
            with cancel_column:
                if st.button("Cancel", use_container_width=True):
                    st.session_state["pending_chat_delete"] = None
                    st.rerun()

        st.caption("Saved locally on this machine.")


def main() -> None:
    if "active_chat_id" not in st.session_state:
        existing_messages = st.session_state.get("messages", [])
        if existing_messages:
            st.session_state["active_chat_id"] = CHAT_HISTORY.save_chat(existing_messages)
        else:
            latest_chat = next(iter(CHAT_HISTORY.list_chats()), None)
            st.session_state["active_chat_id"] = latest_chat["id"] if latest_chat else None
            st.session_state["messages"] = (
                CHAT_HISTORY.load_chat(latest_chat["id"])["messages"] if latest_chat else []
            )

    render_chat_sidebar()

    st.title("Incident Copilot")
    st.caption("Cited, read-only guidance from indexed runbooks and the details you provide.")

    last_message = st.session_state["messages"][-1] if st.session_state["messages"] else None
    has_questions = bool(last_message and last_message.get("role") == "assistant"
                         and last_message.get("response", {}).get("clarifying_questions"))
    placeholder = ("Answer the question or add evidence…" if has_questions
                   else "Share the incident details or paste an alert…")
    prompt = st.chat_input(placeholder)

    if prompt and prompt.strip():
        st.session_state["messages"].append({"role": "user", "content": prompt})
        incident_context = build_incident_context(st.session_state["messages"])
        try:
            with st.spinner("Reviewing the evidence…"):
                response = get_agent(telemetry_cache_version()).triage(incident_context)
            st.session_state["messages"].append({"role": "assistant", "response": response.to_dict()})
        except Exception as error:
            st.session_state["messages"].append({
                "role": "assistant", "error": f"Triage is unavailable: {error}",
            })
        st.session_state["active_chat_id"] = CHAT_HISTORY.save_chat(
            st.session_state["messages"], st.session_state["active_chat_id"]
        )
        st.rerun()

    if not st.session_state["messages"]:
        st.subheader("What happened?")
        st.write(
            "Describe the alert and share the evidence you have: symptoms, service, environment, "
            "time window, metrics, and recent changes. You can add details as we investigate."
        )
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            elif "error" in message:
                st.error(message["error"])
            else:
                render_response(response_from_dict(message["response"]))


if __name__ == "__main__":
    main()
