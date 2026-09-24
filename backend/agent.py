"""Yale SOM course agent: PydanticAI + gpt-5.6-luna through Portkey.

Tools: search_courses (tools.py) and web_search (OpenAI's native web search).
Every run is appended to output/audit_trail.json.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai import Agent
from pydantic_ai.capabilities import WebSearch
from pydantic_ai.messages import (
    BaseToolCallPart,
    BaseToolReturnPart,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from pydantic_core import to_json

from models import AgentResult
from tools import search_courses

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

MODEL_NAME = "gpt-5.6-luna"
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")
PROMPT_PATH = HERE / "prompts" / "prompt.md"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"
MAX_MODEL_REQUESTS = 20  # web_search often needs several rounds (open_page, search, refine)
RESULT_PREVIEW_CHARS = 300

_audit_lock = threading.Lock()


def _build_agent() -> Agent[None, str]:
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set (put it in a .env file).")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    return Agent(
        model,
        instructions=PROMPT_PATH.read_text(encoding="utf-8"),
        tools=[search_courses],
        capabilities=[WebSearch()],  # native OpenAI web search (no local fallback)
        model_settings=OpenAIResponsesModelSettings(openai_reasoning_summary="auto"),
    )


def _tool_label(name: str) -> str:
    """Native web-search calls show up under names like 'web_search' or 'web_search_call'."""
    return "web_search" if name.startswith("web_search") else name


def _preview(value: Any) -> str:
    text = value if isinstance(value, str) else to_json(value).decode("utf-8", "replace")
    text = " ".join(text.split())
    return text if len(text) <= RESULT_PREVIEW_CHARS else text[: RESULT_PREVIEW_CHARS - 1] + "…"


def _summarize_run(messages: list[Any]) -> tuple[list[str], list[dict[str, Any]], str]:
    """Pull thoughts, tool calls (name/args/short result) and the stop reason out of a run."""
    thoughts: list[str] = []
    calls: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    finish_reason: str | None = None

    last_response = max(
        (i for i, m in enumerate(messages) if isinstance(m, ModelResponse)), default=-1
    )
    for index, message in enumerate(messages):
        if isinstance(message, ModelResponse):
            finish_reason = message.finish_reason
            has_calls = any(isinstance(p, BaseToolCallPart) for p in message.parts)
            for part in message.parts:
                if isinstance(part, ThinkingPart) and part.content:
                    thoughts.append(part.content)
                elif isinstance(part, TextPart) and part.content:
                    # Text before a tool call is a "thought"; the last response's text is the reply.
                    if has_calls and index != last_response:
                        thoughts.append(part.content)
                elif isinstance(part, BaseToolCallPart):
                    entry = {
                        "tool": _tool_label(part.tool_name),
                        "args": part.args_as_dict(),
                        "result": None,
                    }
                    calls.append(entry)
                    by_id[part.tool_call_id] = entry
                elif isinstance(part, BaseToolReturnPart):
                    # Native tools (web search) return their result inside the model response.
                    entry = by_id.get(part.tool_call_id)
                    if entry is not None:
                        entry["result"] = _preview(part.content)
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, (BaseToolReturnPart, RetryPromptPart)):
                    entry = by_id.get(part.tool_call_id)
                    if entry is not None:
                        entry["result"] = _preview(part.content)

    reason = f"final answer (finish_reason={finish_reason or 'stop'})"
    return thoughts, calls, reason


def _append_audit(entry: dict[str, Any]) -> None:
    """Append one run to output/audit_trail.json without touching earlier rows."""
    with _audit_lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        rows: list[Any] = []
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size > 0:
            try:
                loaded = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
                rows = loaded if isinstance(loaded, list) else [loaded]
            except json.JSONDecodeError:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                AUDIT_PATH.replace(AUDIT_PATH.with_name(f"audit_trail.corrupt-{stamp}.json"))
        rows.append(entry)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(AUDIT_PATH)


def run_agent(message: str) -> dict:
    entry: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user_message": message,
        "model": MODEL_NAME,
        "thoughts": [],
        "tool_calls": [],
        "stopped": "",
        "reply": "",
    }
    try:
        run = _build_agent().run_sync(
            message, usage_limits=UsageLimits(request_limit=MAX_MODEL_REQUESTS)
        )
        thoughts, calls, stopped = _summarize_run(run.new_messages())
        tools_used = list(dict.fromkeys(c["tool"] for c in calls))
        result = AgentResult(reply=run.output, tools_used=tools_used)
        entry.update(thoughts=thoughts, tool_calls=calls, stopped=stopped, reply=result.reply)
    except Exception as exc:  # keep the chat alive; the audit trail records what happened
        detail = f"{type(exc).__name__}: {exc}"[:400]
        result = AgentResult(
            reply=f"Sorry, the course agent hit an error and could not answer. ({detail})"
        )
        entry.update(stopped=f"error: {detail}", reply=result.reply)
    _append_audit(entry)
    return result.model_dump()
