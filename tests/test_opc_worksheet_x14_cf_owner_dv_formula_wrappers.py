"""Exact X14 data-validation formula-wrapper ownership carve."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rns_import_server.opc_worksheet_x14_cf_owner_topology import (
    OPCWorksheetX14CfOwnerTopologyError,
    read_worksheet_x14_cf_owner_topology,
)
from tests.opc_worksheet_x14_cf_owner_fixture_factory import CF_URI, DV_URI, X14, XM, package, worksheet
from tests.real_rns_corpus import real_rns_corpus_path


PART = "xl/worksheets/first.xml"


def error(path: Path) -> tuple[str, str, str, str]:
    with pytest.raises(OPCWorksheetX14CfOwnerTopologyError) as captured:
        read_worksheet_x14_cf_owner_topology(path)
    return captured.value.as_tuple()


def dv(values: str, *, uri: str = DV_URI, attributes: str = "") -> str:
    return (f'<extLst><ext uri="{uri}"{attributes}><x14:dataValidations>'
            f'<x14:dataValidation>{values}</x14:dataValidation>'
            '</x14:dataValidations></ext></extLst>')


def cf() -> str:
    return (f'<extLst><ext uri="{CF_URI}"><x14:conditionalFormattings>'
            '<x14:conditionalFormatting/></x14:conditionalFormattings></ext></extLst>')


@pytest.mark.parametrize("values", (
    '<x14:formula1><xm:f>one</xm:f></x14:formula1>',
    '<x14:formula2><xm:f>two</xm:f></x14:formula2>',
    '<x14:formula1><xm:f>one</xm:f></x14:formula1><x14:formula2><xm:f>two</xm:f></x14:formula2>',
    '<xm:sqref>A1</xm:sqref><x14:formula1><xm:f>one</xm:f></x14:formula1><x14:formula2><xm:f>two</xm:f></x14:formula2>',
    '<x14:formula1/><x14:formula2/>',
))
def test_exact_dv_formula_wrappers_are_unowned_and_do_not_mask_adjacent_cf(tmp_path: Path, values: str) -> None:
    body = cf() + dv(values)
    result = read_worksheet_x14_cf_owner_topology(package(tmp_path / "valid.xlsx", sheet_one=worksheet(body)))
    assert len(result.worksheets[0].containers) == 1


@pytest.mark.parametrize(("values", "detail"), (
    ('<x14:Formula1><xm:f>bad</xm:f></x14:Formula1>', f"{{{XM}}}f"),
    ('<x14:Formula2><xm:f>bad</xm:f></x14:Formula2>', f"{{{XM}}}f"),
    ('<foreign><xm:f>bad</xm:f></foreign>', f"{{{XM}}}f"),
    ('<x:formula2 xmlns:x="urn:foreign"><xm:f>bad</xm:f></x:formula2>', f"{{{XM}}}f"),
    ('<formula1 xmlns=""><xm:f>bad</xm:f></formula1>', f"{{{XM}}}f"),
    ('<x14:formula1><foreign><xm:f>bad</xm:f></foreign></x14:formula1>', f"{{{XM}}}f"),
    ('<x14:formula1><xm:sqref>A1</xm:sqref></x14:formula1>', f"{{{XM}}}sqref"),
))
def test_nonexact_or_deeper_wrapper_never_inherits_dv_formula_ownership(tmp_path: Path, values: str, detail: str) -> None:
    assert error(package(tmp_path / "bad-wrapper.xlsx", sheet_one=worksheet(dv(values)))) == (
        "invalid-x14-cf-parent", PART, "tag", detail,
    )


@pytest.mark.parametrize(("body", "detail"), (
    ('<x14:formula1><xm:f>bad</xm:f></x14:formula1>', f"{{{XM}}}f"),
    ('<outer><x14:formula2><xm:f>bad</xm:f></x14:formula2></outer>', f"{{{XM}}}f"),
    ('<outer><x14:dataValidation><x14:formula1><xm:f>bad</xm:f></x14:formula1></x14:dataValidation></outer>', f"{{{XM}}}f"),
))
def test_wrapper_requires_the_exact_dv_depth(tmp_path: Path, body: str, detail: str) -> None:
    malformed = f'<extLst><ext uri="{DV_URI}"><x14:dataValidations>{body}</x14:dataValidations></ext></extLst>'
    assert error(package(tmp_path / "wrong-depth.xlsx", sheet_one=worksheet(malformed))) == (
        "invalid-x14-cf-parent", PART, "tag", detail,
    )


@pytest.mark.parametrize("uri", (DV_URI.upper(), DV_URI.swapcase(), "urn:wrong", ""))
def test_wrapper_requires_exact_extension_uri_and_no_extra_attributes(tmp_path: Path, uri: str) -> None:
    values = '<x14:formula1><xm:f>bad</xm:f></x14:formula1>'
    assert error(package(tmp_path / "wrong-uri.xlsx", sheet_one=worksheet(dv(values, uri=uri)))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{XM}}}f",
    )
    assert error(package(tmp_path / "extra-attribute.xlsx", sheet_one=worksheet(dv(values, attributes=' extra="x"')))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{XM}}}f",
    )


@pytest.mark.parametrize("position", ("before", "after"))
def test_formula_wrapper_does_not_change_cf_fault_tier_or_document_order(tmp_path: Path, position: str) -> None:
    formula = dv('<x14:formula1><xm:f>ok</xm:f></x14:formula1>')
    fault = '<x14:cfRule/>'
    body = fault + formula if position == "before" else formula + fault
    assert error(package(tmp_path / f"precedence-{position}.xlsx", sheet_one=worksheet(body))) == (
        "invalid-x14-cf-parent", PART, "tag", f"{{{X14}}}cfRule",
    )
    assert error(package(tmp_path / "atomic.xlsx", sheet_one=worksheet(cf() + formula), sheet_two=worksheet(fault))) == (
        "invalid-x14-cf-parent", "xl/worksheets/second.xml", "tag", f"{{{X14}}}cfRule",
    )


def test_real_read_only_corpus_accepts_x14_dv_formula_wrappers_without_mutation() -> None:
    corpus = real_rns_corpus_path()
    expected_hash = "2a1786d5836e4c3144107704f281bc9513fcd8de97937499268dc806c1106dd1"
    assert hashlib.sha256(corpus.read_bytes()).hexdigest() == expected_hash
    result = read_worksheet_x14_cf_owner_topology(corpus)
    assert sum(len(sheet.containers) for sheet in result.worksheets) > 0
    assert hashlib.sha256(corpus.read_bytes()).hexdigest() == expected_hash
