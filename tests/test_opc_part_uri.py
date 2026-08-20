import pytest

from rns_import_server.opc_part_uri import (
    CanonicalPartURI,
    OPCPartURIError,
    RawPartURI,
    normalized_part_collisions,
    parse_relative_part_uri,
    require_unique_part_uris,
    canonicalize_part_uri,
    resolve_relative_part_uri,
)


def error_tuple(callable_, *args):
    with pytest.raises(OPCPartURIError) as caught:
        callable_(*args)
    return caught.value.as_tuple()


def test_canonical_part_returns_typed_nfc_form_and_preserves_case():
    result = canonicalize_part_uri(RawPartURI("xl/Worksheets/é.xml"))
    assert result == CanonicalPartURI("xl/Worksheets/é.xml")
    assert canonicalize_part_uri("xl/Sheet.xml") != canonicalize_part_uri("xl/sheet.xml")


def test_unreserved_percent_aliases_normalize_before_lookup_and_collide():
    assert canonicalize_part_uri("xl/%77orkbook.xml") == CanonicalPartURI("xl/workbook.xml")
    collisions = normalized_part_collisions(["xl/workbook.xml", "xl/%77orkbook.xml"])
    assert [item.as_tuple() for item in collisions] == [
        ("duplicate-normalized-part", "xl/workbook.xml", "xl/workbook.xml", "xl/%77orkbook.xml")
    ]
    assert error_tuple(require_unique_part_uris, ["xl/workbook.xml", "xl/%77orkbook.xml"]) == (
        "duplicate-normalized-part", "xl/workbook.xml", "xl/workbook.xml"
    )


def test_exact_duplicate_part_names_are_collisions():
    values = ["xl/workbook.xml", "xl/workbook.xml"]
    collisions = normalized_part_collisions(values)
    assert [item.as_tuple() for item in collisions] == [
        ("duplicate-normalized-part", "xl/workbook.xml", "xl/workbook.xml", "xl/workbook.xml")
    ]
    assert error_tuple(require_unique_part_uris, values) == (
        "duplicate-normalized-part", "xl/workbook.xml", "xl/workbook.xml"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("xl/%2fworkbook.xml", ("encoded-separator", "xl/%2fworkbook.xml", "xl/%2fworkbook.xml")),
        ("xl/%5Cworkbook.xml", ("encoded-separator", "xl/%5Cworkbook.xml", "xl/%5Cworkbook.xml")),
        ("xl/%2e%2e/workbook.xml", ("encoded-traversal", "xl/%2e%2e/workbook.xml", "xl/../workbook.xml")),
        ("xl/../workbook.xml", ("invalid-part-segment", "xl/../workbook.xml", "xl/../workbook.xml")),
        ("/xl/workbook.xml", ("invalid-slash", "/xl/workbook.xml", "/xl/workbook.xml")),
        ("xl//workbook.xml", ("invalid-slash", "xl//workbook.xml", "xl//workbook.xml")),
        ("xl\\workbook.xml", ("invalid-backslash", "xl\\workbook.xml", "xl\\workbook.xml")),
        ("xl/%", ("invalid-percent-escape", "xl/%", "xl/%")),
        ("xl/%C2%80.xml", ("invalid-control", "xl/%C2%80.xml", "xl/%C2%80.xml")),
        ("xl/\x7f.xml", ("invalid-control", "xl/\x7f.xml", "xl/\x7f.xml")),
        ("xl/e\u0301.xml", ("ambiguous-unicode", "xl/e\u0301.xml", "xl/e\u0301.xml")),
    ],
)
def test_part_rejections_have_exact_tuples(value, expected):
    assert error_tuple(canonicalize_part_uri, value) == expected


def test_percent_encoded_utf8_continuation_bytes_are_validated_after_decoding():
    assert canonicalize_part_uri("xl/%C3%A9.xml") == CanonicalPartURI("xl/%C3%A9.xml")
    assert canonicalize_part_uri("xl/%E2%80%93.xml") == CanonicalPartURI("xl/%E2%80%93.xml")
    assert error_tuple(canonicalize_part_uri, "xl/%C2%80.xml") == (
        "invalid-control", "xl/%C2%80.xml", "xl/%C2%80.xml"
    )


def test_relative_resolution_is_source_relative_idempotent_and_rejects_root_escape():
    source = CanonicalPartURI("xl/worksheets/sheet1.xml")
    result = resolve_relative_part_uri(source, "../workbook.xml")
    assert result == CanonicalPartURI("xl/workbook.xml")
    assert resolve_relative_part_uri(None, "xl/workbook.xml") == result
    assert parse_relative_part_uri("../workbook.xml").value == "../workbook.xml"
    assert error_tuple(resolve_relative_part_uri, CanonicalPartURI("root.xml"), "../escape.xml") == (
        "package-root-escape", "../escape.xml", "../escape.xml"
    )


def test_relative_resolution_keeps_raw_dot_segments_and_percent_escapes_distinct():
    source = CanonicalPartURI("xl/worksheets/sheet1.xml")
    assert resolve_relative_part_uri(source, "../shared%20strings.xml") == CanonicalPartURI(
        "xl/shared%20strings.xml"
    )


@pytest.mark.parametrize("target", [".", "..", "a/.", "a/.."])
def test_relative_resolution_rejects_terminal_directory_targets(target):
    assert error_tuple(resolve_relative_part_uri, CanonicalPartURI("xl/worksheets/sheet1.xml"), target) == (
        "invalid-part-uri", target, target
    )


@pytest.mark.parametrize("target", ["..", "../.."])
def test_relative_resolution_reports_root_escape_before_terminal_directory_error(target):
    assert error_tuple(resolve_relative_part_uri, CanonicalPartURI("root.xml"), target) == (
        "package-root-escape", target, target
    )


def test_relative_target_rejects_absolute_query_fragment_and_encoded_traversal():
    assert error_tuple(parse_relative_part_uri, "/xl/workbook.xml") == (
        "invalid-slash", "/xl/workbook.xml", "/xl/workbook.xml"
    )
    assert error_tuple(parse_relative_part_uri, "xl/workbook.xml?x") == (
        "invalid-target-character", "xl/workbook.xml?x", "xl/workbook.xml?x"
    )
    assert error_tuple(parse_relative_part_uri, "%2e%2e/workbook.xml") == (
        "encoded-traversal", "%2e%2e/workbook.xml", "../workbook.xml"
    )
