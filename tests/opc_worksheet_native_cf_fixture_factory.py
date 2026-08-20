"""Direct ZIP/XML fixtures for native conditional-formatting presence."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tests.opc_workbook_fixture_factory import OFFICE_REL_NS, REL_NS, relationship

SML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_TIME = (1980, 1, 1, 0, 0, 0)


def worksheet(conditional_formatting: str = "") -> bytes:
    return f'<worksheet xmlns="{SML}" xmlns:x14="{X14}">{conditional_formatting}</worksheet>'.encode()


def package(destination: Path, *, sheet_one: bytes | None = None, sheet_two: bytes | None = None,
            sheet_one_name: str = "xl/worksheets/first.xml", extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    workbook = (f'<workbook xmlns="{SML}" xmlns:r="{OFFICE_REL_NS}"><sheets>'
                '<sheet name="Первый" sheetId="1" r:id="one"/>'
                '<sheet name="Второй" sheetId="2" r:id="two"/></sheets></workbook>').encode()
    workbook_rels = (relationship("one", f"{OFFICE_REL_NS}/worksheet", "worksheets/first.xml") +
                     relationship("two", f"{OFFICE_REL_NS}/worksheet", "worksheets/второй.xml"))
    overrides = (f'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                 f'<Override PartName="/{sheet_one_name}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                 '<Override PartName="/xl/worksheets/второй.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    members = [
        ("[Content_Types].xml", f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{overrides}</Types>'.encode()),
        ("_rels/.rels", f'<Relationships xmlns="{REL_NS}">{relationship("root", f"{OFFICE_REL_NS}/officeDocument", "xl/workbook.xml")}</Relationships>'.encode()),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{REL_NS}">{workbook_rels}</Relationships>'.encode()),
        (sheet_one_name, worksheet() if sheet_one is None else sheet_one),
        ("xl/worksheets/второй.xml", worksheet() if sheet_two is None else sheet_two),
    ]
    members.extend(extra_members)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        for name, payload in members:
            info = ZipInfo(name, date_time=_TIME)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, payload, compress_type=ZIP_DEFLATED, compresslevel=9)
    return destination
