"""
Vadalog Checks Module

Unit tests for Vadalog programs: evaluate a program on the platform engine and
compare each output predicate with the rows you expect, given as a CSV file or
as a list of rows. ``check_question`` does the same for a program the
natural-language translator writes from a question.

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

import csv
import json
import math
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

from ..vadalog.manage_vadalog import evaluate_program, generate_program

EXACT = "exact"
CONTAINS = "contains"
MODES = (EXACT, CONTAINS)

# Rows shown per list in a failure message; the report itself keeps them all.
_SHOWN_ROWS = 8

_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
_OUTPUT_ANNOTATION = re.compile(r'@output\(\s*"([^"]+)"')
_BOOLEANS = {"true": "true", "#t": "true", "false": "false", "#f": "false"}

Rows = List[List[Any]]


@dataclass
class PredicateCheck:
    """How one output predicate compared with its expected rows."""

    predicate: str
    ok: bool
    mode: str
    actual_count: int = 0
    expected_count: int = 0
    missing: Rows = field(default_factory=list)
    extra: Rows = field(default_factory=list)
    error: Optional[str] = None

    def summary(self) -> str:
        if self.error:
            return f"{self.predicate}: FAIL :: {self.error}"
        count = f"count actual={self.actual_count} expected={self.expected_count}"
        if self.mode == EXACT:
            count += " (OK)" if self.actual_count == self.expected_count else " (MISMATCH)"
        parts = [
            count,
            "containment " + ("OK" if not self.missing else f"FAIL missing={_shown(self.missing)}"),
        ]
        if self.mode == EXACT and self.extra:
            parts.append(f"extra={_shown(self.extra)}")
        return f"{self.predicate}: {'PASS' if self.ok else 'FAIL'} :: " + " | ".join(parts)


@dataclass
class CheckReport:
    """The outcome of one checked program."""

    ok: bool
    checks: List[PredicateCheck] = field(default_factory=list)
    result_set: Dict[str, Rows] = field(default_factory=dict)
    error: Optional[str] = None
    program: Optional[str] = None
    question: Optional[str] = None
    model: Optional[str] = None

    def summary(self) -> str:
        if self.error:
            return f"FAIL :: {self.error}"
        if not self.checks:
            predicates = ", ".join(self.result_set) or "none"
            return f"PASS :: evaluated, no expectations (predicates: {predicates})"
        return "\n".join(check.summary() for check in self.checks)

    def assert_ok(self) -> "CheckReport":
        """Raise ``AssertionError`` with the summary unless every check passed."""
        if not self.ok:
            raise AssertionError(self.summary())
        return self

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_cell(value):
    """A cell in a form that compares equal however it was serialized.

    Numbers become exact decimals, so ``2``, ``"2"`` and ``2.0`` match while
    ``2**53`` and ``2**53 + 1`` stay apart. A float is read as the shortest
    decimal that spells it, so the engine's ``0.1`` matches a CSV's ``0.1``.
    Booleans become ``"true"``/``"false"``, because a CSV can only spell them
    as text; the engine's own ``#T``/``#F`` count as booleans too.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value)) if math.isfinite(value) else value
    text = str(value).strip()
    if _NUMBER.match(text):
        return Decimal(text)
    return _BOOLEANS.get(text.lower(), text)


def normalize_row(row) -> tuple:
    return tuple(normalize_cell(cell) for cell in row)


