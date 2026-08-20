from __future__ import annotations
from dataclasses import FrozenInstanceError
from dataclasses import asdict
import pytest
from rns_import_server.opc_style_semantic_reader import OPCStyleSemanticReaderError, read_workbook_style_semantics
from tests.opc_style_fixture_factory import STYLES_CT, STYLES_REL, package, relationship, styles

def error(path):
    with pytest.raises(OPCStyleSemanticReaderError) as caught: read_workbook_style_semantics(path)
    return caught.value.as_tuple()

def test_reads_immutable_ordered_styles_and_explicit_boundary_usage(tmp_path):
    body = ('<numFmts count="1"><numFmt numFmtId="164" formatCode="0.00"/></numFmts>'
            '<fonts count="1"><font><name val="Arial"/><b/><color rgb="FF010203"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="solid"><fgColor theme="1" tint="0.2"/></patternFill></fill><fill><gradientFill degree="45"><stop position="0"><color rgb="FF000000"/></stop></gradientFill></fill></fills>'
            '<borders count="1"><border diagonalUp="1"><left style="thin"><color indexed="2"/></left><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="1" borderId="0" xfId="0" applyNumberFormat="1" applyFont="0" applyFill="1" applyBorder="0" applyAlignment="1" applyProtection="1" quotePrefix="1" pivotButton="0"><alignment horizontal="center" textRotation="45" wrapText="1" indent="2"/><protection locked="0" hidden="1"/></xf></cellXfs>')
    second = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="6"><c r="A6" s="1"><v>1</v></c></row><row r="10"><c r="B10" s="0"><v>2</v></c></row><row r="104"><c r="C104" s="1"><v>3</v></c></row></sheetData></worksheet>'
    result=read_workbook_style_semantics(package(tmp_path/"good.xlsx",style_xml=styles(body), sheet_two=second))
    assert result.style_part.value=="xl/styles.xml"
    assert [x.num_fmt_id for x in result.style_table.number_formats]==[164]
    assert result.style_table.fonts[0].color and result.style_table.fonts[0].color.rgb=="FF010203"
    assert result.style_table.fills[1].stops[0][0]==0.0
    assert [(x.coordinate,x.style_index) for x in result.worksheets[0].cells]==[("A6",0),("B10",0),("C104",1)]
    assert [(x.coordinate,x.style_index) for x in result.worksheets[1].cells]==[("A6",1),("B10",0),("C104",1)]
    assert result.style_table.cell_xfs[1].apply_number_format is True
    assert result.style_table.cell_xfs[1].apply_font is False
    assert result.style_table.cell_xfs[1].apply_fill is True
    assert result.style_table.cell_xfs[1].apply_border is False
    assert result.style_table.cell_xfs[1].apply_alignment is True
    assert result.style_table.cell_xfs[1].apply_protection is True
    assert result.style_table.cell_xfs[1].quote_prefix is True and result.style_table.cell_xfs[1].pivot_button is False
    with pytest.raises(FrozenInstanceError): result.style_table.fonts[0].bold=False

@pytest.mark.parametrize(("kwargs","expected"),[
    ({"styles_relationship":""},("missing-styles-relationship","xl/workbook.xml","Type",STYLES_REL)),
    ({"styles_relationship":relationship("a",STYLES_REL,"styles.xml")+relationship("b",STYLES_REL,"styles.xml")},("ambiguous-styles-relationship","xl/workbook.xml","Type",STYLES_REL)),
    ({"styles_relationship":relationship("a",STYLES_REL,"https://x","External")},("external-styles-relationship","xl/workbook.xml","TargetMode","External")),
    ({"style_override":""},("missing-styles-content-type","xl/styles.xml","PartName","/xl/styles.xml")),
    ({"style_override":f'<Override PartName="/xl/styles.xml" ContentType="{STYLES_CT}"/><Override PartName="/xl/styles.xml" ContentType="{STYLES_CT}"/>'},("ambiguous-styles-content-type","xl/styles.xml","PartName","/xl/styles.xml")),
    ({"style_override":'<Override PartName="/xl/styles.xml" ContentType="no"/>'},("wrong-styles-content-type","xl/styles.xml","ContentType","no")),
])
def test_relationship_and_content_type_failures(tmp_path,kwargs,expected): assert error(package(tmp_path/"bad.xlsx",**kwargs))==expected

def test_dangling_relationship_preserves_dependency_failure(tmp_path):
    from rns_import_server.opc_workbook_topology import OPCWorkbookTopologyError
    with pytest.raises(OPCWorkbookTopologyError) as caught:
        read_workbook_style_semantics(package(tmp_path / "gone.xlsx", styles_relationship=relationship("a", STYLES_REL, "gone.xml")))
    assert caught.value.as_tuple() == ("missing-internal-target", "xl/workbook.xml", "Target", "gone.xml")

