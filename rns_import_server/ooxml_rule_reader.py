"""Typed, read-only parser for native and x14 worksheet CF/DV rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from xml.etree import ElementTree as ET

NS = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "x14": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main",
    "xm": "http://schemas.microsoft.com/office/excel/2006/main",
}


@dataclass(frozen=True)
class UnsupportedFinding:
    part: str
    owner: str
    detail: str
    xml: str | None = None


class OOXMLRuleError(ValueError):
    def __init__(self, code: str, part: str, detail: str) -> None:
        self.code, self.part, self.detail = code, part, detail
        super().__init__(f"{code}: {part}: {detail}")


@dataclass(frozen=True)
class ConditionalFormattingRule:
    part: str
    source: str
    rule_order: int
    sqref: str
    source_sqref: str
    rule_type: str | None
    priority: int | None
    stop_if_true: bool | None
    operator: str | None
    dxf_id: int | None
    dxf_reference: str | None
    x14_id: str | None
    dxf_xml: str | None
    formulas: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]
    group_attributes: tuple[tuple[str, str], ...]
    group_xml: str
    rule_xml: str


@dataclass(frozen=True)
class DataValidationRule:
    part: str
    source: str
    rule_order: int
    sqref: str
    source_sqref: str
    validation_type: str | None
    operator: str | None
    allow_blank: bool | None
    show_error_message: bool | None
    show_input_message: bool | None
    formula1: str | None
    formula2: str | None
    attributes: tuple[tuple[str, str], ...]
    container_attributes: tuple[tuple[str, str], ...]
    container_xml: str
    sqref_attributes: tuple[tuple[str, str], ...]
    validation_xml: str


@dataclass(frozen=True)
class WorksheetRuleModel:
    part: str
    conditional_formats: tuple[ConditionalFormattingRule, ...]
    data_validations: tuple[DataValidationRule, ...]
    findings: tuple[UnsupportedFinding, ...]


@dataclass(frozen=True)
class OOXMLRuleModel:
    contract_version: str
    worksheets: tuple[WorksheetRuleModel, ...]
    findings: tuple[UnsupportedFinding, ...]


def _xml(raw: bytes, part: str) -> ET.Element:
    try:
        return ET.fromstring(raw)
    except ET.ParseError as error:
        raise OOXMLRuleError("malformed-worksheet-xml", part, str(error)) from error


def _attrs(node: ET.Element) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(node.attrib.items()))


def _canonical(node: ET.Element) -> str:
    return ET.tostring(node, encoding="unicode", short_empty_elements=True)


def _bool(value: str | None) -> bool | None:
    return None if value is None else value in {"1", "true", "True"}


def _integer(value: str | None, part: str, field: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise OOXMLRuleError("invalid-integer", part, field) from error


def _tokens(value: str | None, part: str, owner: str) -> tuple[str, ...]:
    tokens = tuple((value or "").split())
    if not tokens:
        raise OOXMLRuleError("missing-sqref", part, owner)
    return tokens


def _findings(part: str, owner: str, node: ET.Element, known_attributes: set[str], known_children: set[str]) -> tuple[UnsupportedFinding, ...]:
    findings = [UnsupportedFinding(part, owner, f"attribute:{key}={node.attrib[key]}", _canonical(node)) for key in sorted(node.attrib) if key not in known_attributes]
    findings.extend(UnsupportedFinding(part, owner, f"child:{child.tag}", _canonical(child)) for child in node if child.tag not in known_children)
    return tuple(findings)


def _native_cf(part: str, root: ET.Element) -> tuple[list[ConditionalFormattingRule], list[UnsupportedFinding]]:
    rules: list[ConditionalFormattingRule] = []
    findings: list[UnsupportedFinding] = []
    order = 0
    for group in root.findall("x:conditionalFormatting", NS):
        sqref = group.get("sqref")
        tokens = _tokens(sqref, part, "conditionalFormatting")
        findings.extend(_findings(part, "conditionalFormatting", group, {"sqref", "pivot"}, {f"{{{NS['x']}}}cfRule"}))
        for rule in group.findall("x:cfRule", NS):
            order += 1
            formulas = tuple("".join(node.itertext()) for node in rule.findall("x:formula", NS))
            known = {f"{{{NS['x']}}}formula", f"{{{NS['x']}}}colorScale", f"{{{NS['x']}}}dataBar", f"{{{NS['x']}}}iconSet"}
            findings.extend(_findings(part, "native-cf-rule", rule, {"type", "priority", "stopIfTrue", "operator", "dxfId", "aboveAverage", "equalAverage", "percent", "bottom", "rank", "stdDev", "text", "timePeriod"}, known))
            for token in tokens:
                rules.append(ConditionalFormattingRule(part, "native", order, token, sqref or "", rule.get("type"), _integer(rule.get("priority"), part, "cfRule.priority"), _bool(rule.get("stopIfTrue")), rule.get("operator"), _integer(rule.get("dxfId"), part, "cfRule.dxfId"), rule.get("dxfId"), None, None, formulas, _attrs(rule), _attrs(group), _canonical(group), _canonical(rule)))
    return rules, findings


def _x14_cf(part: str, root: ET.Element) -> tuple[list[ConditionalFormattingRule], list[UnsupportedFinding]]:
    rules: list[ConditionalFormattingRule] = []
    findings: list[UnsupportedFinding] = []
    order = 0
    for group in root.findall(".//x14:conditionalFormatting", NS):
        sqref_node = group.find("xm:sqref", NS)
        tokens = _tokens(None if sqref_node is None else "".join(sqref_node.itertext()), part, "x14:conditionalFormatting")
        findings.extend(_findings(part, "x14-conditionalFormatting", group, set(), {f"{{{NS['x14']}}}cfRule", f"{{{NS['xm']}}}sqref"}))
        for rule in group.findall("x14:cfRule", NS):
            order += 1
            formulas = tuple("".join(node.itertext()) for node in rule.findall("xm:f", NS))
            dxf = rule.find("x14:dxf", NS)
            findings.extend(_findings(part, "x14-cf-rule", rule, {"type", "priority", "stopIfTrue", "operator", "id", "aboveAverage", "equalAverage", "percent", "bottom", "rank", "stdDev", "text", "timePeriod", "activePresent"}, {f"{{{NS['xm']}}}f", f"{{{NS['x14']}}}dxf", f"{{{NS['x14']}}}colorScale", f"{{{NS['x14']}}}dataBar", f"{{{NS['x14']}}}iconSet"}))
            for token in tokens:
                rules.append(ConditionalFormattingRule(part, "x14", order, token, "".join(sqref_node.itertext()) if sqref_node is not None else "", rule.get("type"), _integer(rule.get("priority"), part, "x14.cfRule.priority"), _bool(rule.get("stopIfTrue")), rule.get("operator"), None, None, rule.get("id"), _canonical(dxf) if dxf is not None else None, formulas, _attrs(rule), _attrs(group), _canonical(group), _canonical(rule)))
    return rules, findings


def _native_dv(part: str, root: ET.Element) -> tuple[list[DataValidationRule], list[UnsupportedFinding]]:
    rules: list[DataValidationRule] = []
    findings: list[UnsupportedFinding] = []
    order = 0
    container = root.find("x:dataValidations", NS)
    for node in root.findall("x:dataValidations/x:dataValidation", NS):
        order += 1
        sqref = node.get("sqref")
        tokens = _tokens(sqref, part, "dataValidation")
        formula1 = node.find("x:formula1", NS)
        formula2 = node.find("x:formula2", NS)
        findings.extend(_findings(part, "native-dataValidation", node, {"type", "operator", "allowBlank", "showErrorMessage", "showInputMessage", "showDropDown", "error", "errorTitle", "prompt", "promptTitle", "imeMode", "sqref"}, {f"{{{NS['x']}}}formula1", f"{{{NS['x']}}}formula2"}))
        for token in tokens:
            rules.append(DataValidationRule(part, "native", order, token, sqref or "", node.get("type"), node.get("operator"), _bool(node.get("allowBlank")), _bool(node.get("showErrorMessage")), _bool(node.get("showInputMessage")), None if formula1 is None else "".join(formula1.itertext()), None if formula2 is None else "".join(formula2.itertext()), _attrs(node), _attrs(container) if container is not None else (), _canonical(container) if container is not None else "", (), _canonical(node)))
    return rules, findings


def _x14_dv(part: str, root: ET.Element) -> tuple[list[DataValidationRule], list[UnsupportedFinding]]:
    rules: list[DataValidationRule] = []
    findings: list[UnsupportedFinding] = []
    order = 0
    container = root.find(".//x14:dataValidations", NS)
    for node in root.findall(".//x14:dataValidation", NS):
        order += 1
        sqref_node = node.find("xm:sqref", NS)
        sqref = None if sqref_node is None else "".join(sqref_node.itertext())
        tokens = _tokens(sqref, part, "x14:dataValidation")
        formula1 = node.find("x14:formula1/xm:f", NS)
        formula2 = node.find("x14:formula2/xm:f", NS)
        findings.extend(_findings(part, "x14-dataValidation", node, {"type", "operator", "allowBlank", "showErrorMessage", "showInputMessage", "showDropDown", "error", "errorTitle", "prompt", "promptTitle", "imeMode", "uid"}, {f"{{{NS['xm']}}}sqref", f"{{{NS['x14']}}}formula1", f"{{{NS['x14']}}}formula2"}))
        for token in tokens:
            rules.append(DataValidationRule(part, "x14", order, token, sqref or "", node.get("type"), node.get("operator"), _bool(node.get("allowBlank")), _bool(node.get("showErrorMessage")), _bool(node.get("showInputMessage")), None if formula1 is None else "".join(formula1.itertext()), None if formula2 is None else "".join(formula2.itertext()), _attrs(node), _attrs(container) if container is not None else (), _canonical(container) if container is not None else "", _attrs(sqref_node) if sqref_node is not None else (), _canonical(node)))
    return rules, findings


def read_ooxml_rules(worksheet_parts: Mapping[str, bytes]) -> OOXMLRuleModel:
    """Read only caller-supplied worksheet parts; never infer part names."""
    if not isinstance(worksheet_parts, Mapping):
        raise TypeError("worksheet_parts must be a mapping")
    worksheets: list[WorksheetRuleModel] = []
    findings: list[UnsupportedFinding] = []
    for part, raw in worksheet_parts.items():
        if not isinstance(part, str) or not isinstance(raw, bytes):
            raise TypeError("worksheet_parts must map str to bytes")
        root = _xml(raw, part)
        native_cf, native_cf_findings = _native_cf(part, root)
        x14_cf, x14_cf_findings = _x14_cf(part, root)
        native_dv, native_dv_findings = _native_dv(part, root)
        x14_dv, x14_dv_findings = _x14_dv(part, root)
        sheet_findings = tuple(native_cf_findings + x14_cf_findings + native_dv_findings + x14_dv_findings)
        worksheets.append(WorksheetRuleModel(part, tuple(native_cf + x14_cf), tuple(native_dv + x14_dv), sheet_findings))
        findings.extend(sheet_findings)
    return OOXMLRuleModel("ooxml-rule-model-v1", tuple(worksheets), tuple(findings))


read_rules = read_ooxml_rules
