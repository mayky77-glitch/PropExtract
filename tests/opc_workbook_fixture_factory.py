"""Namespace-valid synthetic OPC workbook fixture factory."""
from __future__ import annotations

from zipfile import ZIP_DEFLATED, ZipFile


CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def write_workbook(path, mutate=None, boundary=6):
    parts = {
        "[Content_Types].xml": f'''<Types xmlns="{CONTENT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>''',
        "_rels/.rels": f'''<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{DOC_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>''',
        "xl/workbook.xml": f'''<workbook xmlns="{SHEET}" xmlns:r="{DOC_REL}"><sheets><sheet name="First" sheetId="6" r:id="rId2"/><sheet name="Second" sheetId="104" state="hidden" r:id="rId10"/></sheets><definedNames><definedName name="Global">First!$A$1:$D$10</definedName><definedName name="Local" localSheetId="1" hidden="1">Second!$A$1</definedName></definedNames></workbook>''',
        "xl/_rels/workbook.xml.rels": f'''<Relationships xmlns="{PKG}"><Relationship Id="rId2" Type="{DOC_REL}/worksheet" Target="worksheets/sheet6.xml"/><Relationship Id="rId10" Type="{DOC_REL}/worksheet" Target="worksheets/sheet104.xml"/><Relationship Id="rId3" Type="{DOC_REL}/sharedStrings" Target="sharedStrings.xml"/><Relationship Id="rId4" Type="{DOC_REL}/styles" Target="styles.xml"/></Relationships>''',
        "xl/sharedStrings.xml": f'''<sst xmlns="{SHEET}" count="2" uniqueCount="2"><si><t>shared text</t></si><si><r><t>rich</t></r><r><t> text</t></r></si></sst>''',
        "xl/styles.xml": f'''<styleSheet xmlns="{SHEET}"><numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts><fonts count="1"><font><name val="Arial"/><sz val="11"/><b/><color rgb="FF112233"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills><borders count="1"><border><left style="thin"/><right/><top style="thin"/><bottom/></border></borders><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="164" fontId="0" fillId="1" borderId="0"><alignment horizontal="center"/><protection locked="0"/></xf></cellXfs></styleSheet>''',
        "xl/worksheets/sheet6.xml": f'''<worksheet xmlns="{SHEET}" xmlns:r="{DOC_REL}"><dimension ref="A1:D10"/><cols><col min="1" max="1" width="22.5" hidden="1" outlineLevel="2" style="1"/></cols><sheetData><row r="6" ht="18.5" hidden="1" outlineLevel="1" s="1"><c r="A6" t="s"><v>0</v></c><c r="B6" t="inlineStr"><is><t>inline text</t></is></c><c r="C6" s="1"><v>45292</v></c><c r="D6"><f t="shared" si="5" ref="D6:D10">SUM(C6:C10)</f><v>7</v></c></row><row r="10"><c r="A10" t="e"><v>#DIV/0!</v></c><c r="B10"><f t="array" ref="B10:C10">TRANSPOSE(A6:A7)</f><v>cache</v></c></row></sheetData><mergeCells count="1"><mergeCell ref="A6:B6"/></mergeCells><autoFilter ref="A6:D10"/><hyperlinks><hyperlink ref="A6" location="Second!A1" display="jump" tooltip="internal"/><hyperlink ref="B6" r:id="rId1"/></hyperlinks><conditionalFormatting sqref="C6"/></worksheet>''',
        "xl/worksheets/_rels/sheet6.xml.rels": f'''<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{DOC_REL}/hyperlink" Target="https://example.test/x" TargetMode="External"/></Relationships>''',
        "xl/worksheets/sheet104.xml": f'''<worksheet xmlns="{SHEET}"><dimension ref="A1:A1"/><sheetData><row r="104"><c r="A104" t="s"><v>1</v></c></row></sheetData></worksheet>''',
    }
    parts["xl/workbook.xml"] = parts["xl/workbook.xml"].replace('name="First"', f'name="First-{boundary}"')
    parts["xl/worksheets/sheet6.xml"] = parts["xl/worksheets/sheet6.xml"].replace('ref="A1:D10"', f'ref="A{boundary}:D{boundary + 4}"')
    if mutate:
        mutate(parts)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