def test_wrong_relationship_type_and_canonical_aliases_are_not_accepted(tmp_path):
    wrong = relationship("style", "https://example.test/not-styles", "styles.xml")
    assert error(package(tmp_path / "wrong-type.xlsx", styles_relationship=wrong)) == ("wrong-styles-relationship-type", "xl/workbook.xml", "Type", "https://example.test/not-styles")
    unrelated = relationship("other", "https://example.test/not-styles", "mystyles.xml")
    assert error(package(tmp_path / "unrelated-type.xlsx", styles_relationship=unrelated, extra_members=(("xl/mystyles.xml", b"<x/>"),))) == ("missing-styles-relationship", "xl/workbook.xml", "Type", STYLES_REL)
    custom_name = "xl/custom-style-part.xml"
    custom_wrong = relationship("style", "https://example.test/not-styles", "custom-style-part.xml")
    assert error(package(tmp_path / "custom-wrong-type.xlsx", style_name=custom_name, styles_relationship=custom_wrong)) == ("wrong-styles-relationship-type", "xl/workbook.xml", "Type", "https://example.test/not-styles")
    exact_override = f'<Override PartName="/xl/styles.xml" ContentType="{STYLES_CT}"/>'
    assert error(package(tmp_path / "member-alias.xlsx", style_name="xl/%73tyles.xml", style_override=exact_override)) == ("noncanonical-styles-member", "xl/styles.xml", "member", "xl/%73tyles.xml")
    override = f'<Override PartName="/xl/%73tyles.xml" ContentType="{STYLES_CT}"/>'
    assert error(package(tmp_path / "override-alias.xlsx", style_override=override)) == ("noncanonical-styles-content-type", "xl/styles.xml", "PartName", "/xl/%73tyles.xml")

@pytest.mark.parametrize(("xml","expected"),[
    (b"<styleSheet/>",("invalid-styles-root","xl/styles.xml","root","styleSheet")),
    (b"<styleSheet",("malformed-styles-xml","xl/styles.xml","xml","xml")),
    (styles('<fonts count="2"><font/></fonts>'),("invalid-style-count","xl/styles.xml","count","2")),
    (styles('<numFmts count="2"><numFmt numFmtId="164" formatCode="x"/><numFmt numFmtId="164" formatCode="y"/></numFmts>'),("duplicate-numFmt-id","xl/styles.xml","numFmtId","164")),
    (styles('<fonts count="1"><font bad="1"/></fonts>'),("unknown-styles-attribute","xl/styles.xml","attribute","bad")),
    (styles('<fonts count="1"><font/></fonts><fills count="1"><fill><patternFill/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="2" fillId="0" borderId="0"/></cellStyleXfs>'),("invalid-style-index","xl/styles.xml","xf","component")),
])
def test_style_xml_failures(tmp_path,xml,expected): assert error(package(tmp_path/"bad.xlsx",style_xml=xml))==expected

def test_invalid_xf_id_and_cell_style_reference(tmp_path):
    base='<fonts count="1"><font/></fonts><fills count="1"><fill><patternFill/></fill></fills><borders count="1"><border/></borders>'
    assert error(package(tmp_path/"xf.xlsx",style_xml=styles(base+'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="1"/></cellXfs>')))==("invalid-xf-id","xl/styles.xml","xfId","1")
    sheet=b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="6"><c r="A6" s="2"><v>1</v></c></row></sheetData></worksheet>'
    assert error(package(tmp_path/"cell.xlsx",sheet_one=sheet))==("invalid-cell-style-reference","xl/worksheets/first.xml","s","2")

@pytest.mark.parametrize(("fragment", "expected"), [
    ('<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" bad="1"/>', ("unknown-styles-attribute", "xl/styles.xml", "attribute", "bad")),
    ('<fonts count="1"><font><u val="bogus"/></font></fonts>', ("invalid-styles-content", "xl/styles.xml", "u", "bogus")),
    ('<fonts count="1"><font><color rgb="bad"/></font></fonts>', ("invalid-styles-content", "xl/styles.xml", "rgb", "bad")),
    ('<fills count="1"><fill bad="1"><patternFill/></fill></fills>', ("unknown-styles-attribute", "xl/styles.xml", "attribute", "bad")),
])
def test_strict_root_font_color_and_fill_lexicals(tmp_path, fragment, expected):
    xml = fragment.encode() if fragment.startswith("<styleSheet") else styles(fragment)
    assert error(package(tmp_path / "strict.xlsx", style_xml=xml)) == expected

