"""CSV exports in exactly the shape the trivia database imports.

Column names and order below were taken from real exports out of the
database, including the columns this form doesn't collect (`flags`,
`difficulty`, the Ready, Bet, Go! explanations). Those go out empty
rather than being dropped, so a file from here lines up column-for-column
with a file from there.

`specialEventId` is filled from whatever a reviewer saved on the
submission, and is blank otherwise.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from app.games import GRADES, TEMPLE_LEVELS

# Each export is (slug, label, headers, row builder). A game can produce
# more than one file — The Grid splits into categories and the Wisdom
# Wager, which the database treats as separate imports.
Exports = dict[str, list[dict[str, Any]]]


def _rows_elementary(rows: list[dict[str, str]]) -> list[list[str]]:
    out = []
    for i in range(5):
        r = rows[i] if i < len(rows) else {}
        out.append([
            r.get("question", ""), GRADES[i], r.get("correct", ""), "",
            r.get("a", ""), r.get("b", ""), r.get("c", ""), r.get("d", ""),
            "", "", "",
        ])
    return out


def _rows_readybetgo(rows: list[dict[str, str]]) -> list[list[str]]:
    out = []
    for i in range(10):
        r = rows[i] if i < len(rows) else {}
        out.append([
            r.get("question", ""), r.get("a", ""), r.get("b", ""), r.get("c", ""),
            "N/A", "N/A", "N/A", r.get("correct", ""),
            "", "", "",
        ])
    return out


def _rows_temple(rows: list[dict[str, str]]) -> list[list[str]]:
    out = []
    for i in range(20):
        r = rows[i] if i < len(rows) else {}
        out.append([
            r.get("question", ""), r.get("a", ""), r.get("b", ""),
            r.get("c", ""), r.get("d", ""), r.get("correct", ""),
            str(TEMPLE_LEVELS[i]), "", "", "",
        ])
    return out


def _rows_grid_categories(rows: list[dict[str, str]]) -> list[list[str]]:
    out = []
    for i in range(4):
        r = rows[i] if i < len(rows) else {}
        out.append([
            r.get("cat", ""),
            r.get("q1", ""), r.get("a1", ""),
            r.get("q2", ""), r.get("a2", ""),
            r.get("q3", ""), r.get("a3", ""),
            r.get("q4", ""), r.get("a4", ""),
            "", "", "",
        ])
    return out


def _rows_grid_wager(rows: list[dict[str, str]]) -> list[list[str]]:
    r = rows[4] if len(rows) > 4 else {}
    return [[r.get("finalCat", ""), r.get("finalQ", ""), r.get("finalA", ""), "", "", ""]]


def _rows_single(rows: list[dict[str, str]]) -> list[list[str]]:
    r = rows[0] if rows else {}
    return [[r.get("question", ""), r.get("answer", ""), "", "", ""]]


EXPORTS: Exports = {
    "elementary": [{
        "slug": "its-elementary",
        "label": "It's Elementary",
        "headers": ["question", "grade", "correctAnswer", "explanation", "answerA",
                    "answerB", "answerC", "answerD", "flags", "difficulty",
                    "specialEventId"],
        "build": _rows_elementary,
    }],
    "readybetgo": [{
        "slug": "ready-bet-go",
        "label": "Ready, Bet, Go!",
        "headers": ["question", "answerA", "answerB", "answerC", "answerAExplanation",
                    "answerBExplanation", "answerCExplanation", "correctAnswer",
                    "flags", "difficulty", "specialEventId"],
        "build": _rows_readybetgo,
    }],
    "temple": [{
        "slug": "trivia-temple",
        "label": "Trivia Temple",
        "headers": ["question", "answerA", "answerB", "answerC", "answerD",
                    "correctAnswer", "pointLevel", "flags", "difficulty",
                    "specialEventId"],
        "build": _rows_temple,
    }],
    "grid": [
        {
            "slug": "the-grid-categories",
            "label": "The Grid — categories",
            "headers": ["category", "questionOne", "answerOne", "questionTwo",
                        "answerTwo", "questionThree", "answerThree", "questionFour",
                        "answerFour", "flags", "difficulty", "specialEventId"],
            "build": _rows_grid_categories,
        },
        {
            "slug": "the-grid-wisdom-wager",
            "label": "The Grid — Wisdom Wager",
            "headers": ["category", "question", "answer", "flags", "difficulty",
                        "specialEventId"],
            "build": _rows_grid_wager,
        },
    ],
    "single": [{
        "slug": "one-question-only",
        "label": "One Question Only",
        "headers": ["question", "answer", "flags", "difficulty", "specialEventId"],
        "build": _rows_single,
    }],
}


def export_specs(game_id: str) -> list[dict[str, Any]]:
    return EXPORTS.get(game_id, [])


def find_spec(game_id: str, slug: str) -> dict[str, Any] | None:
    for spec in export_specs(game_id):
        if spec["slug"] == slug:
            return spec
    return None


def build_csv(spec: dict[str, Any], rows: list[dict[str, str]],
              special_event_id: str = "") -> str:
    """Render one export as CSV text (LF line endings, RFC-4180 quoting)."""
    headers: list[str] = spec["headers"]
    try:
        event_col = headers.index("specialEventId")
    except ValueError:
        event_col = -1

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in spec["build"](rows or []):
        row = list(row)
        if event_col >= 0 and special_event_id:
            row[event_col] = special_event_id
        writer.writerow(row)
    return buf.getvalue()


def filename_for(spec: dict[str, Any], on: date | None = None) -> str:
    return f"{spec['slug']}-export-{(on or date.today()).isoformat()}.csv"
