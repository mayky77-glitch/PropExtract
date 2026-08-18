import pytest
from rns_import_server.ooxml_x14_cf_reader import X14CFError,read_x14_conditional_formats
X14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main";XM="http://schemas.microsoft.com/office/excel/2006/main"
def part(sheet,row,formulas="<xm:f>A1</xm:f>"):
 return f'<worksheet xmlns:x14="{X14}" xmlns:xm="{XM}"><x14:conditionalFormattings><x14:conditionalFormatting><xm:sqref a="x">A{row} B{row}</xm:sqref><x14:cfRule type="expression" priority="{row}" id="{{{sheet}}}" activePresent="1">{formulas}<x14:dxf><x14:font/></x14:dxf></x14:cfRule></x14:conditionalFormatting><x14:conditionalFormatting/></x14:conditionalFormattings></worksheet>'.encode()
@pytest.mark.parametrize("sheet,row",[("Sheet1",6),("Sheet1",10),("Dashboard",104)])
def test_complete_groups_rules_and_owner(sheet,row):
 c=read_x14_conditional_formats({sheet:part(sheet,row)})[0];assert len(c.groups)==2;rule=c.groups[0].rules[0];assert (rule.worksheet,rule.group,rule.order,rule.priority,rule.uid,rule.sqref)==(sheet,0,0,row,f"{{{sheet}}}",(f"A{row}",f"B{row}"));assert rule.dxf_xml and rule.sqref_attributes==(("a","x"),)
@pytest.mark.parametrize("formulas,code",[("".join("<xm:f>x</xm:f>" for _ in range(4)),"formula-cardinality"),("<x14:bad/>","unknown-rule-child")])
def test_fail_closed(formulas,code):
 with pytest.raises(X14CFError,match=code):read_x14_conditional_formats({"Sheet1":part("Sheet1",6,formulas)})