def test_xf_child_order_and_nested_cells_cannot_change_style_usage(tmp_path):
    base = '<fonts count="1"><font/></fonts><fills count="1"><fill><patternFill/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    wrong_order = styles(base + '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><protection locked="1"/><alignment horizontal="left"/></xf></cellXfs>')
    assert error(package(tmp_path / "order.xlsx", style_xml=wrong_order)) == ("invalid-styles-content", "xl/styles.xml", "xf", "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}alignment")
    nested = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="6"><c r="A6"><v>1</v></c></row></sheetData><extLst><ext><c r="XFD1048576" s="0"/></ext></extLst></worksheet>'
    assert error(package(tmp_path / "nested.xlsx", sheet_one=nested)) == ("invalid-styles-content", "xl/worksheets/first.xml", "cell", "nested")

class _OneShot:
    def __init__(self,path): self.path=path; self.calls=0
    def __fspath__(self): self.calls+=1; return self.path if self.calls==1 else (_ for _ in ()).throw(TypeError())
def test_coerces_path_once(tmp_path):
    path=_OneShot(str(package(tmp_path/"one.xlsx"))); assert read_workbook_style_semantics(path).style_part.value=="xl/styles.xml"; assert path.calls==1

def test_typed_scalars_defaults_and_public_records(tmp_path):
    body = ('<fonts count="2"><font/><font><sz val="11.5"/><color auto="1" tint="-1"/><u/><condense val="0"/><extend/></font></fonts>'
            '<fills count="1"><fill><gradientFill><stop position="1"><color indexed="2"/></stop></gradientFill></fill></fills>'
            '<borders count="1"><border diagonalUp="1" diagonalDown="0" outline="1"><left style="thin"><color rgb="FF000001"/></left><right style="double"/><top/><bottom/><diagonal/><vertical/><horizontal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"><alignment horizontal="left" vertical="top" textRotation="180" wrapText="1" shrinkToFit="0" indent="250" relativeIndent="-15" justifyLastLine="1" readingOrder="2"/><protection locked="1" hidden="0"/></xf><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs>')
    result = read_workbook_style_semantics(package(tmp_path / "typed.xlsx", style_xml=styles(body)))
    empty, font = result.style_table.fonts
    assert empty.size is None and empty.underline is None and empty.condense is False and empty.extend is False
    assert font.size == 11.5 and font.color and font.color.auto is True and font.color.tint == -1.0
    assert font.underline == "single" and font.condense is False and font.extend is True
    assert result.style_table.fills[0].stops[0][0] == 1.0
    alignment = result.style_table.cell_xfs[0].alignment
    protection = result.style_table.cell_xfs[0].protection
    border = result.style_table.borders[0]
    assert alignment and (alignment.horizontal, alignment.vertical, alignment.text_rotation, alignment.wrap_text, alignment.shrink_to_fit, alignment.indent, alignment.relative_indent, alignment.justify_last_line, alignment.reading_order) == ("left", "top", 180, True, False, 250, -15, True, 2)
    assert protection and (protection.locked, protection.hidden) == (True, False)
    assert (border.left.style, border.left.color.rgb if border.left.color else None, border.right.style, border.top.style, border.bottom.style, border.diagonal.style, border.diagonal_up, border.diagonal_down, border.outline) == ("thin", "FF000001", "double", None, None, None, True, False, True)
    assert border.vertical and border.horizontal and border.vertical.style is None and border.horizontal.style is None
    assert asdict(result) == {
        "style_part": {"value": "xl/styles.xml"},
        "style_table": {
            "number_formats": (),
            "fonts": (
                {"name": None, "size": None, "family": None, "charset": None, "scheme": None, "color": None,
                 "bold": False, "italic": False, "underline": None, "strike": False, "outline": False,
                 "shadow": False, "condense": False, "extend": False, "vert_align": None},
                {"name": None, "size": 11.5, "family": None, "charset": None, "scheme": None,
                 "color": {"rgb": None, "indexed": None, "theme": None, "tint": -1.0, "auto": True},
                 "bold": False, "italic": False, "underline": "single", "strike": False, "outline": False,
                 "shadow": False, "condense": False, "extend": True, "vert_align": None},
            ),
            "fills": ({"kind": "gradient", "pattern_type": None, "foreground": None, "background": None,
                       "gradient_type": None, "degree": None, "left": None, "right": None, "top": None,
                       "bottom": None, "stops": ((1.0, {"rgb": None, "indexed": 2, "theme": None,
                                                        "tint": None, "auto": None}),)},),
            "borders": ({
                "left": {"style": "thin", "color": {"rgb": "FF000001", "indexed": None, "theme": None,
                                                       "tint": None, "auto": None}},
                "right": {"style": "double", "color": None},
                "top": {"style": None, "color": None},
                "bottom": {"style": None, "color": None},
                "diagonal": {"style": None, "color": None},
                "diagonal_up": True, "diagonal_down": False, "outline": True,
                "vertical": {"style": None, "color": None},
                "horizontal": {"style": None, "color": None},
            },),
            "cell_style_xfs": ({
                "num_fmt_id": 0, "font_id": 0, "fill_id": 0, "border_id": 0, "xf_id": None,
                "apply_number_format": None, "apply_font": None, "apply_fill": None, "apply_border": None,
                "apply_alignment": None, "apply_protection": None, "quote_prefix": None, "pivot_button": None,
                "alignment": None, "protection": None,
            },),
            "cell_xfs": (
                {"num_fmt_id": 0, "font_id": 1, "fill_id": 0, "border_id": 0, "xf_id": 0,
                 "apply_number_format": None, "apply_font": None, "apply_fill": None, "apply_border": None,
                 "apply_alignment": None, "apply_protection": None, "quote_prefix": None, "pivot_button": None,
                 "alignment": {"horizontal": "left", "vertical": "top", "text_rotation": 180,
                               "wrap_text": True, "shrink_to_fit": False, "indent": 250,
                               "relative_indent": -15, "justify_last_line": True, "reading_order": 2},
                 "protection": {"locked": True, "hidden": False}},
                {"num_fmt_id": 0, "font_id": 1, "fill_id": 0, "border_id": 0, "xf_id": 0,
                 "apply_number_format": None, "apply_font": None, "apply_fill": None, "apply_border": None,
                 "apply_alignment": None, "apply_protection": None, "quote_prefix": None, "pivot_button": None,
                 "alignment": None, "protection": None},
            ),
        },
        "worksheets": (
            {"worksheet_name": "Первый", "worksheet_part": {"value": "xl/worksheets/first.xml"}, "cells": (
                {"coordinate": "A6", "row": 6, "column": 1, "style_index": 0},
                {"coordinate": "B10", "row": 10, "column": 2, "style_index": 0},
                {"coordinate": "C104", "row": 104, "column": 3, "style_index": 1},
            )},
            {"worksheet_name": "Второй", "worksheet_part": {"value": "xl/worksheets/second.xml"}, "cells": ()},
        ),
    }

