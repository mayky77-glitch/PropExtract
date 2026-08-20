"""Direct ZIP/XML fixture builder for the strict worksheet-cell reader."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tests.opc_workbook_fixture_factory import OFFICE_REL_NS, REL_NS, SHEET_NS, relationship

_TIME = (1980, 1, 1, 0, 0, 0)


def worksheet(body: str, hyperlinks: str = "") -> bytes:
    return f'<worksheet xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheetData>{body}</sheetData>{hyperlinks}</worksheet>'.encode()


def package(destination: Path, *, sheet_one: bytes | None = None, sheet_two: bytes | None = None,
            sheet_one_name: str = "xl/worksheets/first.xml", sheet_two_name: str = "xl/worksheets/второй.xml",
            sheet_one_rels: str = "", extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    workbook = (f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets>'
                '<sheet name="Первый" sheetId="1" r:id="one"/>'
                '<sheet name="Второй" sheetId="2" r:id="two"/></sheets></workbook>').encode()
    workbook_rels = (relationship("one", f"{OFFICE_REL_NS}/worksheet", "worksheets/first.xml") +
                     relationship("two", f"{OFFICE_REL_NS}/worksheet", "worksheets/второй.xml"))
    overrides = (f'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                 f'<Override PartName="/{sheet_one_name}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                 f'<Override PartName="/{sheet_two_name}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    members = [
        ("[Content_Types].xml", f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{overrides}</Types>'.encode()),
        ("_rels/.rels", f'<Relationships xmlns="{REL_NS}">{relationship("root", f"{OFFICE_REL_NS}/officeDocument", "xl/workbook.xml")}</Relationships>'.encode()),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{REL_NS}">{workbook_rels}</Relationships>'.encode()),
        (sheet_one_name, sheet_one or worksheet('<row r="6"><c r="A6"><v>7</v></c></row><row r="10"><c r="B10" t="inlineStr"><is><t>текст</t></is></c></row><row r="104"><c r="C104"><f>SUM(A6)</f><v>7</v></c></row>')),
        (sheet_two_name, sheet_two or worksheet('<row r="6"><c r="A6" t="s"><v>4</v></c></row>')),
    ]
    if sheet_one_rels:
        members.append(("xl/worksheets/_rels/first.xml.rels", f'<Relationships xmlns="{REL_NS}">{sheet_one_rels}</Relationships>'.encode()))
    members.extend(extra_members)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        for name, payload in members:
            info = ZipInfo(name, date_time=_TIME); info.create_system = 3; info.external_attr = 0o100644 << 16; info.compress_type = ZIP_DEFLATED
            archive.writestr(info, payload, compress_type=ZIP_DEFLATED, compresslevel=9)
    return destination
