from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from rns_import_server.ooxml_native_cf_reader import (
    MAIN_NS,
    XR_NS,
    NativeCfParseError,
    NativeColorScale,
    NativeDataBar,
    NativeIconSet,
    read_native_conditional_formatting,
)


def _worksheet(contents: str) -> str:
    return f'<worksheet xmlns="{MAIN_NS}" xmlns:xr="{XR_NS}">{contents}</worksheet>'


def _rules(row: int) -> str:
    return f"""
      <conditionalFormatting sqref="A{row} B{row}:C{row}" pivot="1" xr:uid="{{01234567-89AB-CDEF-0123-456789ABCDEF}}">
        <cfRule type="expression" priority="1" dxfId="2" stopIfTrue="0" aboveAverage="true" percent="false" bottom="1" operator="equal" text="hello" timePeriod="today" rank="10" stdDev="2" equalAverage="false">
          <formula>A{row}=1</formula><formula>B{row}=2</formula>
        </cfRule>
        <cfRule type="colorScale" priority="2"><colorScale>
          <cfvo type="min"/><cfvo type="percentile" val="50" gte="false"/><cfvo type="max"/>
          <color rgb="FF0000FF"/><color theme="1" tint="-0.5"/><color indexed="64"/>
        </colorScale></cfRule>
        <cfRule type="dataBar" priority="3"><dataBar minLength="1" maxLength="99" showValue="false" gradient="true" border="0" negativeBarColorSameAsPositive="1" negativeBarBorderColorSameAsPositive="false" axisPosition="middle" direction="rightToLeft">
          <cfvo type="min"/><cfvo type="max"/><color auto="1"/>
        </dataBar></cfRule>
        <cfRule type="iconSet" priority="4"><iconSet iconSet="3Arrows" showValue="true" percent="0" reverse="false">
          <cfvo type="percent" val="0"/><cfvo type="percent" val="33"/><cfvo type="percent" val="67"/>
        </iconSet></cfRule>
      </conditionalFormatting>
      <conditionalFormatting sqref="D{row}" pivot="0"/>
    """


