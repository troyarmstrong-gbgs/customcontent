"""The five games' content shapes — one source of truth.

This module defines, per game, how many rows of content it takes, what
fields each row has, how long each field may be, and how those rows map
onto the CSV columns the trivia database imports.

Both the server-side validator (`validate_submission`) and the CSV
exporter read from here, so a limit can never drift between what the
form accepts and what the export produces. The browser has its own copy
of these limits for live feedback; the browser's copy is a convenience,
this one is the rule.
"""
from __future__ import annotations

from typing import Any

GRADES = ["1st", "2nd", "3rd", "4th", "5th"]
TEMPLE_LEVEL_ORDER = [100, 500, 1000, 2500, 5000]
TEMPLE_LEVELS = [lv for lv in TEMPLE_LEVEL_ORDER for _ in range(4)]
LETTERS = {"a": "A", "b": "B", "c": "C", "d": "D"}


def _f(key: str, limit: int, *, required: bool = True) -> dict[str, Any]:
    return {"key": key, "limit": limit, "required": required}


# `answer_keys` marks the fields that are answer options for a single
# question: they must all be filled, must differ from one another, and
# the `correct` field must match one of them exactly.
GAMES: dict[str, dict[str, Any]] = {
    "elementary": {
        "name": "It's Elementary",
        "rows": 5,
        "fields": [
            _f("question", 100),
            _f("a", 35), _f("b", 35), _f("c", 35), _f("d", 35),
            _f("correct", 0),
        ],
        "answer_keys": ["a", "b", "c", "d"],
    },
    "readybetgo": {
        "name": "Ready, Bet, Go!",
        "rows": 10,
        "fields": [
            _f("question", 200),
            _f("a", 30), _f("b", 35), _f("c", 35),
            _f("correct", 0),
        ],
        "answer_keys": ["a", "b", "c"],
    },
    "temple": {
        "name": "Trivia Temple",
        "rows": 20,
        "fields": [
            _f("question", 200),
            _f("a", 30), _f("b", 35), _f("c", 35), _f("d", 35),
            _f("correct", 0),
        ],
        "answer_keys": ["a", "b", "c", "d"],
    },
    "grid": {
        "name": "The Grid",
        "rows": 5,
        # The Grid's last row is the Wisdom Wager, which has a different
        # shape from the four category rows.
        "fields_by_row": {
            "default": [
                _f("cat", 20),
                _f("q1", 200), _f("a1", 30),
                _f("q2", 200), _f("a2", 30),
                _f("q3", 200), _f("a3", 30),
                _f("q4", 200), _f("a4", 30),
            ],
            "4": [_f("finalCat", 20), _f("finalQ", 200), _f("finalA", 30)],
        },
        "answer_keys": [],
    },
    "single": {
        "name": "One Question Only",
        "rows": 1,
        "fields": [_f("question", 200), _f("answer", 100)],
        "answer_keys": [],
    },
}

GAME_IDS = list(GAMES)


def fields_for(game_id: str, row_index: int) -> list[dict[str, Any]]:
    g = GAMES[game_id]
    by_row = g.get("fields_by_row")
    if by_row:
        return by_row.get(str(row_index), by_row["default"])
    return g["fields"]


def row_label(game_id: str, i: int) -> str:
    if game_id == "elementary":
        return f"{GRADES[i]} Grade"
    if game_id == "temple":
        return f"{TEMPLE_LEVELS[i]:,} pts · Q{(i % 4) + 1}"
    if game_id == "grid":
        return "Wisdom Wager" if i == 4 else f"Category {i + 1}"
    if game_id == "readybetgo":
        return f"Question {i + 1}"
    return "Your question"


# --- validation ------------------------------------------------------------

MAX_GAMES_PER_SUBMISSION = len(GAME_IDS)


