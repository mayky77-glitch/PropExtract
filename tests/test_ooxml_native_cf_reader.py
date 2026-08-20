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
    ("priority",str(INT32_MAX+1),"integer_out_of_range"),
    ("rank",str(UINT32_MAX+1),"integer_out_of_range"),("stdDev",str(INT32_MAX+1),"integer_out_of_range"),
))
def test_field_specific_int32_uint32_boundaries(attribute: str, value: str, code: str):
    typ = "aboveAverage" if attribute=="stdDev" else "top10" if attribute=="rank" else "expression"
    formula="<formula>1</formula>" if typ=="expression" else ""
    rule_attribute = f'priority="{value}"' if attribute == "priority" else f'priority="1" {attribute}="{value}"'
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="{typ}" {rule_attribute}>{formula}</cfRule></conditionalFormatting>'
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == code

@pytest.mark.parametrize(("value","expected"), (("2147483648",2147483648),(str(UINT32_MAX),UINT32_MAX),(" +00000042 ",42)))
def test_dxf_id_is_uint32_and_preserves_xsd_lexical_forms(value: str, expected: int):
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="expression" priority="+0001" dxfId="{value}"><formula>1</formula></cfRule></conditionalFormatting>'
    rule=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml)).containers[0].rules[0]
    assert (rule.priority, rule.dxf_id) == (1,expected)

@pytest.mark.parametrize(("value","code"), (("-1","invalid_integer"),(str(UINT32_MAX+1),"integer_out_of_range")))
def test_dxf_id_rejects_negative_and_uint32_overflow(value: str, code: str):
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1" dxfId="{value}"><formula>1</formula></cfRule></conditionalFormatting>'
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == code

@pytest.mark.parametrize(("field","value","expected"), (
    ("priority"," \t+00001\n ",1), ("stdDev"," +0002 ",2),
    ("rank"," +000001 ",1), ("dxfId","+00000042",42),
))
def test_integer_fields_accept_collapsed_xsd_lexical_forms(field: str, value: str, expected: int):
    typ = "aboveAverage" if field == "stdDev" else "top10" if field == "rank" else "expression"
    formula = "<formula>1</formula>" if typ == "expression" else ""
    attrs = f'priority="1" {field}="{value}"' if field != "priority" else f'priority="{value}"'
    rule=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(f'<conditionalFormatting sqref="A1"><cfRule type="{typ}" {attrs}>{formula}</cfRule></conditionalFormatting>')).containers[0].rules[0]
    assert {"priority":rule.priority,"stdDev":rule.standard_deviation,"rank":rule.rank,"dxfId":rule.dxf_id}[field] == expected

@pytest.mark.parametrize("value", ("+", "-", "1 2", "--1", "+-1"))
def test_integer_fields_reject_non_xsd_lexical_forms(value: str):
    xml=f'<conditionalFormatting sqref="A1"><cfRule type="expression" priority="{value}"><formula>1</formula></cfRule></conditionalFormatting>'
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == "invalid_integer"

@pytest.mark.parametrize(("attribute","field","rule"), (
    ("stopIfTrue","stop_if_true",'<cfRule type="expression" priority="1" {attribute}="{value}"><formula>1</formula></cfRule>'),
    ("aboveAverage","above_average",'<cfRule type="aboveAverage" priority="1" {attribute}="{value}"/>'),
    ("percent","percent",'<cfRule type="top10" priority="1" {attribute}="{value}"/>'),
    ("bottom","bottom",'<cfRule type="top10" priority="1" {attribute}="{value}"/>'),
    ("equalAverage","equal_average",'<cfRule type="aboveAverage" priority="1" {attribute}="{value}"/>'),
    ("showValue","show_value",'<cfRule type="dataBar" priority="1"><dataBar {attribute}="{value}"><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule>'),
    ("showValue","show_value",'<cfRule type="iconSet" priority="1"><iconSet {attribute}="{value}"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule>'),
    ("percent","percent",'<cfRule type="iconSet" priority="1"><iconSet {attribute}="{value}"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule>'),
    ("reverse","reverse",'<cfRule type="iconSet" priority="1"><iconSet {attribute}="{value}"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule>'),
    ("gte","greater_than_or_equal",'<cfRule type="iconSet" priority="1"><iconSet><cfvo type="percent" val="0" {attribute}="{value}"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule>'),
))
@pytest.mark.parametrize(("value","expected"), ((None,None),("false",False),("true",True)))
def test_rule_and_payload_boolean_fields_are_frozen_tri_state(attribute: str, field: str, rule: str, value: str | None, expected: bool | None):
    rendered = "" if value is None else f'{attribute}="{value}"'
    item=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(f'<conditionalFormatting sqref="A1">{rule.format(attribute=attribute,value=value or "") if value is not None else rule.replace(" {attribute}=\"{value}\"", "").replace("{attribute}=\"{value}\"", "")}</conditionalFormatting>')).containers[0].rules[0]
    target = item.payload.thresholds[0] if attribute == "gte" else item.payload if "<dataBar" in rule or "<iconSet" in rule else item
    assert getattr(target,field) is expected
    with pytest.raises(FrozenInstanceError): setattr(target,field,not bool(expected))

