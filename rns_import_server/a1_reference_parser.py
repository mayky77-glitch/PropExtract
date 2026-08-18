"""Structural, fail-closed A1 formula lexer and insertion mapper.

The parser intentionally models only A1 cell/range/whole-row/whole-column
references. It never performs a textual substitution: unsupported Excel
reference dialects fail before a mapped formula is rendered.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


class UnsupportedReference(ValueError):
    """A reference form that cannot safely be mapped by this A1 contract."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CellReference:
    column: str
    row: int
    column_absolute: bool = False
    row_absolute: bool = False

    def render(self) -> str:
        return f"{'$' if self.column_absolute else ''}{self.column}{'$' if self.row_absolute else ''}{self.row}"


@dataclass(frozen=True)
class RowReference:
    row: int
    absolute: bool = False

    def render(self) -> str:
        return f"{'$' if self.absolute else ''}{self.row}"


@dataclass(frozen=True)
class ColumnReference:
    column: str
    absolute: bool = False

    def render(self) -> str:
        return f"{'$' if self.absolute else ''}{self.column}"


ReferenceEndpoint: TypeAlias = CellReference | RowReference | ColumnReference


@dataclass(frozen=True)
class A1Reference:
    sheet_raw: str | None
    sheet_name: str | None
    first: ReferenceEndpoint
    second: ReferenceEndpoint | None = None

    def render(self) -> str:
        prefix = f"{self.sheet_raw}!" if self.sheet_raw is not None else ""
        value = self.first.render()
        return prefix + (f"{value}:{self.second.render()}" if self.second is not None else value)


@dataclass(frozen=True)
class LiteralToken:
    text: str

    def render(self) -> str:
        return self.text


@dataclass(frozen=True)
class StringToken:
    text: str

    def render(self) -> str:
        return self.text


@dataclass(frozen=True)
class ReferenceToken:
    reference: A1Reference

    def render(self) -> str:
        return self.reference.render()


FormulaToken: TypeAlias = LiteralToken | StringToken | ReferenceToken


@dataclass(frozen=True)
class FormulaAst:
    tokens: tuple[FormulaToken, ...]

    def render(self) -> str:
        return "".join(token.render() for token in self.tokens)


MAX_COLUMN = 16_384  # XFD
MAX_ROW = 1_048_576


def _column_number(column: str) -> int:
    value = 0
    for char in column:
        value = value * 26 + ord(char.upper()) - ord("A") + 1
    return value


def _is_name_char(char: str) -> bool:
    return char.isalnum() or char in "_."


def _is_boundary(text: str, index: int) -> bool:
    return index >= len(text) or not (text[index].isalnum() or text[index] in "_.$")


def _is_function_identifier(text: str, index: int) -> bool:
    """Treat a reference-shaped identifier followed by ``(`` as a function."""
    if index >= len(text) or not (text[index].isalpha() or text[index] in "_\\"):
        return False
    position = index + 1
    while position < len(text) and _is_name_char(text[position]):
        position += 1
    return position < len(text) and text[position] == "("


def _consume_string(text: str, index: int) -> int:
    """Consume an Excel double-quoted string, including doubled quotes."""
    position = index + 1
    while position < len(text):
        if text[position] != '"':
            position += 1
            continue
        if position + 1 < len(text) and text[position + 1] == '"':
            position += 2
            continue
        return position + 1
    return len(text)


def _consume_quoted_sheet(text: str, index: int) -> tuple[str, str, int] | None:
    """Return raw, unescaped sheet name and end after the closing apostrophe."""
    if text[index] != "'":
        return None
    position = index + 1
    parts: list[str] = []
    while position < len(text):
        char = text[position]
        if char != "'":
            parts.append(char)
            position += 1
            continue
        if position + 1 < len(text) and text[position + 1] == "'":
            parts.append("'")
            position += 2
            continue
        end = position + 1
        return text[index:end], "".join(parts), end
    return None


def _consume_unquoted_sheet(text: str, index: int) -> tuple[str, int] | None:
    if index >= len(text) or not (text[index].isalpha() or text[index] in "_\\"):
        return None
    position = index + 1
    while position < len(text) and _is_name_char(text[position]):
        position += 1
    return text[index:position], position


