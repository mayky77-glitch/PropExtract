"""Direct OPC fixtures for X14 conditional-formatting owner topology."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tests.opc_workbook_fixture_factory import OFFICE_REL_NS, REL_NS, relationship

SML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
X14 = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM = "http://schemas.microsoft.com/office/excel/2006/main"
CF_URI = "{78C0D931-6437-407d-A8EE-F0AAD7539E65}"
DV_URI = "{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"
_TIME = (1980, 1, 1, 0, 0, 0)


def worksheet(body: str = "") -> bytes:
    return f'<worksheet xmlns="{SML}" xmlns:x14="{X14}" xmlns:xm="{XM}">{body}</worksheet>'.encode()


def package(destination: Path, *, sheet_one: bytes | None = None, sheet_two: bytes | None = None) -> Path:
    workbook = (f'<workbook xmlns="{SML}" xmlns:r="{OFFICE_REL_NS}"><sheets>'
                '<sheet name="Первый" sheetId="1" r:id="one"/><sheet name="Второй" sheetId="2" r:id="two"/>'
                '</sheets></workbook>').encode()
    rels = relationship("one", f"{OFFICE_REL_NS}/worksheet", "worksheets/first.xml") + relationship("two", f"{OFFICE_REL_NS}/worksheet", "worksheets/second.xml")
    types = (f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             '<Override PartName="/xl/worksheets/first.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
             '<Override PartName="/xl/worksheets/second.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>').encode()
    members = (("[Content_Types].xml", types), ("_rels/.rels", f'<Relationships xmlns="{REL_NS}">{relationship("root", f"{OFFICE_REL_NS}/officeDocument", "xl/workbook.xml")}</Relationships>'.encode()), ("xl/workbook.xml", workbook), ("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{REL_NS}">{rels}</Relationships>'.encode()), ("xl/worksheets/first.xml", sheet_one or worksheet()), ("xl/worksheets/second.xml", sheet_two or worksheet()))
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in members:
            info = ZipInfo(name, date_time=_TIME); info.compress_type = ZIP_DEFLATED
            archive.writestr(info, payload)
    return destination