@pytest.mark.parametrize("sheet_name", ("Sheet1", "Dashboard"))
@pytest.mark.parametrize("row", (6, 10, 104))
def test_reads_ordered_complete_native_cf_matrix(sheet_name: str, row: int):
    result = read_native_conditional_formatting(f"xl/worksheets/{sheet_name}.xml", _worksheet(_rules(row)))

    assert result.findings == ()
    assert len(result.containers) == 2
    group, empty = result.containers
    assert group.owner_path == f"xl/worksheets/{sheet_name}.xml#worksheet/conditionalFormatting[1]"
    assert group.sqref == (f"A{row}", f"B{row}:C{row}")
    assert group.pivot is True
    assert group.uid == "{01234567-89AB-CDEF-0123-456789ABCDEF}"
    assert empty.sqref == (f"D{row}",)
    assert empty.pivot is False
    assert empty.uid is None
    assert empty.rules == ()

    expression, color_scale_rule, data_bar_rule, icon_set_rule = group.rules
    assert expression.owner_path.endswith("conditionalFormatting[1]/cfRule[1]")
    assert expression.type == "expression"
    assert expression.priority == 1 and expression.dxf_id == 2
    assert expression.stop_if_true is False
    assert expression.above_average is True
    assert expression.percent is False
    assert expression.bottom is True
    assert expression.operator == "equal"
    assert expression.text == "hello" and expression.time_period == "today"
    assert expression.rank == 10 and expression.standard_deviation == 2
    assert expression.equal_average is False
    assert expression.formulas == (f"A{row}=1", f"B{row}=2")
    assert expression.payload is None

    assert isinstance(color_scale_rule.payload, NativeColorScale)
    assert [value.type for value in color_scale_rule.payload.thresholds] == ["min", "percentile", "max"]
    assert color_scale_rule.payload.thresholds[1].value == "50"
    assert color_scale_rule.payload.thresholds[1].greater_than_or_equal is False
    assert color_scale_rule.payload.colors[0].rgb == "FF0000FF"
    assert color_scale_rule.payload.colors[1].theme == 1
    assert color_scale_rule.payload.colors[1].tint == -0.5
    assert color_scale_rule.payload.colors[2].indexed == 64

    assert isinstance(data_bar_rule.payload, NativeDataBar)
    assert data_bar_rule.payload.min_length == 1 and data_bar_rule.payload.max_length == 99
    assert data_bar_rule.payload.show_value is False and data_bar_rule.payload.gradient is True
    assert data_bar_rule.payload.border is False
    assert data_bar_rule.payload.negative_bar_color_same_as_positive is True
    assert data_bar_rule.payload.negative_bar_border_color_same_as_positive is False
    assert data_bar_rule.payload.axis_position == "middle" and data_bar_rule.payload.direction == "rightToLeft"
    assert data_bar_rule.payload.color.auto is True

    assert isinstance(icon_set_rule.payload, NativeIconSet)
    assert icon_set_rule.payload.icon_set == "3Arrows"
    assert icon_set_rule.payload.show_value is True
    assert icon_set_rule.payload.percent is False and icon_set_rule.payload.reverse is False
    assert [item.value for item in icon_set_rule.payload.thresholds] == ["0", "33", "67"]
    with pytest.raises(FrozenInstanceError):
        group.pivot = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("attribute", "expected"),
    (("", None), ('pivot="false"', False), ('pivot="true"', True)),
)
def test_pivot_is_tri_state(attribute: str, expected: bool | None):
    result = read_native_conditional_formatting(
        "xl/worksheets/sheet1.xml",
        _worksheet(f'<conditionalFormatting sqref="A1" {attribute}/><conditionalFormatting sqref="B1"/>'),
    )
    assert result.containers[0].pivot is expected
    assert result.containers[1].pivot is None


def test_preserves_zero_rule_container_and_empty_worksheet_collection():
    part = "xl/worksheets/sheet1.xml"
    only_empty = read_native_conditional_formatting(part, _worksheet('<conditionalFormatting sqref="A1"/>'))
    no_containers = read_native_conditional_formatting(part, _worksheet(""))
    assert only_empty.containers[0].rules == ()
    assert no_containers.containers == ()