@pytest.mark.parametrize(("fragment", "expected"), [
    ('<fonts count="1"><font><sz val="0"/></font></fonts>', ("invalid-styles-content", "xl/styles.xml", "sz", "0")),
    ('<fonts count="1"><font><sz val="nan"/></font></fonts>', ("invalid-styles-content", "xl/styles.xml", "sz", "nan")),
    ('<fonts count="1"><font><condense val="maybe"/></font></fonts>', ("invalid-styles-content", "xl/styles.xml", "condense", "maybe")),
    ('<fills count="1"><fill><patternFill><fgColor tint="1.1"/></patternFill></fill></fills>', ("invalid-styles-content", "xl/styles.xml", "tint", "1.1")),
    ('<fills count="1"><fill><gradientFill><stop position="nan"><color rgb="FF000000"/></stop></gradientFill></fill></fills>', ("invalid-styles-content", "xl/styles.xml", "position", "nan")),
    ('<fills count="1"><fill><gradientFill><stop position="-0.1"><color rgb="FF000000"/></stop></gradientFill></fill></fills>', ("invalid-styles-content", "xl/styles.xml", "position", "-0.1")),
])
def test_scalar_semantic_failures(tmp_path, fragment, expected):
    assert error(package(tmp_path / "scalar.xlsx", style_xml=styles(fragment))) == expected

@pytest.mark.parametrize("rotation", ["-1", "181", "254"])
def test_text_rotation_rejects_outside_ooxml_domain(tmp_path, rotation):
    base = '<fonts count="1"><font/></fonts><fills count="1"><fill><patternFill/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    xml = styles(base + f'<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment textRotation="{rotation}"/></xf></cellXfs>')
    assert error(package(tmp_path / f"rotation-{rotation}.xlsx", style_xml=xml)) == ("invalid-styles-content", "xl/styles.xml", "textRotation", rotation)

def test_accepted_worksheet_member_alias_and_large_projection(tmp_path):
    rows = ''.join(f'<row r="{row}"><c r="A{row}" s="0"><v>{row}</v></c></row>' for row in range(1, 501))
    first = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + rows.encode() + b'</sheetData></worksheet>'
    result = read_workbook_style_semantics(package(tmp_path / "alias.xlsx", sheet_one=first, sheet_one_name="xl/worksheets/%66irst.xml"))
    assert len(result.worksheets[0].cells) == 500
    assert result.worksheets[0].cells[-1].coordinate == "A500"
