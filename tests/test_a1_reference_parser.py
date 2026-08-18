from __future__ import annotations

import pytest

from rns_import_server.a1_reference_parser import (
    A1Reference,
    CellReference,
    FormulaAst,
    MAX_ROW,
    ReferenceToken,
    UnsupportedReference,
    map_formula,
    parse_formula,
)
from tests.a1_reference_cases import MAPPING_CASES, UNSUPPORTED_CASES


@pytest.mark.parametrize("formula,host,target,row,expected", MAPPING_CASES)
def test_structural_mapping_cases_cover_distinct_boundaries(
    formula: str, host: str, target: str, row: int, expected: str,
) -> None:
    assert map_formula(formula, host_sheet=host, target_sheet=target, insertion_row=row) == expected


def test_parser_returns_immutable_tokens_ast_and_exact_roundtrip() -> None:
    formula = '=SUM(A10,"A10 [not-a-reference]")+Rate+\'O\'\'Brien\'!$B$10'
    ast = parse_formula(formula)
    assert isinstance(ast, FormulaAst)
    assert ast.render() == formula
    reference_tokens = [token for token in ast.tokens if isinstance(token, ReferenceToken)]
    assert len(reference_tokens) == 2
    assert isinstance(reference_tokens[0].reference, A1Reference)
    assert reference_tokens[0].reference.first == CellReference("A", 10)
    with pytest.raises((AttributeError, TypeError)):
        ast.tokens[0] = ast.tokens[0]  # type: ignore[index]


def test_strings_functions_and_defined_names_are_not_rewritten() -> None:
    formula = '=SUM(A10,"A10",Rate,NameA1)+"[Book]Sheet!A10"'
    assert map_formula(formula, host_sheet="Target", target_sheet="Target", insertion_row=10) == (
        '=SUM(A11,"A10",Rate,NameA1)+"[Book]Sheet!A10"'
    )


@pytest.mark.parametrize("formula", UNSUPPORTED_CASES)
def test_unsupported_reference_is_typed_and_happens_before_any_rewrite(formula: str) -> None:
    with pytest.raises(UnsupportedReference) as error:
        map_formula(formula, host_sheet="Target", target_sheet="Target", insertion_row=10)
    assert error.value.code in {"external_or_structured_reference", "three_dimensional_reference"}


def test_quoted_sheet_apostrophe_roundtrips_when_not_target() -> None:
    formula = "='O''Brien'!A104"
    assert map_formula(formula, host_sheet="Host", target_sheet="Other", insertion_row=104) == formula


@pytest.mark.parametrize(("formula", "row", "expected"), (
    ("=a6+$b$5", 6, "=a7+$b$5"),
    ("=c10:d10", 10, "=c11:d11"),
    ("=e103:e104", 104, "=e103:e105"),
))
def test_mapping_preserves_raw_column_case_at_6_10_and_104(formula: str, row: int, expected: str) -> None:
    assert parse_formula(formula).render() == formula
    assert map_formula(formula, host_sheet="Target", target_sheet="Target", insertion_row=row) == expected


def test_reference_shaped_function_identifier_is_not_a_cell_reference() -> None:
    formula = "=LOG10(A10)+LOG1(A10)+SUM(A10)"
    assert map_formula(formula, host_sheet="Target", target_sheet="Target", insertion_row=10) == "=LOG10(A11)+LOG1(A11)+SUM(A11)"


@pytest.mark.parametrize("formula", (
    "='First':'Last'!A10",
    "='First':Last!A10",
    "=First:'Last'!A10",
    "=First:Last!A10",
))
def test_every_quoted_unquoted_three_dimensional_span_is_rejected(formula: str) -> None:
    with pytest.raises(UnsupportedReference, match="three_dimensional_reference"):
        parse_formula(formula)


def test_unsupported_between_valid_references_never_reaches_render(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_render(self: FormulaAst) -> str:
        raise AssertionError("partial mapping attempted to render")

    monkeypatch.setattr(FormulaAst, "render", unexpected_render)
    with pytest.raises(UnsupportedReference, match="three_dimensional_reference"):
        map_formula("=A6+First:'Last'!A10+B104", host_sheet="Target", target_sheet="Target", insertion_row=10)


@pytest.mark.parametrize("formula", ("=A1048577", "=1048577:1048578"))
def test_parser_rejects_rows_outside_excel_bounds(formula: str) -> None:
    with pytest.raises(UnsupportedReference, match="a1_row_out_of_bounds"):
        parse_formula(formula)


def test_insertion_overflow_fails_before_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FormulaAst, "render", lambda self: (_ for _ in ()).throw(AssertionError("rendered")))
    with pytest.raises(UnsupportedReference, match="a1_row_insertion_overflow"):
        map_formula(f"=A{MAX_ROW}", host_sheet="Target", target_sheet="Target", insertion_row=MAX_ROW)
