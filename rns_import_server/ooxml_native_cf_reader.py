"""Strict native (2006) SpreadsheetML conditional-formatting reader."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import TypeAlias
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XR_NS = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
MAX_ROW, MAX_COLUMN = 1_048_576, 16_384
INT32_MIN, INT32_MAX, UINT32_MAX = -2_147_483_648, 2_147_483_647, 4_294_967_295
_GUID = re.compile(r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$")
_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)$")
_RANGE = re.compile(r"^(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*)(?::(\$?[A-Za-z]{1,3}\$?[1-9][0-9]*))?$")


class NativeCfParseError(ValueError):
    def __init__(self, code: str, owner_path: str, detail: str = "") -> None:
        self.code, self.owner_path, self.detail = code, owner_path, detail
        super().__init__(f"{code} at {owner_path}" + (f": {detail}" if detail else ""))


@dataclass(frozen=True, slots=True)
class NativeCfFinding: code: str; owner_path: str; detail: str
@dataclass(frozen=True, slots=True)
class NativeCfExtension: owner_path: str; uri: str; xml: str
@dataclass(frozen=True, slots=True)
class NativeCfExtensionList: owner_path: str; extensions: tuple[NativeCfExtension, ...]
@dataclass(frozen=True, slots=True)
class NativeCfvo:
    owner_path: str; type: str; value: str | None; greater_than_or_equal: bool | None
    extension_list: NativeCfExtensionList | None
@dataclass(frozen=True, slots=True)
class NativeColor:
    owner_path: str; rgb: str | None; indexed: int | None; theme: int | None
    auto: bool | None; tint: float | None
@dataclass(frozen=True, slots=True)
class NativeColorScale:
    owner_path: str; thresholds: tuple[NativeCfvo, ...]; colors: tuple[NativeColor, ...]
@dataclass(frozen=True, slots=True)
class NativeDataBar:
    owner_path: str; thresholds: tuple[NativeCfvo, ...]; color: NativeColor
    min_length: int | None; max_length: int | None; show_value: bool | None
@dataclass(frozen=True, slots=True)
class NativeIconSet:
    owner_path: str; thresholds: tuple[NativeCfvo, ...]; icon_set: str | None
    show_value: bool | None; percent: bool | None; reverse: bool | None
NativeCfPayload: TypeAlias = NativeColorScale | NativeDataBar | NativeIconSet | None
@dataclass(frozen=True, slots=True)
class NativeCfRule:
    owner_path: str; type: str; priority: int; dxf_id: int | None; stop_if_true: bool | None
    above_average: bool | None; percent: bool | None; bottom: bool | None; operator: str | None
    text: str | None; time_period: str | None; rank: int | None; standard_deviation: int | None
    equal_average: bool | None; formulas: tuple[str, ...]; payload: NativeCfPayload
    extension_list: NativeCfExtensionList | None
@dataclass(frozen=True, slots=True)
class NativeConditionalFormatting:
    owner_path: str; sqref: tuple[str, ...]; pivot: bool | None; uid: str | None
    rules: tuple[NativeCfRule, ...]; extension_list: NativeCfExtensionList | None
@dataclass(frozen=True, slots=True)
class NativeCfReadResult:
    worksheet_part: str; containers: tuple[NativeConditionalFormatting, ...]
    findings: tuple[NativeCfFinding, ...] = ()
    @property
    def conditional_formattings(self) -> tuple[NativeConditionalFormatting, ...]: return self.containers


_TYPES = frozenset(("expression","cellIs","colorScale","dataBar","iconSet","top10","uniqueValues","duplicateValues","containsText","notContainsText","beginsWith","endsWith","containsBlanks","notContainsBlanks","containsErrors","notContainsErrors","timePeriod","aboveAverage"))
_RULE_ATTRS = frozenset(("type","dxfId","priority","stopIfTrue","aboveAverage","percent","bottom","operator","text","timePeriod","rank","stdDev","equalAverage"))
_OPERATORS = frozenset(("between","notBetween","equal","notEqual","greaterThan","lessThan","greaterThanOrEqual","lessThanOrEqual","containsText","notContains","beginsWith","endsWith"))
_TIMES = frozenset(("today","yesterday","tomorrow","last7Days","lastMonth","nextMonth","thisWeek","lastWeek","nextWeek","thisMonth"))
_CFVO = frozenset(("min","max","num","percent","percentile","formula"))
_ICONS = frozenset(("3Arrows","3ArrowsGray","3Flags","3TrafficLights1","3TrafficLights2","3Signs","3Symbols","3Symbols2","4Arrows","4ArrowsGray","4RedToBlack","4Rating","4TrafficLights","5Arrows","5ArrowsGray","5Quarters","5Rating"))
_TEXT_TYPES = frozenset(("containsText","notContainsText","beginsWith","endsWith"))
_FORMULA_TYPES = frozenset(("expression","cellIs","containsText","notContainsText","beginsWith","endsWith","containsBlanks","notContainsBlanks","containsErrors","notContainsErrors","timePeriod"))

def _q(n: str) -> str: return f"{{{MAIN_NS}}}{n}"
def _main(e: ET.Element, n: str) -> bool: return e.tag == _q(n)
def _path(part: str, suffix: str) -> str: return f"{part}#worksheet/{suffix}"
def _fail(code: str, path: str, detail: str = "") -> None: raise NativeCfParseError(code, path, detail)
def _attrs(e: ET.Element, allowed: frozenset[str], path: str) -> None:
    for key in e.attrib:
        if key not in allowed: _fail("unknown_attribute", path, key)
def _mixed(e: ET.Element, path: str) -> None:
    if e.text and e.text.strip(): _fail("mixed_content", path, "text")
    for child in e:
        if child.tail and child.tail.strip(): _fail("mixed_content", path, "tail")
def _required(a: dict[str,str], key: str, path: str) -> str:
    value = a.get(key)
    if value is None or not value.strip(): _fail("missing_required_attribute", path, key)
    return value
def _bool(v: str | None, path: str, key: str) -> bool | None:
    if v is None: return None
    if v in ("1","true"): return True
    if v in ("0","false"): return False
    _fail("invalid_boolean", path, key)
def _i32(v: str | None, path: str, key: str) -> int | None:
    if v is None: return None
    lexical = " ".join(v.split())
    if not re.fullmatch(r"[+-]?[0-9]+", lexical): _fail("invalid_integer", path, key)
    result = int(lexical)
    if not INT32_MIN <= result <= INT32_MAX: _fail("integer_out_of_range", path, key)
    return result
def _u32(v: str | None, path: str, key: str) -> int | None:
    if v is None: return None
    lexical = " ".join(v.split())
    if not re.fullmatch(r"\+?[0-9]+", lexical): _fail("invalid_integer", path, key)
    result = int(lexical)
    if result > UINT32_MAX: _fail("integer_out_of_range", path, key)
    return result
def _float(v: str | None, path: str, key: str) -> float | None:
    if v is None: return None
    try: result = float(v)
    except ValueError: _fail("invalid_float", path, key)
    if not math.isfinite(result): _fail("invalid_float", path, key)
    return result
def _enum(v: str | None, choices: frozenset[str], path: str, key: str) -> str | None:
    if v is not None and v not in choices: _fail("invalid_enum", path, key)
    return v
def _column(s: str) -> int:
    value = 0
    for c in s.upper(): value = value * 26 + ord(c) - 64
    return value
def _cell(s: str, path: str) -> None:
    m = _CELL.fullmatch(s)
    if m is None: _fail("malformed_sqref", path, s)
    if _column(m.group(1)) > MAX_COLUMN or int(m.group(2)) > MAX_ROW: _fail("sqref_out_of_bounds", path, s)
def _sqref(v: str | None, path: str) -> tuple[str,...]:
    if v is None or not v.strip(): _fail("missing_sqref", path)
    result = tuple(v.split())
    for token in result:
        m = _RANGE.fullmatch(token)
        if m is None: _fail("malformed_sqref", path, token)
        _cell(m.group(1), path)
        if m.group(2): _cell(m.group(2), path)
    return result
def _uid(v: str | None, path: str) -> str | None:
    if v is not None and not _GUID.fullmatch(v): _fail("invalid_uid", path, v)
    return v

def _extlst(e: ET.Element, path: str) -> NativeCfExtensionList:
    _attrs(e, frozenset(), path); _mixed(e, path)
    values: list[NativeCfExtension] = []
    for index, child in enumerate(e, 1):
        child_path = f"{path}/ext[{index}]"
        if not _main(child, "ext"): _fail("unknown_owned_content", path, str(child.tag))
        _attrs(child, frozenset(("uri",)), child_path)
        values.append(NativeCfExtension(child_path, _required(child.attrib, "uri", child_path), ET.tostring(child, encoding="unicode")))
    return NativeCfExtensionList(path, tuple(values))

def _cfvo(e: ET.Element, path: str, *, gte: bool) -> NativeCfvo:
    _attrs(e, frozenset(("type","val","gte")), path); _mixed(e, path)
    typ = _required(e.attrib, "type", path); _enum(typ, _CFVO, path, "type")
    value = e.attrib.get("val")
    if typ in ("num","percent","percentile","formula") and (value is None or not value.strip()): _fail("missing_required_attribute", path, "val")
    if not gte and "gte" in e.attrib: _fail("invalid_attribute_for_owner", path, "gte")
    children = list(e)
    if len(children) > 1 or (children and not _main(children[0], "extLst")): _fail("unknown_owned_content", path, "cfvo child")
    return NativeCfvo(path, typ, value, _bool(e.attrib.get("gte"),path,"gte"), _extlst(children[0],f"{path}/extLst") if children else None)

def _color(e: ET.Element, path: str) -> NativeColor:
    _attrs(e, frozenset(("rgb","indexed","theme","auto","tint")), path)
    if list(e) or (e.text and e.text.strip()): _fail("unknown_owned_content", path, "color content")
    rgb = e.attrib.get("rgb")
    if rgb is not None and not re.fullmatch(r"[0-9A-Fa-f]{8}",rgb): _fail("invalid_color",path,"rgb")
    indexed, theme, auto = _u32(e.attrib.get("indexed"),path,"indexed"), _u32(e.attrib.get("theme"),path,"theme"), _bool(e.attrib.get("auto"),path,"auto")
    tint = _float(e.attrib.get("tint"),path,"tint")
    if tint is not None and not -1 <= tint <= 1: _fail("float_out_of_range",path,"tint")
    if sum(x is not None for x in (rgb,indexed,theme,auto)) != 1: _fail("invalid_color",path,"one color source required")
    return NativeColor(path,rgb,indexed,theme,auto,tint)

def _colorscale(e: ET.Element, path: str) -> NativeColorScale:
    _attrs(e,frozenset(),path); _mixed(e,path); children=list(e)
    values=[x for x in children if _main(x,"cfvo")]; colors=[x for x in children if _main(x,"color")]
    if len(children) != len(values)+len(colors): _fail("unknown_owned_content",path,"colorScale child")
    if children[:len(values)] != values or children[len(values):] != colors: _fail("invalid_child_order",path,"colorScale")
    if not 2 <= len(values) <= 3 or len(values) != len(colors): _fail("invalid_payload_cardinality",path,"colorScale")
    return NativeColorScale(path,tuple(_cfvo(x,f"{path}/cfvo[{i}]",gte=False) for i,x in enumerate(values,1)),tuple(_color(x,f"{path}/color[{i}]") for i,x in enumerate(colors,1)))

def _databar(e: ET.Element, path: str) -> NativeDataBar:
    _attrs(e,frozenset(("minLength","maxLength","showValue")),path); _mixed(e,path); children=list(e)
    values=[x for x in children if _main(x,"cfvo")]; colors=[x for x in children if _main(x,"color")]
    if len(children)!=len(values)+len(colors): _fail("unknown_owned_content",path,"dataBar child")
    if children[:len(values)] != values or children[len(values):] != colors: _fail("invalid_child_order",path,"dataBar")
    if len(values)!=2 or len(colors)!=1: _fail("invalid_payload_cardinality",path,"dataBar")
    lo,hi=_u32(e.attrib.get("minLength"),path,"minLength"),_u32(e.attrib.get("maxLength"),path,"maxLength")
    if (lo is not None and lo>100) or (hi is not None and hi>100): _fail("integer_out_of_range",path,"dataBar length")
    if lo is not None and hi is not None and lo>hi: _fail("invalid_range",path,"minLength > maxLength")
    return NativeDataBar(path,tuple(_cfvo(x,f"{path}/cfvo[{i}]",gte=False) for i,x in enumerate(values,1)),_color(colors[0],f"{path}/color[1]"),lo,hi,_bool(e.attrib.get("showValue"),path,"showValue"))

def _iconset(e: ET.Element,path: str) -> NativeIconSet:
    _attrs(e,frozenset(("iconSet","showValue","percent","reverse")),path); _mixed(e,path); values=list(e)
    if not all(_main(x,"cfvo") for x in values): _fail("unknown_owned_content",path,"iconSet child")
    icon=_enum(e.attrib.get("iconSet"),_ICONS,path,"iconSet")
    if len(values) != int((icon or "3TrafficLights1")[0]): _fail("invalid_payload_cardinality",path,"iconSet")
    return NativeIconSet(path,tuple(_cfvo(x,f"{path}/cfvo[{i}]",gte=True) for i,x in enumerate(values,1)),icon,_bool(e.attrib.get("showValue"),path,"showValue"),_bool(e.attrib.get("percent"),path,"percent"),_bool(e.attrib.get("reverse"),path,"reverse"))

def _semantics(a: dict[str,str], typ: str, path: str, dxf: int|None, op: str|None, text: str|None, period: str|None, rank: int|None, std: int|None, percent: bool|None, equal: bool|None, formulas: tuple[str,...], payload: NativeCfPayload) -> None:
    for name in ("aboveAverage","equalAverage"):
        if name in a and typ!="aboveAverage": _fail("invalid_attribute_for_rule_type",path,name)
    for name in ("percent","bottom","rank"):
        if name in a and typ!="top10": _fail("invalid_attribute_for_rule_type",path,name)
    if "operator" in a and typ!="cellIs": _fail("invalid_attribute_for_rule_type",path,"operator")
    if "timePeriod" in a and typ!="timePeriod": _fail("invalid_attribute_for_rule_type",path,"timePeriod")
    if "stdDev" in a and typ!="aboveAverage": _fail("invalid_attribute_for_rule_type",path,"stdDev")
    if text is not None and typ not in _TEXT_TYPES: _fail("invalid_attribute_for_rule_type",path,"text")
    if typ in _TEXT_TYPES and not text: _fail("missing_required_attribute",path,"text")
    if typ=="timePeriod" and period is None: _fail("missing_required_attribute",path,"timePeriod")
    if typ=="cellIs" and op is None: _fail("missing_required_attribute",path,"operator")
    if typ=="top10" and rank is not None:
        if percent is True and not 0<=rank<=100: _fail("integer_out_of_range",path,"rank")
        if percent is not True and not 1<=rank<=1000: _fail("integer_out_of_range",path,"rank")
    if std is not None and (std<0 or equal is True): _fail("invalid_attribute_combination",path,"stdDev")
    if typ in ("colorScale","dataBar","iconSet") and dxf is not None: _fail("invalid_attribute_for_rule_type",path,"dxfId")
    expected={"colorScale":NativeColorScale,"dataBar":NativeDataBar,"iconSet":NativeIconSet}.get(typ)
    if expected is not None and not isinstance(payload,expected): _fail("missing_required_payload",path,typ)
    if expected is None and payload is not None: _fail("unexpected_payload",path,typ)
    if len(formulas)>3: _fail("invalid_formula_cardinality",path,"more than three")
    if typ=="expression" and len(formulas)!=1: _fail("invalid_formula_cardinality",path,"expression")
    if typ=="cellIs" and len(formulas)!=(2 if op in ("between","notBetween") else 1): _fail("invalid_formula_cardinality",path,"cellIs")
    if typ in _FORMULA_TYPES-{"expression","cellIs"} and len(formulas)!=1: _fail("invalid_formula_cardinality",path,typ)
    if expected is not None and len(formulas)>1: _fail("invalid_formula_cardinality",path,"payload")

def _rule(e: ET.Element,path: str) -> NativeCfRule:
    _attrs(e,_RULE_ATTRS,path); _mixed(e,path); typ=_required(e.attrib,"type",path); _enum(typ,_TYPES,path,"type")
    priority=_i32(_required(e.attrib,"priority",path),path,"priority")
    assert priority is not None
    if priority<=0: _fail("integer_out_of_range",path,"priority")
    dxf=_u32(e.attrib.get("dxfId"),path,"dxfId")
    op=_enum(e.attrib.get("operator"),_OPERATORS,path,"operator"); period=_enum(e.attrib.get("timePeriod"),_TIMES,path,"timePeriod")
    rank, std=_u32(e.attrib.get("rank"),path,"rank"),_i32(e.attrib.get("stdDev"),path,"stdDev")
    percent,equal=_bool(e.attrib.get("percent"),path,"percent"),_bool(e.attrib.get("equalAverage"),path,"equalAverage")
    formulas: list[str]=[]; payload: NativeCfPayload=None; ext: NativeCfExtensionList|None=None; state=0
    for child in e:
        if _main(child,"formula") and state==0:
            p=f"{path}/formula[{len(formulas)+1}]"; _attrs(child,frozenset(),p)
            if list(child) or child.text is None or not child.text.strip(): _fail("invalid_formula",p)
            formulas.append(child.text); continue
        if _main(child,"colorScale") or _main(child,"dataBar") or _main(child,"iconSet"):
            if state==2 or payload is not None: _fail("invalid_child_order",path,"payload")
            state=1
            payload=_colorscale(child,f"{path}/colorScale[1]") if _main(child,"colorScale") else _databar(child,f"{path}/dataBar[1]") if _main(child,"dataBar") else _iconset(child,f"{path}/iconSet[1]")
            continue
        if _main(child,"extLst"):
            if ext is not None: _fail("invalid_payload_cardinality",path,"extLst")
            state=2; ext=_extlst(child,f"{path}/extLst"); continue
        _fail("unknown_owned_content",path,str(child.tag))
    forms=tuple(formulas)
    _semantics(e.attrib,typ,path,dxf,op,e.attrib.get("text"),period,rank,std,percent,equal,forms,payload)
    return NativeCfRule(path,typ,priority,dxf,_bool(e.attrib.get("stopIfTrue"),path,"stopIfTrue"),_bool(e.attrib.get("aboveAverage"),path,"aboveAverage"),percent,_bool(e.attrib.get("bottom"),path,"bottom"),op,e.attrib.get("text"),period,rank,std,equal,forms,payload,ext)

def read_native_conditional_formatting(worksheet_part: str, worksheet_xml: str|bytes) -> NativeCfReadResult:
    if not isinstance(worksheet_part,str) or not worksheet_part or worksheet_part.strip()!=worksheet_part: _fail("invalid_worksheet_part",str(worksheet_part),"worksheet_part")
    root_path=_path(worksheet_part,"")
    if not isinstance(worksheet_xml,(str,bytes)): _fail("invalid_worksheet_xml",root_path)
    try: root=ET.fromstring(worksheet_xml)
    except ET.ParseError as exc: _fail("invalid_xml",root_path,str(exc))
    if not _main(root,"worksheet"): _fail("invalid_worksheet_root",root_path)
    values: list[NativeConditionalFormatting]=[]; priorities:set[int]=set()
    for group_no,e in enumerate((x for x in root if _main(x,"conditionalFormatting")),1):
        path=_path(worksheet_part,f"conditionalFormatting[{group_no}]"); _attrs(e,frozenset(("sqref","pivot",f"{{{XR_NS}}}uid")),path); _mixed(e,path)
        rules: list[NativeCfRule]=[]; ext:NativeCfExtensionList|None=None
        for child in e:
            if _main(child,"cfRule"):
                if ext is not None: _fail("invalid_child_order",path,"cfRule after extLst")
                rule=_rule(child,f"{path}/cfRule[{len(rules)+1}]")
                if rule.priority in priorities: _fail("duplicate_priority",rule.owner_path,str(rule.priority))
                priorities.add(rule.priority); rules.append(rule)
            elif _main(child,"extLst"):
                if ext is not None: _fail("invalid_payload_cardinality",path,"extLst")
                ext=_extlst(child,f"{path}/extLst")
            else: _fail("unknown_owned_content",path,str(child.tag))
        values.append(NativeConditionalFormatting(path,_sqref(e.attrib.get("sqref"),path),_bool(e.attrib.get("pivot"),path,"pivot"),_uid(e.attrib.get(f"{{{XR_NS}}}uid"),path),tuple(rules),ext))
    return NativeCfReadResult(worksheet_part,tuple(values))

parse_native_conditional_formatting=read_native_conditional_formatting
read_native_cf=read_native_conditional_formatting
__all__=["MAIN_NS","XR_NS","MAX_ROW","INT32_MIN","INT32_MAX","UINT32_MAX","NativeCfParseError","NativeCfFinding","NativeCfExtension","NativeCfExtensionList","NativeCfvo","NativeColor","NativeColorScale","NativeDataBar","NativeIconSet","NativeCfRule","NativeConditionalFormatting","NativeCfReadResult","read_native_conditional_formatting","parse_native_conditional_formatting","read_native_cf"]
