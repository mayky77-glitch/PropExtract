from __future__ import annotations

from dataclasses import FrozenInstanceError
import pytest

from rns_import_server.ooxml_native_cf_reader import (
    INT32_MAX, MAIN_NS, UINT32_MAX, XR_NS, NativeCfParseError, NativeColorScale,
    NativeDataBar, NativeIconSet, read_native_conditional_formatting,
)

X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
def _ws(body: str) -> str:
    return f'<worksheet xmlns="{MAIN_NS}" xmlns:xr="{XR_NS}" xmlns:x14="{X14}">{body}</worksheet>'
def _ext(label: str) -> str:
    return f'<extLst><ext uri="{{{label}}}"><x14:payload>{label}</x14:payload></ext></extLst>'
def _rules(row: int) -> str:
    return f'''
    <conditionalFormatting sqref="A{row} B{row}:C{row}" pivot="true" xr:uid="{{01234567-89AB-CDEF-0123-456789ABCDEF}}">
      <cfRule type="expression" priority="1" dxfId="2" stopIfTrue="false"><formula>A{row}=1</formula>{_ext("rule")}</cfRule>
      <cfRule type="cellIs" priority="2" dxfId="3" operator="equal"><formula>1</formula></cfRule>
      <cfRule type="top10" priority="3" dxfId="4" rank="10" percent="false" bottom="true"/>
      <cfRule type="aboveAverage" priority="4" dxfId="5" aboveAverage="true" stdDev="2" equalAverage="false"/>
      <cfRule type="containsText" priority="5" dxfId="6" text="hello"><formula>SEARCH("hello",A{row})</formula></cfRule>
      <cfRule type="colorScale" priority="6"><colorScale>
        <cfvo type="min"/><cfvo type="percentile" val="50"/><cfvo type="max"/>
        <color rgb="FF0000FF"/><color theme="1" tint="-0.5"/><color indexed="64"/>
      </colorScale></cfRule>
      <cfRule type="dataBar" priority="7"><dataBar minLength="1" maxLength="99" showValue="false">
        <cfvo type="min"/><cfvo type="max"/><color auto="1"/>
      </dataBar></cfRule>
      <cfRule type="iconSet" priority="8"><iconSet iconSet="3Arrows" showValue="true" percent="false" reverse="false">
        <cfvo type="percent" val="0" gte="true"/><cfvo type="percent" val="33" gte="false"/><cfvo type="percent" val="67"/>
      </iconSet></cfRule>
      {_ext("container")}
    </conditionalFormatting>
    <conditionalFormatting sqref="D{row}" pivot="false"/>'''

@pytest.mark.parametrize("sheet", ("Sheet1", "Dashboard"))
@pytest.mark.parametrize("row", (6, 10, 104))
def test_complete_native_matrix_preserves_typed_ordered_models(sheet: str, row: int):
    result = read_native_conditional_formatting(f"xl/worksheets/{sheet}.xml", _ws(_rules(row)))
    group, empty = result.containers
    assert result.findings == () and group.owner_path == f"xl/worksheets/{sheet}.xml#worksheet/conditionalFormatting[1]"
    assert group.sqref == (f"A{row}", f"B{row}:C{row}") and group.pivot is True
    assert empty.rules == () and empty.pivot is False and empty.extension_list is None
    assert group.uid == "{01234567-89AB-CDEF-0123-456789ABCDEF}"
    assert group.extension_list and group.extension_list.extensions[0].uri == "{container}"
    expression, cell_is, top10, above, text, color, data, icon = group.rules
    assert expression.formulas == (f"A{row}=1",) and expression.extension_list
    assert cell_is.operator == "equal" and cell_is.formulas == ("1",)
    assert (top10.rank, top10.percent, top10.bottom) == (10, False, True)
    assert (above.above_average, above.standard_deviation, above.equal_average) == (True, 2, False)
    assert text.text == "hello" and text.formulas[0].startswith("SEARCH")
    assert isinstance(color.payload, NativeColorScale) and color.payload.thresholds[1].value == "50"
    assert isinstance(data.payload, NativeDataBar) and (data.payload.min_length, data.payload.max_length, data.payload.show_value) == (1,99,False)
    assert isinstance(icon.payload, NativeIconSet) and icon.payload.thresholds[1].greater_than_or_equal is False
    with pytest.raises(FrozenInstanceError): group.pivot = False  # type: ignore[misc]

@pytest.mark.parametrize(("attr","value"), (("",None), ('pivot="false"',False), ('pivot="true"',True)))
def test_pivot_tri_state_and_zero_containers(attr: str, value: bool | None):
    result=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(f'<conditionalFormatting sqref="A1" {attr}/>'))
    assert result.containers[0].pivot is value
    assert read_native_conditional_formatting("xl/worksheets/s.xml",_ws("")).containers == ()

@pytest.mark.parametrize("operator", ("between","notBetween","equal","notEqual","greaterThan","lessThan","greaterThanOrEqual","lessThanOrEqual","containsText","notContains","beginsWith","endsWith"))
def test_all_twelve_native_operators_are_preserved(operator: str):
    formulas = "<formula>1</formula><formula>2</formula>" if operator in ("between","notBetween") else "<formula>1</formula>"
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="cellIs" priority="1" operator="{operator}">{formulas}</cfRule></conditionalFormatting>'
    assert read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml)).containers[0].rules[0].operator == operator