def _consume_sheet_endpoint(text: str, index: int) -> int | None:
    """Consume either legal sheet-name spelling for 3D-span detection."""
    quoted = _consume_quoted_sheet(text, index) if index < len(text) and text[index] == "'" else None
    if quoted is not None:
        if "[" in quoted[0]:
            raise UnsupportedReference("external_or_structured_reference")
        return quoted[2]
    unquoted = _consume_unquoted_sheet(text, index)
    return unquoted[1] if unquoted is not None else None


def _parse_cell(text: str, index: int) -> tuple[CellReference, int] | None:
    position = index
    column_absolute = position < len(text) and text[position] == "$"
    if column_absolute:
        position += 1
    start = position
    while position < len(text) and text[position].isalpha():
        position += 1
    column = text[start:position]
    if not column or _column_number(column) > MAX_COLUMN:
        return None
    row_absolute = position < len(text) and text[position] == "$"
    if row_absolute:
        position += 1
    row_start = position
    while position < len(text) and text[position].isdigit():
        position += 1
    if row_start == position:
        return None
    row = int(text[row_start:position])
    if row < 1:
        return None
    if row > MAX_ROW:
        raise UnsupportedReference("a1_row_out_of_bounds")
    # Preserve source case for exact no-map roundtrips. Validation and sheet
    # matching are case-insensitive, but rendering must not normalize bytes.
    return CellReference(column, row, column_absolute, row_absolute), position


def _parse_column(text: str, index: int) -> tuple[ColumnReference, int] | None:
    position = index
    absolute = position < len(text) and text[position] == "$"
    if absolute:
        position += 1
    start = position
    while position < len(text) and text[position].isalpha():
        position += 1
    column = text[start:position]
    if not column or _column_number(column) > MAX_COLUMN:
        return None
    return ColumnReference(column, absolute), position


def _parse_row(text: str, index: int) -> tuple[RowReference, int] | None:
    position = index
    absolute = position < len(text) and text[position] == "$"
    if absolute:
        position += 1
    start = position
    while position < len(text) and text[position].isdigit():
        position += 1
    if start == position:
        return None
    row = int(text[start:position])
    if row < 1:
        return None
    return RowReference(row, absolute), position


def _parse_reference(text: str, index: int, *, sheet_raw: str | None = None, sheet_name: str | None = None) -> tuple[A1Reference, int] | None:
    """Parse one cell/range/whole-row/whole-column expression at ``index``."""
    cell = _parse_cell(text, index)
    if cell is not None:
        first, position = cell
        if position < len(text) and text[position] == ":":
            second = _parse_cell(text, position + 1)
            if second is None or not _is_boundary(text, second[1]):
                return None
            return A1Reference(sheet_raw, sheet_name, first, second[0]), second[1]
        if _is_boundary(text, position):
            return A1Reference(sheet_raw, sheet_name, first), position
        return None
    column = _parse_column(text, index)
    if column is not None and column[1] < len(text) and text[column[1]] == ":":
        second = _parse_column(text, column[1] + 1)
        if second is not None and _is_boundary(text, second[1]):
            return A1Reference(sheet_raw, sheet_name, column[0], second[0]), second[1]
    row = _parse_row(text, index)
    if row is not None and row[1] < len(text) and text[row[1]] == ":":
        second = _parse_row(text, row[1] + 1)
        if second is not None and _is_boundary(text, second[1]):
            if row[0].row > MAX_ROW or second[0].row > MAX_ROW:
                raise UnsupportedReference("a1_row_out_of_bounds")
            return A1Reference(sheet_raw, sheet_name, row[0], second[0]), second[1]
    return None


def _qualified_reference(text: str, index: int) -> tuple[A1Reference, int] | None:
    quoted = _consume_quoted_sheet(text, index) if text[index] == "'" else None
    if quoted is not None:
        raw, name, position = quoted
        if "[" in raw:
            raise UnsupportedReference("external_or_structured_reference")
        # A single quoted token may encode a 3D span (``'First:Last'``).
        # Reject decoded punctuation before constructing an A1Reference: its
        # raw spelling would otherwise be rendered as a trusted sheet prefix.
        if ":" in name:
            raise UnsupportedReference("three_dimensional_reference")
        if position < len(text) and text[position] == ":":
            other_end = _consume_sheet_endpoint(text, position + 1)
            if other_end is not None and other_end < len(text) and text[other_end] == "!":
                raise UnsupportedReference("three_dimensional_reference")
        if position < len(text) and text[position] == "!":
            return _parse_reference(text, position + 1, sheet_raw=raw, sheet_name=name)
        return None
    unquoted = _consume_unquoted_sheet(text, index)
    if unquoted is None:
        return None
    name, position = unquoted
    if position < len(text) and text[position] == ":":
        other_end = _consume_sheet_endpoint(text, position + 1)
        if other_end is not None and other_end < len(text) and text[other_end] == "!":
            raise UnsupportedReference("three_dimensional_reference")
    if position < len(text) and text[position] == "!":
        return _parse_reference(text, position + 1, sheet_raw=name, sheet_name=name)
    return None


