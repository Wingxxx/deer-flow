"""Role parser for LangGraph messages.

Extracts user queries, system prompts, and conversation history
from LangGraph message lists. Supports both role="user" and type="human"
message formats used by LangGraph.

WING
"""

from typing import Any


def extract_content(msg: Any) -> str:
    """Extract content from a message object or dict.

    Handles both LangGraph message objects (with content attribute)
    and dict messages.
    """
    if isinstance(msg, dict):
        content = msg.get("content", "")
    else:
        content = getattr(msg, "content", "") or ""
    return str(content) if content else ""


def get_role(msg: Any) -> str:
    """Get role from a message object or dict.

    LangGraph HumanMessage uses type="human" instead of role="user".
    We check both attributes for compatibility.
    """
    if isinstance(msg, dict):
        role = msg.get("type", "") or msg.get("role", "")
    else:
        role = getattr(msg, "type", "") or getattr(msg, "role", "")
    return str(role) if role else ""


def _should_extract_as_user(role: str, mode: str = "auto") -> bool:
    """Determine if a role should be treated as user role.

    Args:
        role: The role string to check
        mode: Extraction mode - "auto", "human", or "user"
            - "auto": Both "user" and "human" are treated as user
            - "human": Only "human" is treated as user
            - "user": Only "user" is treated as user

    Returns:
        True if the role should be extracted as user query
    """
    if mode == "auto":
        return role in ("user", "human")
    elif mode == "human":
        return role == "human"
    elif mode == "user":
        return role == "user"
    return role in ("user", "human")


def extract_user_query(messages: list, mode: str = "auto") -> str:
    """Extract the most recent user query from messages.

    Scans messages in order and returns the content of the last
    user/human message found. This is typically the current user input.

    Args:
        messages: List of LangGraph messages
        mode: Extraction mode - "auto", "human", or "user"

    Returns:
        The content of the most recent user message, or empty string
    """
    user_query = ""
    for msg in messages:
        role = get_role(msg)
        if _should_extract_as_user(role, mode):
            user_query = extract_content(msg)
    return user_query


def extract_system_prompt(messages: list) -> str:
    """Extract system prompt from messages.

    Returns the content of the first system message found.

    Args:
        messages: List of LangGraph messages

    Returns:
        The content of the system message, or empty string
    """
    for msg in messages:
        role = get_role(msg)
        if role == "system":
            return extract_content(msg)
    return ""


def extract_history(messages: list, exclude_current_query: bool = True) -> list:
    """Extract conversation history from messages.

    Args:
        messages: List of LangGraph messages
        exclude_current_query: If True, exclude the last user message
            (current query) from history

    Returns:
        List of history messages with role and content
    """
    history = []
    last_user_idx = -1
    last_user_content = ""

    for i, msg in enumerate(messages):
        role = get_role(msg)
        content = extract_content(msg)

        if role in ("user", "human"):
            last_user_idx = i
            last_user_content = content
        elif role == "system":
            continue
        else:
            history.append({"role": role, "content": content})

    if exclude_current_query and last_user_idx >= 0:
        pass

    return history[-4:] if len(history) > 4 else history


def parse_messages(messages: list, mode: str = "auto") -> dict:
    """Parse messages and extract structured data.

    Extracts user query, system prompt, and conversation history
    from a list of LangGraph messages.

    Args:
        messages: List of LangGraph messages
        mode: Extraction mode - "auto", "human", or "user"

    Returns:
        dict with keys:
            - user_query: str - the most recent user message content
            - system_prompt: str - the system prompt content
            - history: list - conversation history (excluding current query)
    """
    user_query = extract_user_query(messages, mode)
    system_prompt = extract_system_prompt(messages)
    history = extract_history(messages, exclude_current_query=True)

    return {
        "user_query": user_query,
        "system_prompt": system_prompt,
        "history": history,
    }