@pytest.mark.parametrize(("xml","code"), (
    ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"/></conditionalFormatting>',"invalid_formula_cardinality"),
    ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><formula>1</formula><formula>2</formula></cfRule></conditionalFormatting>',"invalid_formula_cardinality"),
    ('<conditionalFormatting sqref="A1"><cfRule type="cellIs" priority="1" operator="between"><formula>1</formula></cfRule></conditionalFormatting>',"invalid_formula_cardinality"),
    ('<conditionalFormatting sqref="A1"><cfRule type="cellIs" priority="1" operator="equal"><formula>1</formula><formula>2</formula></cfRule></conditionalFormatting>',"invalid_formula_cardinality"),
    ('<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><formula>1</formula><formula>2</formula><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule></conditionalFormatting>',"invalid_formula_cardinality"),
    ('<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar gradient="true"><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule></conditionalFormatting>',"unknown_attribute"),
    ('<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet iconSet="3Stars"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"invalid_enum"),
    ('<conditionalFormatting sqref="A1"><cfRule type="colorScale" priority="1"><colorScale><cfvo type="autoMin"/><cfvo type="max"/><color rgb="FF000000"/><color rgb="FFFFFFFF"/></colorScale></cfRule></conditionalFormatting>',"invalid_enum"),
    ('<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar axisPosition="middle"><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule></conditionalFormatting>',"unknown_attribute"),
    ('<conditionalFormatting sqref="A1">unexpected<cfRule type="expression" priority="1"><formula>1</formula></cfRule></conditionalFormatting>',"mixed_content"),
    ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><formula>1</formula></cfRule>tail</conditionalFormatting>',"mixed_content"),
))
def test_formula_particles_x14_fields_and_mixed_owned_content_fail_closed(xml: str, code: str):
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == code

def test_extlst_is_owned_at_container_rule_and_cfvo_paths_with_x14_payload():
    xml=f'''<conditionalFormatting sqref="A1">{_ext("container")}
      <cfRule type="colorScale" priority="1"><colorScale>
      <cfvo type="min">{_ext("cfvo")}</cfvo><cfvo type="max"/>
      <color rgb="FF000000"/><color rgb="FFFFFFFF"/></colorScale>{_ext("rule")}</cfRule></conditionalFormatting>'''
    # extLst must follow cfRule at container level; moving it proves order too.
    xml=xml.replace(_ext("container"),"").replace("</conditionalFormatting>",_ext("container")+"</conditionalFormatting>")
    item=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml)).containers[0]
    assert item.extension_list.owner_path.endswith("/extLst")
    assert item.rules[0].extension_list.extensions[0].uri == "{rule}"
    assert item.rules[0].payload.thresholds[0].extension_list.extensions[0].uri == "{cfvo}"  # type: ignore[union-attr]

@pytest.mark.parametrize(("rank","percent","ok"), (("0","true",True),("100","true",True),("101","true",False),("1","false",True),("1000","false",True),("0","false",False),("1001","false",False)))
def test_top10_rank_uses_uint32_with_percent_semantics(rank: str, percent: str, ok: bool):
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="top10" priority="1" rank="{rank}" percent="{percent}"/></conditionalFormatting>'
    if ok: assert read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml)).containers[0].rules[0].rank == int(rank)
    else:
        with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
        assert error.value.code == "integer_out_of_range"

@pytest.mark.parametrize(("attribute","value","code"), (
    ("priority",str(INT32_MAX+1),"integer_out_of_range"),("dxfId",str(INT32_MAX+1),"integer_out_of_range"),
    ("rank",str(UINT32_MAX+1),"integer_out_of_range"),("stdDev",str(INT32_MAX+1),"integer_out_of_range"),
))
def test_field_specific_int32_uint32_boundaries(attribute: str, value: str, code: str):
    typ = "aboveAverage" if attribute=="stdDev" else "top10" if attribute=="rank" else "expression"
    formula="<formula>1</formula>" if typ=="expression" else ""
    rule_attribute = f'priority="{value}"' if attribute == "priority" else f'priority="1" {attribute}="{value}"'
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="{typ}" {rule_attribute}>{formula}</cfRule></conditionalFormatting>'
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == code

@pytest.mark.parametrize(("xml","code"), (
    ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1" rank="1"><formula>1</formula></cfRule></conditionalFormatting>',"invalid_attribute_for_rule_type"),
    ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1" text="x"><formula>1</formula></cfRule></conditionalFormatting>',"invalid_attribute_for_rule_type"),
    ('<conditionalFormatting sqref="A1"><cfRule type="aboveAverage" priority="1" stdDev="-1"/></conditionalFormatting>',"invalid_attribute_combination"),
    ('<conditionalFormatting sqref="A1"><cfRule type="aboveAverage" priority="1" equalAverage="true" stdDev="1"/></conditionalFormatting>',"invalid_attribute_combination"),
    ('<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1"><formula>1</formula></cfRule></conditionalFormatting><conditionalFormatting sqref="B1"><cfRule type="expression" priority="1"><formula>1</formula></cfRule></conditionalFormatting>',"duplicate_priority"),
    ('<conditionalFormatting sqref="A1" sqref="B1"/>',"invalid_xml"),
))
def test_rule_relations_duplicate_and_xml_faults_are_deterministic(xml: str, code: str):
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == code