def read_expected_csv(path, header=False) -> List[tuple]:
    """Expected rows from a CSV file: one row per line, blank lines skipped.

    There is no header unless ``header=True``, which skips the first line.
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for index, raw in enumerate(csv.reader(handle)):
            if header and index == 0:
                continue
            if not raw or (len(raw) == 1 and not raw[0].strip()):
                continue
            rows.append(normalize_row(raw))
    return rows


def compare_rows(predicate, actual, expected, mode=EXACT) -> PredicateCheck:
    """Compare the rows a predicate produced with the rows expected of it.

    ``exact`` passes when both sides hold the same rows the same number of
    times, in any order; ``missing`` and ``extra`` then list every occurrence
    one side has beyond the other, so a row expected twice but produced once
    is missing once. ``contains`` passes when every expected row was produced
    at least once, whatever else was, and lists each missing row once. Rows
    are listed as they were given rather than in their normalized form.
    """
    _check_mode(mode)
    actual_rows = [normalize_row(row) for row in actual]
    expected_rows = [normalize_row(row) for row in expected]
    if mode == CONTAINS:
        actual_set, expected_set = set(actual_rows), set(expected_rows)
        missing = _unique([_display_row(row) for row, key in zip(expected, expected_rows)
                           if key not in actual_set])
        extra = _unique([_display_row(row) for row, key in zip(actual, actual_rows)
                         if key not in expected_set])
        ok = not missing
    else:
        missing = _surplus(expected, expected_rows, Counter(actual_rows))
        extra = _surplus(actual, actual_rows, Counter(expected_rows))
        ok = not missing and not extra
    return PredicateCheck(
        predicate=predicate, ok=ok, mode=mode,
        actual_count=len(actual_rows), expected_count=len(expected_rows),
        missing=missing, extra=extra,
    )


def check_program(program, expect=None, mode=EXACT, params=None, compute=None,
                  header=False) -> CheckReport:
    """Evaluate a Vadalog program and check its outputs.

    ``expect`` maps each output predicate to its expected rows: a CSV path or a
    list of rows. With no ``expect`` the check passes when the program
    evaluates. Never raises for a failed check or an engine error; read
    ``report.ok``, or call ``report.assert_ok()`` inside a test.

    Example::

        report = px.check_program(open("tc.vada").read(), expect={"tc": "tc.csv"})
        report.assert_ok()
    """
    _check_mode(mode)
    try:
        evaluation = evaluate_program(program, params=params, compute=compute) or {}
    except Exception as exc:
        return CheckReport(ok=False, error=f"engine error: {exc}", program=program)

    if isinstance(evaluation, dict) and evaluation.get("errorMessage"):
        return CheckReport(ok=False, error=f"engine error: {evaluation['errorMessage']}",
                           program=program)
    result_set = (evaluation.get("resultSet") if isinstance(evaluation, dict) else None) or {}
    outputs = set(_OUTPUT_ANNOTATION.findall(program or ""))

    checks = [_check_predicate(result_set, outputs, predicate, rows, mode, header)
              for predicate, rows in (expect or {}).items()]
    return CheckReport(ok=all(check.ok for check in checks), checks=checks,
                       result_set=result_set, program=program)


def check_question(question, expect=None, mode=EXACT, expect_predicate=None,
                   context=None, params=None, compute=None, header=False) -> CheckReport:
    """Translate a question into a Vadalog program, evaluate it, and check it.

    ``expect`` is either a mapping like ``check_program`` takes, or a single CSV
    path or list of rows. In the second form the rows are checked against
    ``expect_predicate``, or the last ``@output`` of the generated program
    when that is not given. Each call is metered as one program generation.
    """
    _check_mode(mode)
    try:
        generated = generate_program(question, context=context)
    except Exception as exc:
        return CheckReport(ok=False, error=str(exc), question=question)

    program = generated["program"]
    if expect is not None and not isinstance(expect, Mapping):
        predicate = expect_predicate or detect_output_predicate(program)
        if not predicate:
            return CheckReport(
                ok=False, program=program, question=question, model=generated["model"],
                error="the generated program has no @output; pass expect_predicate")
        expect = {predicate: expect}

    report = check_program(program, expect=expect, mode=mode, params=params,
                           compute=compute, header=header)
    report.question = question
    report.model = generated["model"]
    return report


def detect_output_predicate(program) -> Optional[str]:
    """The predicate of the last ``@output`` annotation, if there is one."""
    outputs = _OUTPUT_ANNOTATION.findall(program or "")
    return outputs[-1] if outputs else None


def _check_predicate(result_set, outputs, predicate, expected, mode, header) -> PredicateCheck:
    # The engine leaves an @output that derived no rows out of the result set.
    if predicate not in result_set and predicate not in outputs:
        produced = ", ".join(result_set) or "no rows for any predicate"
        return PredicateCheck(predicate=predicate, ok=False, mode=mode,
                              error=f"not an output of the program (produced: {produced})")
    if isinstance(expected, (str, os.PathLike)):
        try:
            expected = read_expected_csv(expected, header=header)
        except OSError as exc:
            return PredicateCheck(predicate=predicate, ok=False, mode=mode,
                                  error=f"cannot read expected CSV: {exc}")
    return compare_rows(predicate, result_set.get(predicate, []), expected, mode)


def _check_mode(mode):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, got {mode!r}")


def _surplus(rows, keys, budget: Counter) -> list:
    """The rows, in order, left over once ``budget`` has absorbed its occurrences."""
    budget = Counter(budget)
    left = []
    for row, key in zip(rows, keys):
        if budget[key] > 0:
            budget[key] -= 1
        else:
            left.append(_display_row(row))
    return left


def _display_row(row) -> list:
    # Rows read from a CSV arrive already normalized, so 2 has become Decimal(2).
    return [_display_cell(cell) for cell in row]


def _display_cell(cell):
    if not isinstance(cell, Decimal):
        return cell
    if cell == cell.to_integral_value():
        return int(cell)
    as_float = float(cell)
    return as_float if Decimal(repr(as_float)) == cell else str(cell)


def _unique(rows):
    seen, unique = set(), []
    for row in rows:
        key = normalize_row(row)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _shown(rows):
    text = json.dumps(rows[:_SHOWN_ROWS], default=str)
    hidden = len(rows) - _SHOWN_ROWS
    return text + (f" (+{hidden} more)" if hidden > 0 else "")
