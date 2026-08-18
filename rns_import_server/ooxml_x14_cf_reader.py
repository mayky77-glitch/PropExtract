"""Fail-closed reader for x14 conditional formatting collections."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from xml.etree import ElementTree as ET

X14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"; XM="http://schemas.microsoft.com/office/excel/2006/main"
NS={"x14":X14,"xm":XM}
class X14CFError(ValueError): pass
@dataclass(frozen=True)
class Formula: value:str
@dataclass(frozen=True)
class Rule: worksheet:str;group:int;order:int;type:str|None;priority:int|None;uid:str|None;attributes:tuple[tuple[str,str],...];sqref:tuple[str,...];sqref_attributes:tuple[tuple[str,str],...];formulas:tuple[Formula,...];payload_xml:str|None;dxf_xml:str|None
@dataclass(frozen=True)
class Group: worksheet:str;order:int;attributes:tuple[tuple[str,str],...];sqref:tuple[str,...];sqref_attributes:tuple[tuple[str,str],...];rules:tuple[Rule,...]
@dataclass(frozen=True)
class Collection: worksheet:str;attributes:tuple[tuple[str,str],...];groups:tuple[Group,...]
def _canon(n): return ET.tostring(n,encoding="unicode")
def _attrs(n): return tuple(sorted(n.attrib.items()))
def _parse(raw,part):
 try:return ET.fromstring(raw)
 except ET.ParseError as e:raise X14CFError(f"malformed:{part}") from e
def read_x14_conditional_formats(parts:Mapping[str,bytes])->tuple[Collection,...]:
 out=[]
 for part,raw in parts.items():
  root=_parse(raw,part);collections=[]
  for collection in root.findall(".//x14:conditionalFormattings",NS):
   groups=[]
   for gi,group in enumerate(collection.findall("x14:conditionalFormatting",NS)):
    sq=group.find("xm:sqref",NS);tokens=tuple(("" if sq is None else "".join(sq.itertext())).split());rules=[]
    children=list(group)
    if any(c.tag not in {f"{{{XM}}}sqref",f"{{{X14}}}cfRule"} for c in children):raise X14CFError("unknown-group-child")
    for ri,node in enumerate(group.findall("x14:cfRule",NS)):
     kids=list(node);allowed={f"{{{XM}}}f",f"{{{X14}}}dxf",f"{{{X14}}}colorScale",f"{{{X14}}}dataBar",f"{{{X14}}}iconSet"}
     if any(k.tag not in allowed for k in kids):raise X14CFError("unknown-rule-child")
     formulas=tuple(Formula("".join(k.itertext())) for k in kids if k.tag==f"{{{XM}}}f")
     if len(formulas)>3:raise X14CFError("formula-cardinality")
     dxf=next((k for k in kids if k.tag==f"{{{X14}}}dxf"),None);payload=next((k for k in kids if k.tag in {f"{{{X14}}}colorScale",f"{{{X14}}}dataBar",f"{{{X14}}}iconSet"}),None)
     priority=None if node.get("priority") is None else int(node.get("priority"));rules.append(Rule(part,gi,ri,node.get("type"),priority,node.get("id"),_attrs(node),tokens,_attrs(sq) if sq is not None else (),formulas,_canon(payload) if payload is not None else None,_canon(dxf) if dxf is not None else None))
    groups.append(Group(part,gi,_attrs(group),tokens,_attrs(sq) if sq is not None else (),tuple(rules)))
   collections.append(Collection(part,_attrs(collection),tuple(groups)))
  out.extend(collections)
 return tuple(out)
