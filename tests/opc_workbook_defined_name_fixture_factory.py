"""Deterministic direct ZIP/XML fixtures for workbook defined-name tests."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tests.opc_workbook_fixture_factory import OFFICE_REL_NS, REL_NS, SHEET_NS, relationship


_TIME = (1980, 1, 1, 0, 0, 0)


def workbook(defined_names: str = "", sheets: str | None = None) -> bytes:
    entries = sheets or (
        '<sheet name="Первый" sheetId="1" r:id="one"/>'
        '<sheet name="Лист &apos;Два&apos;" sheetId="2" r:id="two"/>'
    )
    return (
        f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets>{entries}</sheets>{defined_names}</workbook>'
    ).encode()


def package(destination: Path, *, workbook_xml: bytes | None = None, workbook_member: str = "xl/workbook.xml",
            extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    payload = workbook_xml or workbook()
    rels = (
        relationship("one", f"{OFFICE_REL_NS}/worksheet", "worksheets/first.xml")
        + relationship("two", f"{OFFICE_REL_NS}/worksheet", "worksheets/second.xml")
    )
    types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '</Types>'
    )
    members = (
        ("[Content_Types].xml", types.encode()),
        ("_rels/.rels", f'<Relationships xmlns="{REL_NS}">{relationship("root", f"{OFFICE_REL_NS}/officeDocument", "xl/workbook.xml")}</Relationships>'.encode()),
        (workbook_member, payload),
        ("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{REL_NS}">{rels}</Relationships>'.encode()),
        ("xl/worksheets/first.xml", b"<worksheet/>"),
        ("xl/worksheets/second.xml", b"<worksheet/>"),
        *extra_members,
    )
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        for name, value in members:
            info = ZipInfo(name, date_time=_TIME)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, value, compress_type=ZIP_DEFLATED, compresslevel=9)
    return destination
