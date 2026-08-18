"""Namespace-valid worksheet XML fixtures for native and x14 rule semantics."""
from __future__ import annotations

X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM = "http://schemas.microsoft.com/office/excel/2006/main"


def worksheet_parts(boundary: int = 6, mutate=None) -> dict[str, bytes]:
    end = boundary + 4
    parts = {
        f"xl/worksheets/sheet{boundary}.xml": f'''<worksheet xmlns="{X}" xmlns:x14="{X14}" xmlns:xm="{XM}">
<conditionalFormatting sqref="A{boundary}:A{end} C{boundary}:C{end}"><cfRule type="cellIs" priority="2" stopIfTrue="1" operator="greaterThan" dxfId="3" custom="keep"><formula>10</formula><formula>20</formula><unknown/></cfRule></conditionalFormatting>
<dataValidations count="1"><dataValidation type="whole" operator="between" allowBlank="1" showErrorMessage="0" showInputMessage="1" sqref="B{boundary}:B{end} D{boundary}:D{end}" custom="keep"><formula1>1</formula1><formula2>9</formula2><future/></dataValidation></dataValidations>
<extLst><ext uri="{{test}}"><x14:conditionalFormattings><x14:conditionalFormatting><xm:sqref>E{boundary}:E{end} G{boundary}:G{end}</xm:sqref><x14:cfRule type="expression" priority="7" dxfId="4" id="{{id-{boundary}}}" custom="keep"><x14:formula>A{boundary}&gt;0</x14:formula><x14:future/></x14:cfRule></x14:conditionalFormatting></x14:conditionalFormattings><x14:dataValidations count="1"><x14:dataValidation type="list" allowBlank="0" showErrorMessage="1" showInputMessage="0" uid="{{uid-{boundary}}}" custom="keep"><x14:formula1><xm:f>"yes,no"</xm:f></x14:formula1><xm:sqref>F{boundary}:F{end} H{boundary}:H{end}</xm:sqref><x14:future/></x14:dataValidation></x14:dataValidations></ext></extLst>
</worksheet>'''.encode(),
        f"xl/worksheets/other{boundary}.xml": f'''<worksheet xmlns="{X}"><dataValidations><dataValidation type="date" operator="greaterThan" sqref="A{boundary}"><formula1>45292</formula1></dataValidation></dataValidations></worksheet>'''.encode(),
    }
    if mutate:
        mutate(parts)
    return parts
