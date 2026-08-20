"""Direct ZIP/XML fixtures for strict style semantics."""
from __future__ import annotations
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from tests.opc_worksheet_cell_fixture_factory import OFFICE_REL_NS, REL_NS, SHEET_NS, relationship, worksheet

_TIME = (1980, 1, 1, 0, 0, 0)
STYLES_REL = f"{OFFICE_REL_NS}/styles"
STYLES_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"

def styles(body: str) -> bytes: return f'<styleSheet xmlns="{SHEET_NS}">{body}</styleSheet>'.encode()

def package(destination: Path, *, style_xml: bytes | None = None, styles_relationship: str | None = None, style_name: str = "xl/styles.xml", style_override: str | None = None, sheet_one: bytes | None = None, sheet_two: bytes | None = None, sheet_one_name: str = "xl/worksheets/first.xml", sheet_two_name: str = "xl/worksheets/second.xml", extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    workbook = (f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets><sheet name="Первый" sheetId="1" r:id="one"/><sheet name="Второй" sheetId="2" r:id="two"/></sheets></workbook>').encode()
    workbook_rels = relationship("one", f"{OFFICE_REL_NS}/worksheet", sheet_one_name.removeprefix("xl/")) + relationship("two", f"{OFFICE_REL_NS}/worksheet", sheet_two_name.removeprefix("xl/"))
    if styles_relationship is None: styles_relationship = relationship("style", STYLES_REL, "styles.xml")
    workbook_rels += styles_relationship
    override = style_override if style_override is not None else f'<Override PartName="/{style_name}" ContentType="{STYLES_CT}"/>'
    content = (f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/{sheet_one_name}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/{sheet_two_name}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>{override}</Types>').encode()
    default = styles('<numFmts count="1"><numFmt numFmtId="164" formatCode="0.00"/></numFmts><fonts count="1"><font><name val="Arial"/></font></fonts><fills count="1"><fill><patternFill/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>')
    members=[("[Content_Types].xml",content),("_rels/.rels",f'<Relationships xmlns="{REL_NS}">{relationship("root",f"{OFFICE_REL_NS}/officeDocument","xl/workbook.xml")}</Relationships>'.encode()),("xl/workbook.xml",workbook),("xl/_rels/workbook.xml.rels",f'<Relationships xmlns="{REL_NS}">{workbook_rels}</Relationships>'.encode()),(sheet_one_name,sheet_one or worksheet('<row r="6"><c r="A6" s="0"><v>1</v></c></row><row r="10"><c r="B10"><v>2</v></c></row><row r="104"><c r="C104" s="1"><v>3</v></c></row>')),(sheet_two_name,sheet_two or worksheet('<row r="6"><c r="A6"><v>1</v></c></row>')),(style_name,style_xml or default)] + list(extra_members)
    with ZipFile(destination,"w",compression=ZIP_DEFLATED,compresslevel=9,strict_timestamps=True) as archive:
        for name,payload in members:
            info=ZipInfo(name,date_time=_TIME); info.create_system=3; info.external_attr=0o100644<<16; info.compress_type=ZIP_DEFLATED; archive.writestr(info,payload,compress_type=ZIP_DEFLATED,compresslevel=9)
    return destination