class ValidationError(Exception):
    """Raised with a list of human-readable problems."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems[:5]))


def _clean(v: Any) -> str:
    """Coerce whatever arrived over the wire into a trimmed string."""
    if v is None:
        return ""
    if not isinstance(v, str):
        v = str(v)
    # Strip control characters; keep newlines out of single-line answers
    # by collapsing all whitespace runs to single spaces.
    return " ".join(v.split()).strip()


def validate_game(game_id: str, rows: Any) -> tuple[list[dict[str, str]], list[str]]:
    """Clean and check one game's rows.

    Returns (cleaned_rows, problems). Never trusts the browser: every
    limit, every required field and every cross-field rule is re-checked
    here, because the form's own checks are only a courtesy to the
    person typing.
    """
    problems: list[str] = []
    spec = GAMES[game_id]
    n = spec["rows"]
    if not isinstance(rows, list):
        return [], [f"{spec['name']}: content must be a list of rows."]
    if len(rows) > n:
        rows = rows[:n]

    cleaned: list[dict[str, str]] = []
    for i in range(n):
        raw = rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}
        out: dict[str, str] = {}
        where = f"{spec['name']} — {row_label(game_id, i)}"

        for fd in fields_for(game_id, i):
            val = _clean(raw.get(fd["key"]))
            if fd["required"] and not val:
                problems.append(f"{where}: {fd['key']} is required.")
            if fd["limit"] and len(val) > fd["limit"]:
                problems.append(
                    f"{where}: {fd['key']} is {len(val)} characters, "
                    f"the limit is {fd['limit']}."
                )
                val = val[: fd["limit"]]
            if val:
                out[fd["key"]] = val

        keys = spec["answer_keys"]
        if keys:
            answers = [out.get(k, "") for k in keys]
            filled = [a for a in answers if a]
            lowered = [a.lower() for a in filled]
            if len(set(lowered)) != len(lowered):
                problems.append(f"{where}: two answer options are identical.")
            correct = out.get("correct", "")
            if correct and correct not in filled:
                problems.append(
                    f"{where}: the correct answer must match one of the options exactly."
                )
            # Store the option letter alongside the text; Ready, Bet, Go!
            # is read by letter downstream.
            if correct:
                for k in keys:
                    if out.get(k) == correct:
                        out["correctLetter"] = LETTERS[k]
                        break

        cleaned.append(out)

    return cleaned, problems


def validate_submission(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a whole submission and return the record to store.

    Raises ValidationError with every problem found, so the form can show
    them all at once rather than one per round trip.
    """
    problems: list[str] = []

    name = _clean(payload.get("name"))[:120]
    email = _clean(payload.get("email"))[:254]
    group = _clean(payload.get("group"))[:160]
    location = _clean(payload.get("location"))[:160]
    event_date = _clean(payload.get("eventDate"))[:10]

    if not name:
        problems.append("Your name is required.")
    if "@" not in email or "." not in email.split("@")[-1] or " " in email:
        problems.append("A valid email address is required.")
    if not event_date or len(event_date) != 10 or event_date[4] != "-":
        problems.append("An event date is required.")
    if not location:
        problems.append("A store is required.")

    games = payload.get("games")
    if not isinstance(games, list) or not games:
        problems.append("Pick at least one game.")
        games = []
    games = [g for g in games if g in GAMES][:MAX_GAMES_PER_SUBMISSION]
    if not games and not problems:
        problems.append("Pick at least one game.")

    raw_content = payload.get("content") or {}
    if not isinstance(raw_content, dict):
        raw_content = {}

    content: dict[str, list[dict[str, str]]] = {}
    for gid in games:
        rows, game_problems = validate_game(gid, raw_content.get(gid))
        content[gid] = rows
        problems.extend(game_problems)

    if problems:
        raise ValidationError(problems)

    return {
        "name": name,
        "email": email.lower(),
        "group": group,
        "location": location,
        "event_date": event_date,
        "games": games,
        "content": content,
    }