@pytest.mark.parametrize(("xml","code"), (
    ('<conditionalFormatting sqref="A1" xr:uid="invalid"/>',"invalid_uid"),
    ('<conditionalFormatting sqref="A0"/>',"malformed_sqref"), ('<conditionalFormatting sqref=" "/>',"missing_sqref"),
    ('<conditionalFormatting sqref="A1" pivot="yes"/>',"invalid_boolean"),
    ('<conditionalFormatting sqref="A1"><cfRule priority="1"><formula>1</formula></cfRule></conditionalFormatting>',"missing_required_attribute"),
    ('<conditionalFormatting sqref="A1"><cfRule type="expression"><formula>1</formula></cfRule></conditionalFormatting>',"missing_required_attribute"),
))
def test_direct_contract_faults_are_explicit(xml: str, code: str):
    with pytest.raises(NativeCfParseError) as error: read_native_conditional_formatting("xl/worksheets/s.xml",_ws(xml))
    assert error.value.code == code

def _owned_attribute_target(result, owner: str):
    group = result.containers[0]
    rule = group.rules[0] if group.rules else None
    if owner == "group": return group
    assert rule is not None
    if owner == "rule": return rule
    assert rule.payload is not None
    if owner == "payload": return rule.payload
    if owner == "color": return rule.payload.color  # type: ignore[union-attr]
    return rule.payload.thresholds[0]  # type: ignore[union-attr]

