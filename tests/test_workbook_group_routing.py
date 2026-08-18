from __future__ import annotations

from rns_import_server.workbook_groups import (
    SheetProjection, SheetRow, WorkbookGroupCode, resolve_workbook_group,
)


RNS = "RU-12345678-09-2026"
NAME = "Стройка А"
CODE = "123-1234567"


def row(number: int, *, a=None, b=None, c=None, d=None, e=None, f=None, business=False, formatted=False, owned=False) -> SheetRow:
    return SheetRow(number, a, b, c, d, e, f, business, formatted, owned)


def projection(*rows: SheetRow, identity="book-1", digest="hash-1", generation=7) -> SheetProjection:
    return SheetProjection.from_rows(identity, digest, generation, rows)


def resolve(sheet: SheetProjection, **kwargs):
    return resolve_workbook_group(
        sheet, construction_id="a", official_name=NAME, code_prefix=CODE,
        rns=RNS, official_names=(NAME, "Стройка Б", "Другая"), **kwargs,
    )


def header(number: int, name=NAME) -> SheetRow:
    return row(number, d=name)


def test_adjacent_groups_use_exact_single_header_and_insert_before_next_header() -> None:
    result = resolve(projection(header(4), row(5, c="123-1234567-0001", d="Есть"), header(6, "Стройка Б")))
    assert result.code is WorkbookGroupCode.INSERTION_PLANNED
    assert result.block_start == 4 and result.block_end == 5
    assert result.plan is not None and result.plan.target_row == 6


def test_missing_and_repeated_target_headers_fail_closed() -> None:
    assert resolve(projection(header(4, "Другая"))).code is WorkbookGroupCode.BLOCK_MISSING
    assert resolve(projection(header(4), header(10))).code is WorkbookGroupCode.BLOCK_DUPLICATE


def test_group_first_rns_match_wins_over_same_rns_outside() -> None:
    result = resolve(projection(header(4), row(5, f=RNS), header(6, "Другая"), row(7, f=RNS)))
    assert result.code is WorkbookGroupCode.EXISTING_ROW
    assert result.existing_row is not None
    assert result.existing_row.identity.canonical_rns == RNS
    assert result.existing_row.observed_row == 5


def test_outside_only_duplicate_inside_and_absence_have_distinct_results() -> None:
    outside = resolve(projection(header(4), header(6, "Другая"), row(7, f=RNS)))
    duplicate = resolve(projection(header(4), row(5, f=RNS), row(6, f=RNS), header(10, "Другая")))
    absent = resolve(projection(header(4), header(10, "Другая")))
    assert outside.code is WorkbookGroupCode.RNS_WRONG_BLOCK
    assert duplicate.code is WorkbookGroupCode.RNS_BLOCK_CONFLICT
    assert absent.code is WorkbookGroupCode.INSERTION_PLANNED and absent.plan.target_row == 10


def test_foreign_structured_c_conflicts_but_blank_and_legacy_dash_are_allowed() -> None:
    foreign = resolve(projection(header(4), row(5, c="999-1234567-0001"), header(6, "Другая")))
    allowed = resolve(projection(header(4), row(5), row(6, c="-"), header(10, "Другая")))
    assert foreign.code is WorkbookGroupCode.BLOCK_CODE_CONFLICT
    assert allowed.code is WorkbookGroupCode.INSERTION_PLANNED


def test_only_validated_blank_slot_is_planned_not_an_arbitrary_blank_c() -> None:
    invalid = resolve(projection(header(4), row(5, business=True), header(6, "Другая")))
    valid = resolve(projection(header(4), row(5, business=True, formatted=True), header(6, "Другая")))
    assert invalid.code is WorkbookGroupCode.INSERTION_PLANNED and invalid.plan.target_row == 6
    assert valid.code is WorkbookGroupCode.BLANK_ROW_PLANNED and valid.plan.target_row == 5


def test_insertion_points_preserve_next_header_boundaries() -> None:
    for next_header in (6, 10, 104):
        result = resolve(projection(header(4), header(next_header, "Другая")))
        assert result.code is WorkbookGroupCode.INSERTION_PLANNED
        assert result.plan is not None and result.plan.target_row == next_header


def test_last_group_blank_requires_ownership_evidence() -> None:
    unsafe = resolve(projection(header(4), row(5, business=True, formatted=True)))
    safe = resolve(projection(header(4), row(5, business=True, formatted=True, owned=True)))
    assert unsafe.code is WorkbookGroupCode.NO_SAFE_INSERTION_POINT
    assert safe.code is WorkbookGroupCode.BLANK_ROW_PLANNED and safe.plan.target_row == 5


def test_arbitrary_blank_shape_row_is_not_a_header_boundary() -> None:
    result = resolve(projection(header(4), row(5, d="Случайный текст"), header(10, "Другая")))
    assert result.code is WorkbookGroupCode.INSERTION_PLANNED
    assert result.plan is not None and result.plan.target_row == 10


def test_repeated_code_allows_equivalent_name_but_rejects_different_name_and_keeps_leading_zeroes() -> None:
    code = "123-1234567-0001"
    allowed = resolve(projection(header(4), row(5, c=code, d="Объект Ёлка"), header(10, "Другая")), object_code=code, object_name="объект елка")
    conflicting = resolve(projection(header(4), row(5, c=code, d="Другой объект"), header(10, "Другая")), object_code=code, object_name="Объект Ёлка")
    assert allowed.code is WorkbookGroupCode.INSERTION_PLANNED
    assert conflicting.code is WorkbookGroupCode.OBJECT_CODE_NAME_CONFLICT


def test_plan_includes_stale_revalidation_identity_and_rejects_stale_input() -> None:
    sheet = projection(header(4), header(10, "Другая"))
    result = resolve(sheet)
    assert result.plan is not None
    assert (result.plan.workbook_identity, result.plan.workbook_hash, result.plan.registry_generation) == ("book-1", "hash-1", 7)
    assert resolve(sheet, expected_workbook_hash="old").code is WorkbookGroupCode.STALE_WORKBOOK
    assert resolve(sheet, expected_registry_generation=6).code is WorkbookGroupCode.STALE_REGISTRY


def test_side_effect_free_projection_and_raw_existing_values_are_preserved() -> None:
    source = projection(header(4), row(5, a="01", c="123-1234567-0001", d="Объект", f="№RU-12345678-09-2026"), header(10, "Другая"))
    before = source.rows
    result = resolve(source)
    assert source.rows == before
    assert result.existing_row is not None
    assert result.existing_row.raw_values == source.rows[1].raw_values