def parse_formula(formula: str) -> FormulaAst:
    """Lex ``formula`` into immutable literal/string/reference tokens."""
    if not isinstance(formula, str):
        raise TypeError("formula must be str")
    tokens: list[FormulaToken] = []
    literal_start = 0
    position = 0
    while position < len(formula):
        char = formula[position]
        if char == '"':
            if literal_start < position:
                tokens.append(LiteralToken(formula[literal_start:position]))
            end = _consume_string(formula, position)
            tokens.append(StringToken(formula[position:end]))
            position = literal_start = end
            continue
        # ``[book]Sheet!A1`` and ``Table[Column]`` are deliberately refused;
        # no token rendering has occurred yet, so mapping is all-or-nothing.
        if char == "[":
            raise UnsupportedReference("external_or_structured_reference")
        # A1 grammar cannot begin midway through a defined name. This avoids
        # treating the tail of ``NameA1`` as the unrelated cell ``EA1``.
        can_start = position == 0 or not _is_name_char(formula[position - 1])
        if can_start and _is_function_identifier(formula, position):
            position += 1
            continue
        qualified = _qualified_reference(formula, position) if can_start and (char == "'" or char.isalpha() or char in "_\\") else None
        if qualified is not None:
            if literal_start < position:
                tokens.append(LiteralToken(formula[literal_start:position]))
            reference, end = qualified
            tokens.append(ReferenceToken(reference))
            position = literal_start = end
            continue
        reference = _parse_reference(formula, position) if can_start else None
        if reference is not None:
            if literal_start < position:
                tokens.append(LiteralToken(formula[literal_start:position]))
            parsed, end = reference
            tokens.append(ReferenceToken(parsed))
            position = literal_start = end
            continue
        position += 1
    if literal_start < len(formula):
        tokens.append(LiteralToken(formula[literal_start:]))
    return FormulaAst(tuple(tokens))


def _shift_endpoint(endpoint: ReferenceEndpoint, insertion_row: int) -> ReferenceEndpoint:
    if isinstance(endpoint, ColumnReference) or endpoint.row < insertion_row:
        return endpoint
    if endpoint.row >= MAX_ROW:
        raise UnsupportedReference("a1_row_insertion_overflow")
    if isinstance(endpoint, CellReference):
        return CellReference(endpoint.column, endpoint.row + 1, endpoint.column_absolute, endpoint.row_absolute)
    return RowReference(endpoint.row + 1, endpoint.absolute)


def _maps_on_sheet(reference: A1Reference, *, host_sheet: str, target_sheet: str) -> bool:
    candidate = host_sheet if reference.sheet_name is None else reference.sheet_name
    return candidate.casefold() == target_sheet.casefold()


def map_formula(formula: str, *, host_sheet: str, target_sheet: str, insertion_row: int) -> str:
    """Map A1 references across one row insertion, preserving all other text."""
    if not isinstance(host_sheet, str) or not host_sheet or not isinstance(target_sheet, str) or not target_sheet:
        raise ValueError("host_sheet and target_sheet must be non-empty strings")
    if not isinstance(insertion_row, int) or isinstance(insertion_row, bool) or not 1 <= insertion_row <= MAX_ROW:
        raise UnsupportedReference("a1_row_insertion_overflow")
    ast = parse_formula(formula)
    mapped: list[FormulaToken] = []
    for token in ast.tokens:
        if not isinstance(token, ReferenceToken) or not _maps_on_sheet(token.reference, host_sheet=host_sheet, target_sheet=target_sheet):
            mapped.append(token)
            continue
        reference = token.reference
        mapped.append(ReferenceToken(A1Reference(
            reference.sheet_raw,
            reference.sheet_name,
            _shift_endpoint(reference.first, insertion_row),
            _shift_endpoint(reference.second, insertion_row) if reference.second is not None else None,
        )))
    return FormulaAst(tuple(mapped)).render()


# Deliberate aliases for integration callers that name the operation by its
# input rather than by the parser implementation.
parse_a1_formula = parse_formula
map_a1_references = map_formula
