from __future__ import annotations

import pytest

from rns_import_server.ooxml_rule_reader import OOXMLRuleError, read_ooxml_rules
from tests.ooxml_rule_fixture_factory import worksheet_parts


@pytest.mark.parametrize("boundary", (6, 10, 104))
def test_reads_complete_native_and_x14_rules_at_distinct_boundaries(boundary: int) -> None:
    model = read_ooxml_rules(worksheet_parts(boundary))
    first, other = model.worksheets
    assert first.part == f"xl/worksheets/sheet{boundary}.xml" and other.part == f"xl/worksheets/other{boundary}.xml"
    assert [rule.sqref for rule in first.conditional_formats] == [f"A{boundary}:A{boundary + 4}", f"C{boundary}:C{boundary + 4}", f"E{boundary}:E{boundary + 4}", f"G{boundary}:G{boundary + 4}"]
    native, x14 = first.conditional_formats[0], first.conditional_formats[2]
    assert (native.source, native.rule_order, native.priority, native.stop_if_true, native.operator, native.dxf_id, native.formulas) == ("native", 1, 2, True, "greaterThan", 3, ("10", "20"))
    assert (x14.source, x14.rule_order, x14.priority, x14.dxf_reference, x14.formulas) == ("x14", 1, 7, "4", (f"A{boundary}>0",))
    assert [rule.sqref for rule in first.data_validations] == [f"B{boundary}:B{boundary + 4}", f"D{boundary}:D{boundary + 4}", f"F{boundary}:F{boundary + 4}", f"H{boundary}:H{boundary + 4}"]
    native_dv, x14_dv = first.data_validations[0], first.data_validations[2]
    assert (native_dv.validation_type, native_dv.operator, native_dv.allow_blank, native_dv.show_error_message, native_dv.show_input_message, native_dv.formula1, native_dv.formula2) == ("whole", "between", True, False, True, "1", "9")
    assert (x14_dv.source, x14_dv.validation_type, x14_dv.allow_blank, x14_dv.formula1) == ("x14", "list", False, '"yes,no"')
    assert [(finding.owner, finding.detail) for finding in first.findings] == [("native-cf-rule", "attribute:custom"), ("native-cf-rule", f"child:{{{__import__('tests.ooxml_rule_fixture_factory', fromlist=['X']).X}}}unknown"), ("x14-cf-rule", "attribute:custom"), ("x14-cf-rule", f"child:{{{__import__('tests.ooxml_rule_fixture_factory', fromlist=['X14']).X14}}}future"), ("native-dataValidation", "attribute:custom"), ("native-dataValidation", f"child:{{{__import__('tests.ooxml_rule_fixture_factory', fromlist=['X']).X}}}future"), ("x14-dataValidation", "attribute:custom"), ("x14-dataValidation", f"child:{{{__import__('tests.ooxml_rule_fixture_factory', fromlist=['X14']).X14}}}future")]


@pytest.mark.parametrize(
    ("mutate", "code", "field"),
    [
        (lambda parts: parts.__setitem__("xl/worksheets/sheet6.xml", parts["xl/worksheets/sheet6.xml"].replace(b'priority="2"', b'priority="bad"')), "invalid-integer", "cfRule.priority"),
        (lambda parts: parts.__setitem__("xl/worksheets/sheet6.xml", parts["xl/worksheets/sheet6.xml"].replace(b'sqref="A6:A10 C6:C10"', b'sqref=""')), "missing-sqref", "conditionalFormatting"),
        (lambda parts: parts.__setitem__("xl/worksheets/sheet6.xml", b"<worksheet"), "malformed-worksheet-xml", ""),
    ],
)
def test_semantic_mutations_have_exact_typed_error(tmp_path, mutate, code, field) -> None:
    parts = worksheet_parts(6, mutate)
    with pytest.raises(OOXMLRuleError) as raised:
        read_ooxml_rules(parts)
    assert (raised.value.code, raised.value.detail) == (code, field) if field else (code, raised.value.detail)


def test_explicit_part_map_never_discovers_or_reorders_parts() -> None:
    parts = worksheet_parts(10)
    model = read_ooxml_rules(parts)
    assert [sheet.part for sheet in model.worksheets] == list(parts)
