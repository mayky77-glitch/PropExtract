"""Deterministic direct ZIP/XML fixtures for workbook topology tests."""
from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_TIME = (1980, 1, 1, 0, 0, 0)


def relationship(identifier: str, type_uri: str, target: str, mode: str = "Internal") -> str:
    suffix = "" if mode == "Internal" else f' TargetMode="{mode}"'
    return f'<Relationship Id="{identifier}" Type="{type_uri}" Target="{target}"{suffix}/>'


def package(destination: Path, *, workbook_xml: bytes | None = None, root_relationships: str | None = None,
            workbook_relationships: str | None = None, worksheet_parts: tuple[str, ...] = ("xl/worksheets/sheet1.xml",),
            workbook_content_type: str | None = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
            workbook_member: str = "xl/workbook.xml", override_part_name: str = "/xl/workbook.xml",
            extra_overrides: tuple[tuple[str, str], ...] = (), extra_members: tuple[tuple[str, bytes], ...] = ()) -> Path:
    root = root_relationships or relationship("rWorkbook", f"{OFFICE_REL_NS}/officeDocument", "xl/workbook.xml")
    sheets = workbook_relationships or relationship("rSheet1", f"{OFFICE_REL_NS}/worksheet", "worksheets/sheet1.xml")
    workbook = workbook_xml or (
        f'<workbook xmlns="{SHEET_NS}" xmlns:r="{OFFICE_REL_NS}"><sheets>'
        '<sheet name="Main" sheetId="1" r:id="rSheet1"/></sheets></workbook>'
    ).encode()
    content_types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    if workbook_content_type is not None:
        content_types += f'<Override PartName="{override_part_name}" ContentType="{workbook_content_type}"/>'
    content_types += "".join(f'<Override PartName="{part_name}" ContentType="{content_type}"/>' for part_name, content_type in extra_overrides)
    content_types += "</Types>"
    members = (
        ("[Content_Types].xml", content_types.encode()),
        ("_rels/.rels", f'<Relationships xmlns="{REL_NS}">{root}</Relationships>'.encode()),
        (workbook_member, workbook),
        ("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{REL_NS}">{sheets}</Relationships>'.encode()),
        *((name, b"<worksheet/>") for name in worksheet_parts),
        *extra_members,
    )
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        for name, payload in members:
            info = ZipInfo(name, date_time=_TIME)
            info.create_system = 3; info.external_attr = 0o100644 << 16; info.compress_type = ZIP_DEFLATED
            archive.writestr(info, payload, compress_type=ZIP_DEFLATED, compresslevel=9)
    return destination