@pytest.mark.parametrize(("owner","field","template","first","second","expected_first","expected_second"), (
    ("group","sqref",'<conditionalFormatting sqref="TOKEN"/>',"A1 B2:C2","D3",("A1","B2:C2"),("D3",)),
    ("group","pivot",'<conditionalFormatting sqref="A1" pivot="TOKEN"/>',"false","true",False,True),
    ("group","uid",'<conditionalFormatting sqref="A1" xr:uid="TOKEN"/>',"{01234567-89AB-CDEF-0123-456789ABCDEF}","{89ABCDEF-0123-4567-89AB-CDEF01234567}","{01234567-89AB-CDEF-0123-456789ABCDEF}","{89ABCDEF-0123-4567-89AB-CDEF01234567}"),
    ("rule","type",'<conditionalFormatting sqref="A1"><cfRule type="TOKEN" priority="1"><formula>1</formula></cfRule></conditionalFormatting>',"expression","duplicateValues","expression","duplicateValues"),
    ("rule","priority",'<conditionalFormatting sqref="A1"><cfRule type="expression" priority="TOKEN"><formula>1</formula></cfRule></conditionalFormatting>',"1","2",1,2),
    ("rule","dxf_id",'<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1" dxfId="TOKEN"><formula>1</formula></cfRule></conditionalFormatting>',"2","3",2,3),
    ("rule","stop_if_true",'<conditionalFormatting sqref="A1"><cfRule type="expression" priority="1" stopIfTrue="TOKEN"><formula>1</formula></cfRule></conditionalFormatting>',"false","true",False,True),
    ("rule","above_average",'<conditionalFormatting sqref="A1"><cfRule type="aboveAverage" priority="1" aboveAverage="TOKEN"/> </conditionalFormatting>',"false","true",False,True),
    ("rule","percent",'<conditionalFormatting sqref="A1"><cfRule type="top10" priority="1" percent="TOKEN"/> </conditionalFormatting>',"false","true",False,True),
    ("rule","bottom",'<conditionalFormatting sqref="A1"><cfRule type="top10" priority="1" bottom="TOKEN"/> </conditionalFormatting>',"false","true",False,True),
    ("rule","operator",'<conditionalFormatting sqref="A1"><cfRule type="cellIs" priority="1" operator="TOKEN"><formula>1</formula></cfRule></conditionalFormatting>',"equal","greaterThan","equal","greaterThan"),
    ("rule","text",'<conditionalFormatting sqref="A1"><cfRule type="containsText" priority="1" text="TOKEN"><formula>1</formula></cfRule></conditionalFormatting>',"a","b","a","b"),
    ("rule","time_period",'<conditionalFormatting sqref="A1"><cfRule type="timePeriod" priority="1" timePeriod="TOKEN"><formula>1</formula></cfRule></conditionalFormatting>',"today","tomorrow","today","tomorrow"),
    ("rule","rank",'<conditionalFormatting sqref="A1"><cfRule type="top10" priority="1" rank="TOKEN"/> </conditionalFormatting>',"1","2",1,2),
    ("rule","standard_deviation",'<conditionalFormatting sqref="A1"><cfRule type="aboveAverage" priority="1" stdDev="TOKEN"/> </conditionalFormatting>',"1","2",1,2),
    ("rule","equal_average",'<conditionalFormatting sqref="A1"><cfRule type="aboveAverage" priority="1" equalAverage="TOKEN"/> </conditionalFormatting>',"false","true",False,True),
    ("payload","min_length",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar minLength="TOKEN"><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule></conditionalFormatting>',"1","2",1,2),
    ("payload","max_length",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar maxLength="TOKEN"><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule></conditionalFormatting>',"98","99",98,99),
    ("payload","show_value",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar showValue="TOKEN"><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000"/></dataBar></cfRule></conditionalFormatting>',"false","true",False,True),
    ("payload","icon_set",'<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet iconSet="TOKEN"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"3Arrows","3Flags","3Arrows","3Flags"),
    ("payload","percent",'<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet percent="TOKEN"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"false","true",False,True),
    ("payload","reverse",'<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet reverse="TOKEN"><cfvo type="percent" val="0"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"false","true",False,True),
    ("color","rgb",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="TOKEN"/></dataBar></cfRule></conditionalFormatting>',"FF000000","FFFFFFFF","FF000000","FFFFFFFF"),
    ("color","indexed",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color indexed="TOKEN"/></dataBar></cfRule></conditionalFormatting>',"1","2",1,2),
    ("color","theme",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color theme="TOKEN"/></dataBar></cfRule></conditionalFormatting>',"1","2",1,2),
    ("color","auto",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color auto="TOKEN"/></dataBar></cfRule></conditionalFormatting>',"false","true",False,True),
    ("color","tint",'<conditionalFormatting sqref="A1"><cfRule type="dataBar" priority="1"><dataBar><cfvo type="min"/><cfvo type="max"/><color rgb="FF000000" tint="TOKEN"/></dataBar></cfRule></conditionalFormatting>',"-0.5","0.5",-0.5,0.5),
    ("cfvo","type",'<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet><cfvo type="TOKEN" val="1"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"percent","percentile","percent","percentile"),
    ("cfvo","value",'<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet><cfvo type="percent" val="TOKEN"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"1","2","1","2"),
    ("cfvo","greater_than_or_equal",'<conditionalFormatting sqref="A1"><cfRule type="iconSet" priority="1"><iconSet><cfvo type="percent" val="1" gte="TOKEN"/><cfvo type="percent" val="50"/><cfvo type="percent" val="90"/></iconSet></cfRule></conditionalFormatting>',"false","true",False,True),
))
def test_owned_attributes_preserve_explicit_mutations(owner: str, field: str, template: str, first: str, second: str, expected_first, expected_second):
    original=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(template.replace("TOKEN",first)))
    mutated=read_native_conditional_formatting("xl/worksheets/s.xml",_ws(template.replace("TOKEN",second)))
    assert getattr(_owned_attribute_target(original,owner),field) == expected_first
    assert getattr(_owned_attribute_target(mutated,owner),field) == expected_second

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
