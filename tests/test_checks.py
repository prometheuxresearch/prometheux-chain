"""Unit tests for Vadalog programs: the comparison, and the two check entry points.

The engine and the translator are patched out, so nothing here reaches a
backend. Run with ``python -m pytest tests``.
"""
from unittest.mock import patch

import pytest

import prometheux_chain as px
from prometheux_chain.testing import manage_checks
from prometheux_chain.vadalog import manage_vadalog

TC_RESULT = {
    "resultSet": {"tc": [[1, 2], [2, 3], [1, 3]]},
    "columnNames": {"tc": ["X", "Y"]},
}


def _engine(result=None, error=None):
    def evaluate(program, params=None, compute=None):
        if error:
            raise Exception(error)
        return result
    return patch.object(manage_checks, "evaluate_program", side_effect=evaluate)


# ── comparison ───────────────────────────────────────────────────────────────

def test_numbers_match_however_they_were_serialized():
    check = px.compare_rows("p", [[2, "3", 4.0]], [["2", "3.0", "4"]])
    assert check.ok


def test_booleans_match_their_csv_spelling():
    assert px.compare_rows("p", [[True, False]], [["true", "False"]]).ok


def test_exact_fails_on_an_extra_row_and_reports_it():
    check = px.compare_rows("tc", [[1, 2], [2, 3]], [[1, 2]])
    assert not check.ok
    assert check.extra == [[2, 3]]
    assert check.missing == []


def test_contains_ignores_extra_rows():
    check = px.compare_rows("tc", [[1, 2], [2, 3]], [[1, 2]], mode="contains")
    assert check.ok
    assert "MISMATCH" not in check.summary()


def test_contains_still_fails_on_a_missing_row():
    check = px.compare_rows("tc", [[1, 2]], [[1, 2], [9, 9]], mode="contains")
    assert not check.ok
    assert check.missing == [[9, 9]]


def test_reported_rows_keep_the_values_they_were_given(tmp_path):
    path = tmp_path / "tc.csv"
    path.write_text("1,2\n9,9.5\n", encoding="utf-8")
    check = px.compare_rows("tc", [[1, 2], [3, "x"]], px.read_expected_csv(path))

    assert check.missing == [[9, 9.5]]
    assert check.extra == [[3, "x"]]
    assert "missing=[[9, 9.5]]" in check.summary()


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        px.compare_rows("p", [], [], mode="subset")


def test_the_expected_csv_skips_blank_lines_and_an_optional_header(tmp_path):
    path = tmp_path / "tc.csv"
    path.write_text("x,y\n1,2\n\n2,3\n", encoding="utf-8")

    assert px.read_expected_csv(path, header=True) == [(1.0, 2.0), (2.0, 3.0)]
    assert len(px.read_expected_csv(path)) == 3


# ── check_program ────────────────────────────────────────────────────────────

def test_a_program_matching_its_csv_passes(tmp_path):
    path = tmp_path / "tc.csv"
    path.write_text("1,2\n2,3\n1,3\n", encoding="utf-8")
    with _engine(TC_RESULT):
        report = px.check_program("tc(X,Y) :- edge(X,Y).", expect={"tc": str(path)})

    assert report.ok, report.summary()
    assert report.assert_ok() is report


def test_rows_can_be_given_inline():
    with _engine(TC_RESULT):
        report = px.check_program("p.", expect={"tc": [[1, 2], [2, 3]]})

    assert not report.ok
    (check,) = report.checks
    assert check.extra == [[1, 3]]
    with pytest.raises(AssertionError, match="tc: FAIL"):
        report.assert_ok()


def test_a_predicate_the_program_did_not_produce_fails_with_what_it_did():
    with _engine(TC_RESULT):
        report = px.check_program("p.", expect={"reachable": [[1]]})

    assert not report.ok
    assert "produced: tc" in report.checks[0].error


def test_an_engine_error_is_a_failed_report_not_an_exception():
    with _engine(error="HTTP Error 500: parse error at line 1"):
        report = px.check_program("p(", expect={"p": [[1]]})

    assert not report.ok
    assert "parse error" in report.error


def test_an_unreadable_csv_fails_only_its_own_predicate(tmp_path):
    with _engine(TC_RESULT):
        report = px.check_program("p.", expect={"tc": str(tmp_path / "missing.csv")})

    assert not report.ok
    assert "cannot read expected CSV" in report.checks[0].error


def test_no_expectations_passes_when_the_program_evaluates():
    with _engine(TC_RESULT):
        report = px.check_program("p.")

    assert report.ok
    assert report.result_set == TC_RESULT["resultSet"]


# ── check_question ───────────────────────────────────────────────────────────

GENERATED = {"program": '@output("tc").\ntc(X,Y) :- edge(X,Y).', "model": "p/m", "response": ""}


def test_a_question_checks_the_last_output_of_its_program():
    with patch.object(manage_checks, "generate_program", return_value=dict(GENERATED)), \
            _engine(TC_RESULT):
        report = px.check_question("transitive closure", expect=[[1, 2], [2, 3], [1, 3]])

    assert report.ok, report.summary()
    assert report.checks[0].predicate == "tc"
    assert (report.question, report.model) == ("transitive closure", "p/m")
    assert report.program == GENERATED["program"]


def test_a_program_without_output_needs_the_predicate_named():
    generated = dict(GENERATED, program="tc(X,Y) :- edge(X,Y).")
    with patch.object(manage_checks, "generate_program", return_value=generated):
        report = px.check_question("transitive closure", expect=[[1, 2]])

    assert not report.ok
    assert "expect_predicate" in report.error


def test_a_failed_translation_is_a_failed_report():
    with patch.object(manage_checks, "generate_program",
                      side_effect=Exception("the translator returned no Vadalog program")):
        report = px.check_question("gibberish", expect=[[1]])

    assert not report.ok
    assert "no Vadalog program" in report.error


# ── generate_program ─────────────────────────────────────────────────────────

def test_the_structured_code_example_is_preferred():
    answer = {"response": "```vadalog\nlonger(X) :- other(X), more(X).\n```",
              "code_examples": [{"code": "tc(X,Y) :- edge(X,Y)."}],
              "metadata": {"provider": "anthropic", "model": "m1"}}
    with patch.object(manage_vadalog.JarvisPyClient, "generate_program", return_value=answer):
        generated = px.generate_program("tc")

    assert generated["program"] == "tc(X,Y) :- edge(X,Y)."
    assert generated["model"] == "anthropic/m1"


def test_without_a_code_example_the_longest_fenced_block_is_used():
    answer = {"response": "```\nshort.\n```\ntext\n```vadalog\ntc(X,Y) :- edge(X,Y).\n```"}
    with patch.object(manage_vadalog.JarvisPyClient, "generate_program", return_value=answer):
        assert px.generate_program("tc")["program"] == "tc(X,Y) :- edge(X,Y)."


def test_an_answer_with_no_program_raises():
    with patch.object(manage_vadalog.JarvisPyClient, "generate_program",
                      return_value={"response": "I cannot help with that."}):
        with pytest.raises(Exception, match="no Vadalog program"):
            px.generate_program("?")