@pytest.mark.parametrize(
    ("fragment", "code"),
    (
        ('<conditionalFormatting><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "missing_sqref"),
        ('<conditionalFormatting sqref=" "><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "missing_sqref"),
        ('<conditionalFormatting sqref="A0"><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "malformed_sqref"),
        ('<conditionalFormatting sqref="XFE1"><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "sqref_out_of_bounds"),
        ('<conditionalFormatting sqref="A1" pivot="maybe"><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "invalid_boolean"),
        ('<conditionalFormatting sqref="A1" xr:uid="not-a-guid"><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "invalid_uid"),
        ('<conditionalFormatting sqref="A1" bogus="1"><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "unknown_attribute"),
        ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="x"><formula>A1=1</formula></cfRule></conditionalFormatting>', "invalid_integer"),
        ('<conditionalFormatting sqref="A1"><cfRule priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>', "missing_required_attribute"),
        ('<conditionalFormatting sqref="A1"><cfRule type="madeUp" priority="1"/></conditionalFormatting>', "invalid_enum"),
        ('<conditionalFormatting sqref="A1"><bogus/></conditionalFormatting>', "unknown_owned_content"),
        ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><formula>A1=1</formula><bogus/></cfRule></conditionalFormatting>', "unknown_owned_content"),
        ('<conditionalFormatting sqref="A1"><cfRule type="colorScale" priority="1"/></conditionalFormatting>', "missing_required_payload"),
        ('<conditionalFormatting sqref="A1"><cfRule type="colorScale" priority="1"><colorScale><cfvo type="percent"/><cfvo type="max"/><color rgb="FF000000"/><color rgb="FFFFFFFF"/></colorScale></cfRule></conditionalFormatting>', "missing_required_attribute"),
        ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><colorScale><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/><color rgb="FFFFFFFF"/></colorScale></cfRule></conditionalFormatting>', "unexpected_payload"),
        ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><formula/></cfRule></conditionalFormatting>', "invalid_formula"),
    ),
)
def test_fails_closed_for_every_owned_field_family(fragment: str, code: str):
    with pytest.raises(NativeCfParseError) as failure:
        read_native_conditional_formatting("xl/worksheets/sheet1.xml", _worksheet(fragment))
    assert failure.value.code == code
    assert failure.value.owner_path.startswith("xl/worksheets/sheet1.xml#worksheet/")


@pytest.mark.parametrize(
    ("needle", "replacement", "code"),
    (
        ('dxfId="2"', 'dxfId="-1"', "invalid_integer"),
        ('stopIfTrue="0"', 'stopIfTrue="2"', "invalid_boolean"),
        ('operator="equal"', 'operator="inside"', "invalid_enum"),
        ('rank="10"', 'rank="0"', "integer_out_of_range"),
        ('stdDev="2"', 'stdDev="bad"', "invalid_integer"),
        ('equalAverage="false"', 'equalAverage="yes"', "invalid_boolean"),
        ('type="percentile"', 'type="bad"', "invalid_enum"),
        ('rgb="FF0000FF"', 'rgb="bad"', "invalid_color"),
        ('minLength="1"', 'minLength="101"', "integer_out_of_range"),
        ('axisPosition="middle"', 'axisPosition="bad"', "invalid_enum"),
        ('iconSet="3Arrows"', 'iconSet="bad"', "invalid_enum"),
    ),
)
def test_every_typed_rule_and_payload_field_rejects_invalid_mutation(needle: str, replacement: str, code: str):
    with pytest.raises(NativeCfParseError) as failure:
        read_native_conditional_formatting("xl/worksheets/sheet1.xml", _worksheet(_rules(6).replace(needle, replacement, 1)))
    assert failure.value.code == code


def test_duplicate_xml_attribute_is_a_deterministic_invalid_xml_fault():
    xml = _worksheet('<conditionalFormatting sqref="A1" sqref="B1"/>')
    with pytest.raises(NativeCfParseError) as failure:
        read_native_conditional_formatting("xl/worksheets/sheet1.xml", xml)
    assert failure.value.code == "invalid_xml"


def test_duplicate_rule_priority_is_rejected_across_container_boundaries():
    xml = _worksheet(
        '<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><formula>A1=1</formula></cfRule></conditionalFormatting>'
        '<conditionalFormatting sqref="B1"><cfRule type="expression" priority="1"><formula>B1=1</formula></cfRule></conditionalFormatting>'
    )
    with pytest.raises(NativeCfParseError) as failure:
        read_native_conditional_formatting("xl/worksheets/sheet1.xml", xml)
    assert failure.value.code == "duplicate_priority"


def test_conflicting_color_sources_and_icon_set_cardinality_fail_closed():
    conflicting_color = '<conditionalFormatting sqref="A1"><cfRule type="colorScale" priority="1"><colorScale><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000" theme="1"/><color rgb="FFFFFFFF"/></colorScale></cfRule></conditionalFormatting>'
    wrong_icon_count = '<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet iconSet="4Arrows"><cfvo type="percent" val="0"/><cfvo type="percent" val="33"/><cfvo type="percent" val="67"/></iconSet></cfRule></conditionalFormatting>'
    for fragment, code in ((conflicting_color, "invalid_color"), (wrong_icon_count, "invalid_payload_cardinality")):
        with pytest.raises(NativeCfParseError) as failure:
            read_native_conditional_formatting("xl/worksheets/sheet1.xml", _worksheet(fragment))
        assert failure.value.code == code
