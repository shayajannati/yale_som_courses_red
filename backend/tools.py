"""Agent tools.

search_courses does semantic search over data/yale_som.db. There is no keyword
filter and no embeddings/vector store: the course list is small (~234 rows), so
the whole catalog is handed to the LLM itself, which reads it and ranks courses
by meaning. This means paraphrases and related concepts work (e.g. "courses
about persuading customers"), at the cost of one extra model call per search.

web_search is OpenAI's native web search tool, attached to the agent in agent.py.
"""

from __future__ import annotations

import functools
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from models import CourseSearchResult

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "data" / "yale_som.db"
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

MODEL_NAME = "gpt-5.6-luna"
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")
MAX_RESULTS = 15

_RANK_SCHEMA = {
    "type": "json_schema",
    "name": "course_ranking",
    "schema": {
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Course row ids, most relevant to the query first.",
            }
        },
        "required": ["ids"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _client() -> OpenAI:
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set (put it in a .env file).")
    return OpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
    )


@functools.lru_cache(maxsize=1)
def _load_courses() -> tuple[dict, ...]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM courses").fetchall()
    con.close()
    return tuple(dict(row) for row in rows)


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _catalog_line(row: dict) -> str:
    """One line per course for the ranking prompt: id | number title | category/type | faculty | day+time | units."""
    title = _clip(row["course_title"], 90)
    return (
        f"{row['id']} | {row['course_number']} {title} | "
        f"{row['course_category']}/{row['course_type']} | {row['faculty_1'] or 'TBA'} | "
        f"{row['daytimes'] or 'TBA'} | {row['units']}u"
    )


def _course_summary(row: dict) -> dict[str, str]:
    return {
        "number": row["course_number"],
        "section": row["section"],
        "title": row["course_title"],
        "faculty": row["faculty_1"],
        "category": row["course_category"],
        "type": row["course_type"],
        "session": row["course_session"],
        "day_time": row["daytimes"] or "TBA",
        "room": row["room"] or "TBA",
        "units": row["units"],
        "syllabus": row["syllabus"] or row["old_syllabus"],
        "description": _clip(row["course_description"], 500),
        "faculty_bio": _clip(row["faculty_bio"], 300),
    }


def search_courses(query: str, limit: int = MAX_RESULTS) -> CourseSearchResult:
    """Semantically search the Yale SOM course list (data/yale_som.db).

    This ranks courses by meaning, not keyword overlap — an LLM reads the whole
    catalog and picks what genuinely matches, so related concepts and paraphrases
    work even if they don't share exact words with the course text.

    Args:
        query: A natural-language description of what the student wants — a topic,
            a professor, a schedule, a category, or any mix of these.
        limit: Maximum courses to return (capped at 15).
    """
    limit = max(1, min(limit, MAX_RESULTS))
    courses = _load_courses()
    catalog = "\n".join(_catalog_line(row) for row in courses)
    prompt = (
        "Catalog (one course per line, `id | number title | category/type | faculty | "
        f"day+time | units`):\n{catalog}\n\n"
        f"Query: {query!r}\n\n"
        f"Return the ids of the courses that genuinely match this query, ranked most "
        f"relevant first, at most {limit} of them. Return fewer than {limit} if fewer "
        "genuinely match — never pad the list with irrelevant courses."
    )

    try:
        response = _client().responses.create(
            model=MODEL_NAME,
            input=[
                {
                    "role": "system",
                    "content": "You rank Yale SOM courses by semantic relevance to a search query.",
                },
                {"role": "user", "content": prompt},
            ],
            text={"format": _RANK_SCHEMA},
        )
        ids = json.loads(response.output_text)["ids"]
    except Exception as exc:
        return CourseSearchResult(
            total_matches=0,
            returned=0,
            note=f"Semantic search failed: {type(exc).__name__}: {exc}",
        )

    by_id = {row["id"]: row for row in courses}
    matched = [by_id[i] for i in ids if i in by_id][:limit]
    return CourseSearchResult(
        total_matches=len(matched),
        returned=len(matched),
        note="" if matched else "No courses matched that query semantically.",
        courses=[_course_summary(row) for row in matched],
    )
