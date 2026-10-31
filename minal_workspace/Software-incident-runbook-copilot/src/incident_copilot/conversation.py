from __future__ import annotations


def build_incident_context(messages: list[dict[str, object]]) -> str:
    """Keep the initial report and clarification answers together for each triage turn."""
    turns: list[tuple[str, list[str]]] = []
    pending_questions: list[str] = []
    for message in messages:
        if message.get("role") == "assistant":
            response = message.get("response")
            if isinstance(response, dict):
                questions = response.get("clarifying_questions", [])
                pending_questions = [str(item) for item in questions] if isinstance(questions, list) else []
        elif message.get("role") == "user":
            content = str(message.get("content", "")).strip()
            if content:
                turns.append((content, pending_questions))
                pending_questions = []

    if not turns:
        return ""
    if len(turns) == 1:
        return turns[0][0]

    context = [f"Latest user update:\n{turns[-1][0]}", "Conversation so far:"]
    for index, (content, questions) in enumerate(turns):
        if index == 0:
            context.append(f"Initial incident report:\n{content}")
        else:
            if questions:
                context.append("Assistant asked:\n" + "\n".join(f"- {question}" for question in questions))
            context.append(f"User follow-up:\n{content}")
    return "\n\n".join(context)
