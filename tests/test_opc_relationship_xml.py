from __future__ import annotations

import pytest

from rns_import_server.opc_relationship_xml import (
    OPCRelationshipXMLError,
    RELATIONSHIPS_NAMESPACE,
    Relationship,
    parse_relationship_xml,
)


PART = "xl/_rels/workbook.xml.rels"


def _document(body: str, *, root_attributes: str = "") -> str:
    return f'<Relationships xmlns="{RELATIONSHIPS_NAMESPACE}"{root_attributes}>{body}</Relationships>'


def _relationship(**attributes: str) -> str:
    values = {
        "Id": "rId1",
        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
        "Target": "worksheets/sheet1.xml",
        **attributes,
    }
    return "<Relationship " + " ".join(f'{name}="{value}"' for name, value in values.items()) + "/>"


def _error_tuple(payload: bytes | str) -> tuple[str, str, str]:
    with pytest.raises(OPCRelationshipXMLError) as caught:
        parse_relationship_xml(PART, payload)
    return caught.value.as_tuple()


def test_parses_immutable_records_in_document_order_with_internal_default():
    xml = _document(_relationship(Id="rId2", Target="two.xml") + _relationship(Id="rId1", Target="https://example.test/one.xml#sheet", TargetMode="External"))
    assert parse_relationship_xml(PART, xml) == (
        Relationship("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "two.xml", "Internal"),
        Relationship("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "https://example.test/one.xml#sheet", "External"),
    )


@pytest.mark.parametrize("identifier", ["éлемент", "名_2", "𐐀-name", "a\u0301"])
def test_accepts_xml_10_unicode_ncname_ids(identifier: str):
    records = parse_relationship_xml(PART, _document(_relationship(Id=identifier)))
    assert records[0].id == identifier


@pytest.mark.parametrize("identifier", ["1id", "-id", ".id", "r:id", "id space", "\u00b7id"])
def test_rejects_invalid_ncname_ids(identifier: str):
    assert _error_tuple(_document(_relationship(Id=identifier))) == ("invalid-relationship-id", PART, identifier)


def test_rejects_duplicate_ids_before_returning_partial_result():
    assert _error_tuple(_document(_relationship(Id="rId") + _relationship(Id="rId"))) == (
        "duplicate-relationship-id", PART, "rId"
    )


@pytest.mark.parametrize(
    "type_uri",
    [
        "relative/type",
        "http://example.test/type#fragment",
        "http://example.test/bad space",
        "http://example.test/%zz",
        "http://example.test/\\bad",
        "https://пример.рф/type",
    ],
)
def test_type_must_be_absolute_uri_without_fragment(type_uri: str):
    assert _error_tuple(_document(_relationship(Type=type_uri))) == ("invalid-relationship-type", PART, type_uri)


@pytest.mark.parametrize("type_uri", ["urn:example:kind", "https://example.test/a%20b?version=1", "tag:example.test,2026:type"])
def test_type_uri_valid_edges(type_uri: str):
    assert parse_relationship_xml(PART, _document(_relationship(Type=type_uri)))[0].type_uri == type_uri


def test_accepts_nfc_unicode_only_in_uri_path_query_and_fragment_components():
    internal = "worksheets/лист.xml"
    external = "../лист.xml?ключ=значение#фрагмент"
    type_uri = "https://example.test/лист.xml?ключ=значение"
    assert parse_relationship_xml(PART, _document(_relationship(Target=internal)))[0].target == internal
    assert parse_relationship_xml(PART, _document(_relationship(Target=external, TargetMode="External")))[0].target == external
    assert parse_relationship_xml(PART, _document(_relationship(Type=type_uri)))[0].type_uri == type_uri


@pytest.mark.parametrize(
    ("attribute", "value", "code"),
    [
        ("Target", "worksheets/cafe\u0301.xml", "invalid-relationship-target"),
        ("Target", "worksheets/лист\u200b.xml", "invalid-relationship-target"),
        ("Target", "worksheets/лист\u202e.xml", "invalid-relationship-target"),
        ("Target", "worksheets/лист\\.xml", "invalid-relationship-target"),
        ("Type", "https://пример.рф/лист.xml", "invalid-relationship-type"),
        ("Type", "https://пользователь@example.test/лист.xml", "invalid-relationship-type"),
    ],
)
def test_rejects_noncanonical_or_nonascii_authority_unicode(attribute: str, value: str, code: str):
    assert _error_tuple(_document(_relationship(**{attribute: value}))) == (code, PART, value)


@pytest.mark.parametrize(
    ("target", "expected_code"),
    [
        ("worksheets/\x01.xml", "malformed-xml"),
        ("worksheets/\x7f.xml", "invalid-relationship-target"),
        ("worksheets/\x80.xml", "invalid-relationship-target"),
        ("worksheets/\ud800.xml", "malformed-xml"),
    ],
)
def test_rejects_controls_and_surrogates(target: str, expected_code: str):
    assert _error_tuple(_document(_relationship(Target=target)))[0] == expected_code


@pytest.mark.parametrize(
    "type_uri",
    [
        "http://[not-ipv6]/type",
        "http://[2001:db8::1/type",
        "http://example.test:port/type",
        "http://user@@example.test/type",
        "http://example.test]/type",
        "http://exa[mple.test/type",
    ],
)
def test_type_uri_rejects_invalid_rfc3986_authority_grammar(type_uri: str):
    assert _error_tuple(_document(_relationship(Type=type_uri))) == ("invalid-relationship-type", PART, type_uri)


@pytest.mark.parametrize("mode", ["internal", "external", "", "Remote"])
def test_target_mode_is_exact(mode: str):
    assert _error_tuple(_document(_relationship(TargetMode=mode))) == ("invalid-target-mode", PART, mode)


@pytest.mark.parametrize("target", ["", "bad space", "../%zz", "http://[bad"])
def test_target_must_be_nonblank_valid_uri_reference(target: str):
    assert _error_tuple(_document(_relationship(Target=target))) == ("invalid-relationship-target", PART, target)


def test_target_mode_uri_semantics_are_exact_and_mode_aware():
    assert _error_tuple(_document(_relationship(Target="https://example.test/workbook.xml"))) == (
        "internal-target-not-relative", PART, "https://example.test/workbook.xml"
    )
    assert parse_relationship_xml(PART, _document(_relationship(Target="/workbook.xml", TargetMode="Internal")))[0].target == "/workbook.xml"
    for target in ("../x", "/x", "//host/x", "urn:example:workbook#sheet"):
        assert parse_relationship_xml(PART, _document(_relationship(Target=target, TargetMode="External")))[0].target == target


def test_openpyxl_raw_space_hyperlinks_are_narrowly_accepted_and_preserved():
    hyperlink = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    file_target = "file:///run/user/1000/РнС и ГРО/реестр.xlsx"
    relative_target = "../РнС и ГРО/реестр.xlsx"
    for target in (file_target, relative_target):
        relationship = parse_relationship_xml(
            PART,
            _document(_relationship(Type=hyperlink, Target=target, TargetMode="External")),
        )[0]
        assert relationship.target == target
        assert relationship.target_mode == "External"

    escaped = "file:///run/user/1000/РнС%20и%20ГРО/реестр.xlsx"
    assert parse_relationship_xml(PART, _document(_relationship(Target=escaped, TargetMode="External")))[0].target == escaped


@pytest.mark.parametrize("literal", ("\t", "\n", "\r"))
@pytest.mark.parametrize("encoding", (None, "utf-8", "utf-16"))
def test_rejects_literal_xml_attribute_whitespace_before_elementtree_normalizes_it(literal: str, encoding: str | None):
    target = f"file:///run/user/1000/РнС{literal}и ГРО/реестр.xlsx"
    payload: bytes | str = _document(_relationship(
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        Target=target,
        TargetMode="External",
    ))
    if encoding is not None:
        payload = payload.encode(encoding)
    assert _error_tuple(payload) == ("invalid-relationship-target", PART, target)


@pytest.mark.parametrize("encoding", ("utf-16-le", "utf-16-be"))
def test_bomless_utf16_declared_document_preserves_literal_target_control_rejection(encoding: str):
    target = "file:///run/user/1000/РнС\tи ГРО/реестр.xlsx"
    payload = (
        '<?xml version="1.0" encoding="utf-16"?>'
        + _document(_relationship(
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            Target=target,
            TargetMode="External",
        ))
    ).encode(encoding)
    assert _error_tuple(payload) == ("invalid-relationship-target", PART, target)


@pytest.mark.parametrize("encoding", ("utf-16-le", "utf-16-be"))
def test_bomless_utf16_without_declaration_preserves_literal_target_control_rejection(encoding: str):
    target = "file:///run/user/1000/РнС\tи ГРО/реестр.xlsx"
    payload = _document(_relationship(
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        Target=target,
        TargetMode="External",
    )).encode(encoding)
    assert _error_tuple(payload) == ("invalid-relationship-target", PART, target)


@pytest.mark.parametrize("encoding", ("utf-16-le", "utf-16-be"))
def test_bomless_utf16_declared_document_without_literal_control_stays_accepted(encoding: str):
    payload = (
        '<?xml version="1.0" encoding="utf-16"?>'
        + _document(_relationship(Target="worksheets/sheet1.xml"))
    ).encode(encoding)
    assert parse_relationship_xml(PART, payload)[0].target == "worksheets/sheet1.xml"


def test_elementtree_parse_root_and_child_errors_precede_literal_target_control_check():
    duplicate_target = _document(
        '<Relationship Id="rId" Type="urn:x" Target="one.xml" Target="file:///a\tb"/>'
    )
    assert _error_tuple(duplicate_target) == ("malformed-xml", PART, "document")

    wrong_root = '<Other><Relationship Id="rId" Type="urn:x" Target="file:///a\tb"/></Other>'
    assert _error_tuple(wrong_root) == ("invalid-relationships-root", PART, "Other")

    wrong_namespace_child = _document(
        '<Relationship xmlns="urn:wrong" Id="rId" Type="urn:x" Target="file:///a\tb"/>'
    )
    assert _error_tuple(wrong_namespace_child) == ("invalid-relationships-child", PART, "{urn:wrong}Relationship")


@pytest.mark.parametrize(
    ("character_reference", "normalized_character"),
    (("&#9;", "\t"), ("&#10;", "\n"), ("&#13;", "\r"), ("&#x9;", "\t"), ("&#xA;", "\n"), ("&#xD;", "\r")),
)
def test_character_reference_whitespace_keeps_elementtree_validation_path(character_reference: str, normalized_character: str):
    lexical_target = f"file:///run/user/1000/РнС{character_reference}и ГРО/реестр.xlsx"
    normalized_target = f"file:///run/user/1000/РнС{normalized_character}и ГРО/реестр.xlsx"
    assert _error_tuple(_document(_relationship(
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        Target=lexical_target,
        TargetMode="External",
    ))) == ("invalid-relationship-target", PART, normalized_target)


@pytest.mark.parametrize(
    ("attributes", "target"),
    [
        ({"TargetMode": "External"}, "file:///a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"}, "file:///a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "Internal"}, "a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "https://example.test/a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "urn:example:a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file://host/a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///a b?query"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///a b#fragment"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, " file:///a b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///a b "),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///a b\\c"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///a b\x7f"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///cafe\u0301 b"),
        ({"Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "TargetMode": "External"}, "file:///a b%zz"),
    ],
)
def test_openpyxl_raw_space_compatibility_rejects_every_broader_form(attributes: dict[str, str], target: str):
    assert _error_tuple(_document(_relationship(Target=target, **attributes))) == (
        "invalid-relationship-target",
        PART,
        target,
    )


@pytest.mark.parametrize(
    ("type_uri", "valid"),
    [
        ("http://999.999.999.999/type", True),
        ("http://[V1.a]/type", True),
        ("http://[fe80::1%25eth0]/type", False),
        ("http://[v1.]/type", False),
    ],
)
def test_type_uri_host_reviewer_boundaries(type_uri: str, valid: bool):
    if valid:
        assert parse_relationship_xml(PART, _document(_relationship(Type=type_uri)))[0].type_uri == type_uri
    else:
        assert _error_tuple(_document(_relationship(Type=type_uri))) == ("invalid-relationship-type", PART, type_uri)


@pytest.mark.parametrize(
    ("attribute", "value", "mode", "code"),
    [
        ("Type", "https://example.test:\u0661/лист.xml", None, "invalid-relationship-type"),
        ("Target", "https://example.test:\uff11/лист.xml", "External", "invalid-relationship-target"),
    ],
)
def test_rejects_unicode_authority_ports(attribute: str, value: str, mode: str | None, code: str):
    attributes = {attribute: value}
    if mode is not None:
        attributes["TargetMode"] = mode
    assert _error_tuple(_document(_relationship(**attributes))) == (code, PART, value)


@pytest.mark.parametrize("name", ["Id", "Type", "Target"])
def test_required_relationship_attributes_are_enforced(name: str):
    attributes = {"Id": "rId", "Type": "urn:example:type", "Target": "one.xml"}
    del attributes[name]
    xml = "<Relationship " + " ".join(f'{key}="{value}"' for key, value in attributes.items()) + "/>"
    assert _error_tuple(_document(xml)) == ("missing-relationship-attribute", PART, name)


def test_rejects_unknown_attributes_root_attributes_children_and_wrong_namespace():
    assert _error_tuple(_document(_relationship(foo="bar"))) == ("unknown-relationship-attribute", PART, "foo")
    assert _error_tuple(_document(_relationship(), root_attributes=' extra="x"')) == ("unknown-root-attribute", PART, "extra")
    assert _error_tuple(_document("<Unexpected/>")) == (
        "invalid-relationships-child", PART, f"{{{RELATIONSHIPS_NAMESPACE}}}Unexpected"
    )
    assert _error_tuple("<Relationships><Relationship Id=\"rId\" Type=\"urn:x\" Target=\"one.xml\"/></Relationships>") == (
        "invalid-relationships-root", PART, "Relationships"
    )


def test_rejects_non_whitespace_element_content_and_nested_children():
    assert _error_tuple(_document("unexpected" + _relationship())) == (
        "invalid-relationships-content", PART, "text"
    )
    assert _error_tuple(_document('<Relationship Id="rId" Type="urn:x" Target="one.xml">text</Relationship>')) == (
        "invalid-relationship-content", PART, "rId"
    )
    assert _error_tuple(_document('<Relationship Id="rId" Type="urn:x" Target="one.xml"><owned/></Relationship>')) == (
        "invalid-relationship-content", PART, "rId"
    )


def test_malformed_xml_has_stable_error_tuple():
    assert _error_tuple(b"<Relationships") == ("malformed-xml", PART, "document")


@pytest.mark.parametrize(
    "payload",
    [
        '<!DOCTYPE Relationships><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        '<!DOCTYPE Relationships [<!ENTITY owned "x">]><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">&owned;</Relationships>',
    ],
)
def test_rejects_plain_and_entity_doctypes_before_parsing(payload: str):
    assert _error_tuple(payload) == ("forbidden-doctype", PART, "doctype")


def test_rejects_non_whitespace_child_tail():
    assert _error_tuple(_document(_relationship() + "tail")) == ("invalid-relationships-content", PART, "tail")


@pytest.mark.parametrize(
    "payload",
    [
        '<!-- <!DOCTYPE Relationships> --><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        '<?note <!DOCTYPE Relationships>?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    ],
)
def test_comment_and_processing_instruction_doctype_text_is_not_a_doctype(payload: str):
    assert parse_relationship_xml(PART, payload) == ()
