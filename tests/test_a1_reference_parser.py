from __future__ import annotations

import pytest

from rns_import_server.a1_reference_parser import (
    A1Reference,
    CellReference,
    FormulaAst,
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
