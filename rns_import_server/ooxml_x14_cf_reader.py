"""Fail-closed reader for x14 conditional formatting collections."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from re import fullmatch
from xml.etree import ElementTree as ET

X14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"; XM="http://schemas.microsoft.com/office/excel/2006/main"
NS={"x14":X14,"xm":XM}
@dataclass(frozen=True)
class X14CFError(ValueError):
 code:str; owner_path:str; qname:str=""; value:str=""; owner_xml:str=""
 def __str__(self): return f"{self.code}: {self.owner_path}: {self.qname}: {self.value}"
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
def _error(code,path,node=None,qname="",value=""):
 raise X14CFError(code,path,qname,value,"" if node is None else _canon(node))
def _parse(raw,part):
 try:return ET.fromstring(raw)
 except ET.ParseError as e:raise X14CFError("malformed-xml",part,value=str(e)) from e
def _tri(node,key,path):
 value=node.get(key)
 if value is not None and value not in {"0","1","true","false"}:_error("invalid-tristate",path,node,key,value)
 return value
def _priority(node,path):
 value=node.get("priority")
 if value is None:return None
 try:
  result=int(value)
  if result<1:_error("invalid-priority",path,node,"priority",value)
  return result
 except ValueError:_error("invalid-priority",path,node,"priority",value)
def read_x14_conditional_formats(parts:Mapping[str,bytes])->tuple[Collection,...]:
 out=[]
 for part,raw in parts.items():
  root=_parse(raw,part);collections=[]
  for collection in root.findall(".//x14:conditionalFormattings",NS):
   groups=[]
   for gi,group in enumerate(collection.findall("x14:conditionalFormatting",NS)):
    sq=group.find("xm:sqref",NS);tokens=tuple(("" if sq is None else "".join(sq.itertext())).split());rules=[]
    path=f"{part}/collection[{len(collections)}]/group[{gi}]"
    children=list(group)
    if any(c.tag not in {f"{{{XM}}}sqref",f"{{{X14}}}cfRule"} for c in children):_error("unknown-group-child",path,group)
    if children and children[0].tag==f"{{{X14}}}cfRule" and len(children)>1:_error("group-child-order",path,group)
    if children and not tokens and any(c.tag==f"{{{X14}}}cfRule" for c in children):_error("missing-sqref",path,group)
    for ri,node in enumerate(group.findall("x14:cfRule",NS)):
     kids=list(node);allowed={f"{{{XM}}}f",f"{{{X14}}}dxf",f"{{{X14}}}colorScale",f"{{{X14}}}dataBar",f"{{{X14}}}iconSet"}
     rule_path=f"{path}/rule[{ri}]"
     if any(k.tag not in allowed for k in kids):_error("unknown-rule-child",rule_path,node)
     formulas=tuple(Formula("".join(k.itertext())) for k in kids if k.tag==f"{{{XM}}}f")
     if len(formulas)>3:_error("formula-cardinality",rule_path,node)
     dxf=next((k for k in kids if k.tag==f"{{{X14}}}dxf"),None);payload=next((k for k in kids if k.tag in {f"{{{X14}}}colorScale",f"{{{X14}}}dataBar",f"{{{X14}}}iconSet"}),None)
     if sum(k.tag==f"{{{X14}}}dxf" for k in kids)>1 or sum(k.tag in {f"{{{X14}}}colorScale",f"{{{X14}}}dataBar",f"{{{X14}}}iconSet"} for k in kids)>1:_error("duplicate-rule-child",rule_path,node)
     _tri(node,"stopIfTrue",rule_path);_tri(node,"aboveAverage",rule_path);_tri(node,"activePresent",rule_path)
     if node.get("id") is not None and fullmatch(r"\{[0-9A-Fa-f-]{36}\}",node.get("id")) is None:_error("invalid-guid",rule_path,node,"id",node.get("id"))
     priority=_priority(node,rule_path);rules.append(Rule(part,gi,ri,node.get("type"),priority,node.get("id"),_attrs(node),tokens,_attrs(sq) if sq is not None else (),formulas,_canon(payload) if payload is not None else None,_canon(dxf) if dxf is not None else None))
    groups.append(Group(part,gi,_attrs(group),tokens,_attrs(sq) if sq is not None else (),tuple(rules)))
   collections.append(Collection(part,_attrs(collection),tuple(groups)))
  out.extend(collections)
 return tuple(out)
