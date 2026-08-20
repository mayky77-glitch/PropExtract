"""Strict, immutable X14 conditional-formatting owner topology reader."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile
import zlib

from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology

_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
_XM: Final = "http://schemas.microsoft.com/office/excel/2006/main"
_WORKSHEET=f"{{{_SML}}}worksheet"; _EXTLST=f"{{{_SML}}}extLst"; _EXT=f"{{{_SML}}}ext"
_FORMS=f"{{{_X14}}}conditionalFormattings"; _FORM=f"{{{_X14}}}conditionalFormatting"
_RULE=f"{{{_X14}}}cfRule"; _DXF=f"{{{_X14}}}dxf"; _DV=f"{{{_X14}}}dataValidations"; _DV_ITEM=f"{{{_X14}}}dataValidation"
_F=f"{{{_XM}}}f"; _SQREF=f"{{{_XM}}}sqref"
_CF_URI="{78C0D931-6437-407d-A8EE-F0AAD7539E65}"; _DV_URI="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"
_OWNED=frozenset({_FORMS,_FORM,_RULE,_DXF,_F,_SQREF})
_LOCALS=frozenset({"conditionalFormattings","conditionalFormatting","cfRule","dxf","f","sqref"})

__all__=("OPCWorksheetX14CfOwnerTopologyError","X14CfContainerOwner","WorksheetX14CfOwnerTopology","WorkbookX14CfOwnerTopology","X14CfRuleEnvelope","X14CfContainerEnvelope","WorksheetX14CfEnvelope","WorkbookX14CfEnvelope","read_worksheet_x14_cf_owner_topology","read_worksheet_x14_cf_envelope")

@dataclass(frozen=True)
class X14CfContainerOwner:
    owner_path: str
    document_order: int
@dataclass(frozen=True)
class WorksheetX14CfOwnerTopology:
    worksheet: WorksheetDescriptor
    containers: tuple[X14CfContainerOwner,...]
@dataclass(frozen=True)
class WorkbookX14CfOwnerTopology:
    worksheets: tuple[WorksheetX14CfOwnerTopology,...]
@dataclass(frozen=True)
class X14CfRuleEnvelope:
    owner_path: str
    document_order: int
    type: str
    priority: int
    stop_if_true: bool | None
    rule_id: str
    formula: str
    has_inline_dxf: bool
@dataclass(frozen=True)
class X14CfContainerEnvelope:
    owner: X14CfContainerOwner
    sqref_text: str
    rules: tuple[X14CfRuleEnvelope,...]
@dataclass(frozen=True)
class WorksheetX14CfEnvelope:
    worksheet: WorksheetDescriptor
    containers: tuple[X14CfContainerEnvelope,...]
@dataclass(frozen=True)
class WorkbookX14CfEnvelope:
    worksheets: tuple[WorksheetX14CfEnvelope,...]
@dataclass
class OPCWorksheetX14CfOwnerTopologyError(ValueError):
    code: str
    subject: str
    field: str
    detail: str
    def __post_init__(self)->None: ValueError.__init__(self,self.code,self.subject,self.field,self.detail)
    def as_tuple(self)->tuple[str,str,str,str]: return (self.code,self.subject,self.field,self.detail)
def _fail(*v:str)->None: raise OPCWorksheetX14CfOwnerTopologyError(*v)

def _path(value:os.PathLike[str]|str)->str:
    subject=f"{type(value).__module__}.{type(value).__qualname__}"
    try: result=os.fspath(value)
    except TypeError as error: _fail("invalid-package-path",subject,"path",type(error).__name__)
    except Exception as error: _fail("unreadable-package",subject,"path",type(error).__name__)
    if not isinstance(result,str): _fail("invalid-package-path",subject,"path",type(result).__name__)
    if "\0" in result: _fail("unreadable-package",result,"path","embedded-nul")
    return result
def _case_dot_key(value:str)->str|None:
    if not value or value.startswith("/") or value.endswith("/") or "//" in value:return None
    result=[]
    for piece in value.split("/"):
        if piece==".":continue
        if piece=="..":
            if not result:return None
            result.pop()
        else:result.append(piece)
    return "/".join(result).casefold()
def _member(path:str,part:CanonicalPartURI)->bytes:
    try:
        with ZipFile(path) as archive:
            found=[]
            for info in archive.infolist():
                try: canonical=canonicalize_part_uri(info.filename)
                except OPCPartURIError:
                    if _case_dot_key(info.filename)!=part.value.casefold():_fail("unreadable-worksheet-part",part.value,"member","invalid-member-name")
                    found.append(info);continue
                if canonical==part or canonical.value.casefold()==part.value.casefold() or _case_dot_key(info.filename)==part.value.casefold():found.append(info)
            if not found:_fail("missing-worksheet-member",part.value,"member",part.value)
            if len(found)!=1:_fail("ambiguous-worksheet-member",part.value,"member",part.value)
            if found[0].filename!=part.value:_fail("noncanonical-worksheet-member",part.value,"member",found[0].filename)
            return archive.read(found[0])
    except OPCWorksheetX14CfOwnerTopologyError:raise
    except (BadZipFile,LargeZipFile,KeyError,OSError,RuntimeError,ValueError,zlib.error) as error:_fail("unreadable-worksheet-part",part.value,"xml",type(error).__name__)
def _xml(payload:bytes,part:CanonicalPartURI)->ET.Element:
    try:return ET.fromstring(payload)
    except (LookupError,ValueError):_fail("unsupported-xml-encoding",part.value,"xml","encoding")
    except ET.ParseError as error:
        unknown="unknown encoding" in str(error).lower()
        _fail("unsupported-xml-encoding" if unknown else "malformed-worksheet-xml",part.value,"xml","encoding" if unknown else "xml")
    except UnicodeError:_fail("malformed-worksheet-xml",part.value,"xml","xml")
def _local(tag:object)->str:return tag.rsplit("}",1)[-1] if isinstance(tag,str) else ""
def _nonwhite(value:str|None)->bool:return bool(value and not value.isspace())
def _native_allowed(tag:object,parent:ET.Element|None)->bool:
    return (tag==f"{{{_SML}}}conditionalFormatting" and parent is not None and parent.tag==_WORKSHEET) or (tag==f"{{{_SML}}}cfRule" and parent is not None and parent.tag==f"{{{_SML}}}conditionalFormatting") or (tag==f"{{{_SML}}}f" and parent is not None and parent.tag in {f"{{{_SML}}}c",f"{{{_SML}}}cfRule"})

def _inspect(root:ET.Element,part:CanonicalPartURI,base:int):
    """One DFS event stream: child errors at entry, cardinality at owner exit."""
    faults=[]; owners=[]; event=base; cf_count=0; extlst_seen=0
    def add(tier,code,field,detail):faults.append((tier,event,(code,part.value,field,detail)))
    def walk(node,parent,*,parent_direct_extlst,parent_cf_ext,parent_dv_ext,parent_dv,parent_dv_item,parent_forms,parent_form,parent_rule,extlst_index,ext_index):
        nonlocal event,cf_count,extlst_seen
        event+=1; start=event; tag=node.tag; local=_local(tag)
        direct_extlst=parent is root and tag==_EXTLST
        if direct_extlst:extlst_seen+=1;extlst_index=extlst_seen
        direct_ext=parent_direct_extlst and tag==_EXT
        cf_ext=direct_ext and node.attrib.get("uri","")==_CF_URI
        dv_ext=direct_ext and node.attrib=={"uri":_DV_URI}
        forms=tag==_FORMS and parent_cf_ext
        form=tag==_FORM and parent_forms
        rule=tag==_RULE and parent_form
        dxf=tag==_DXF and parent_rule
        dv_here=tag==_DV and parent_dv_ext
        dv_item=tag==_DV_ITEM and parent_dv
        dv_value=tag in {_F,_SQREF} and (parent_dv or parent_dv_item)
        if local in _LOCALS and tag not in _OWNED and not _native_allowed(tag,parent):add(1,"x14-cf-namespace-collision","tag",str(tag))
        elif tag==_FORMS and not forms:add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag==_FORM and not form:add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag==_RULE and not rule:add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag==_DXF and not dxf:add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag in {_F,_SQREF} and not (dv_value or (tag==_F and parent_rule) or (tag==_SQREF and parent_form)):add(1,"invalid-x14-cf-parent","tag",str(tag))
        if parent_cf_ext and tag!=_FORMS:add(2,"unknown-x14-cf-child","tag",str(tag))
        elif parent_forms and tag!=_FORM:add(2,"unknown-x14-cf-child","tag",str(tag))
        elif parent_form and tag not in {_RULE,_SQREF}:add(2,"unknown-x14-cf-child","tag",str(tag))
        elif parent_rule and tag not in {_F,_DXF}:add(2,"unknown-x14-cf-child","tag",str(tag))
        if direct_extlst and node.attrib:add(2,"unknown-x14-cf-attribute","attribute",sorted(node.attrib)[0])
        if direct_ext and any(child.tag==_FORMS for child in node) and not (cf_ext or dv_ext):
            add(1,"unsupported-x14-cf-extension-uri","uri",node.attrib.get("uri", ""))
        if cf_ext:
            cf_count+=1
            if cf_count>1:add(1,"duplicate-x14-cf-extension","uri",_CF_URI)
            extra=sorted(set(node.attrib)-{"uri"})
            if extra:add(2,"unknown-x14-cf-attribute","attribute",extra[0])
        if tag==_FORMS and forms and node.attrib:add(2,"unknown-x14-cf-attribute","attribute",sorted(node.attrib)[0])
        if tag==_FORM and form and node.attrib:add(2,"unknown-x14-cf-attribute","attribute",sorted(node.attrib)[0])
        if _nonwhite(node.text) and tag in {_EXTLST,_FORMS,_FORM,_RULE}|({_EXT} if cf_ext else set()):add(2,"invalid-x14-cf-content",local,"text")
        child_ext=0
        for child in node:
            child_index=ext_index
            if direct_extlst and child.tag==_EXT:child_ext+=1;child_index=child_ext
            walk(child,node,parent_direct_extlst=direct_extlst,parent_cf_ext=cf_ext,parent_dv_ext=dv_ext,parent_dv=dv_here,parent_dv_item=dv_item,parent_forms=forms,parent_form=form,parent_rule=rule,extlst_index=extlst_index,ext_index=child_index)
            event+=1
            if _nonwhite(child.tail) and tag in {_EXTLST,_FORMS,_FORM,_RULE}|({_EXT} if cf_ext else set()):add(2,"invalid-x14-cf-content",local,"tail")
        if cf_ext and sum(child.tag==_FORMS for child in node)!=1:add(1,"invalid-x14-cf-cardinality","ext","conditionalFormattings")
        if tag==_FORMS and forms and not any(child.tag==_FORM for child in node):add(1,"invalid-x14-cf-cardinality","conditionalFormattings","conditionalFormatting")
        if tag==_FORM and form:owners.append((start,extlst_index or 0,ext_index or 0,node))
        event+=1
    walk(root,None,parent_direct_extlst=False,parent_cf_ext=False,parent_dv_ext=False,parent_dv=False,parent_dv_item=False,parent_forms=False,parent_form=False,parent_rule=False,extlst_index=None,ext_index=None)
    return faults,owners,event

def _accepted(package_path:os.PathLike[str]|str):
    path=_path(package_path); topology=read_workbook_topology(path)
    trees=[(sheet,sheet.worksheet_part,_xml(_member(path,sheet.worksheet_part),sheet.worksheet_part)) for sheet in topology.worksheets]
    for _,part,root in trees:
        if root.tag!=_WORKSHEET:_fail("invalid-worksheet-root",part.value,"root",str(root.tag))
    faults=[]; inspected=[]; base=0
    for sheet,part,root in trees:
        current,owners,base=_inspect(root,part,base);faults.extend(current);inspected.append((sheet,part,owners))
    if faults:
        tier=min(item[0] for item in faults);_fail(*min((item for item in faults if item[0]==tier),key=lambda item:item[1])[2])
    worksheets=[]; validated=[]
    for sheet,part,specs in inspected:
        counts={}; owners=[]
        for document_order,(_,extlst,ext,node) in enumerate(specs,1):
            key=(extlst,ext);counts[key]=counts.get(key,0)+1
            owners.append(X14CfContainerOwner(f"{part.value}/worksheet/extLst[{extlst}]/ext[{ext}]/conditionalFormattings[1]/conditionalFormatting[{counts[key]}]",document_order))
        owner_tuple=tuple(owners)
        worksheets.append(WorksheetX14CfOwnerTopology(sheet,owner_tuple))
        validated.append((sheet,part,owner_tuple,tuple(item[3] for item in specs)))
    return WorkbookX14CfOwnerTopology(tuple(worksheets)),tuple(validated)

def read_worksheet_x14_cf_owner_topology(package_path:os.PathLike[str]|str)->WorkbookX14CfOwnerTopology:
    topology,_=_accepted(package_path)
    return topology

_GUID=re.compile(r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$")
_INT32=2147483647

def _semantic_fail(code:str,part:CanonicalPartURI,field:str,detail:str)->None:
    _fail(code,part.value,field,detail)

def _rule_envelope(node:ET.Element,owner:X14CfContainerOwner,index:int,document_order:int,part:CanonicalPartURI)->X14CfRuleEnvelope:
    required={"type","priority","id"}; allowed=required|{"stopIfTrue"}
    extra=sorted(set(node.attrib)-allowed)
    if extra:_semantic_fail("unknown-x14-cf-attribute",part,"attribute",extra[0])
    missing=sorted(required-set(node.attrib))
    if missing:_semantic_fail("invalid-x14-cf-cardinality",part,"attribute",missing[0])
    if node.attrib["type"]!="expression":_semantic_fail("unsupported-x14-cf-rule-type",part,"type",node.attrib["type"])
    raw=node.attrib["priority"]
    significant=raw.strip()
    if len(raw)>64 or len(significant)>16 or not re.fullmatch(r"[+]?[1-9][0-9]*",significant):_semantic_fail("invalid-x14-cf-priority",part,"priority",raw)
    priority=int(significant)
    if priority>_INT32:_semantic_fail("invalid-x14-cf-priority",part,"priority",raw)
    boolean=None
    if "stopIfTrue" in node.attrib:
        token=node.attrib["stopIfTrue"]
        if token not in {"0","1","false","true"}:_semantic_fail("invalid-x14-cf-boolean",part,"stopIfTrue",token)
        boolean=token in {"1","true"}
    rule_id=node.attrib["id"]
    if not _GUID.fullmatch(rule_id):_semantic_fail("invalid-x14-cf-id",part,"id",rule_id)
    children=list(node)
    if len(children)!=2:_semantic_fail("invalid-x14-cf-cardinality",part,"cfRule","f,dxf")
    if [child.tag for child in children]!=[_F,_DXF]:_semantic_fail("invalid-x14-cf-order",part,"cfRule","f,dxf")
    formula,dxf=children
    if formula.attrib or list(formula) or not formula.text or not formula.text.strip() or _nonwhite(formula.tail):_semantic_fail("invalid-x14-cf-formula",part,"f","content")
    if dxf.attrib or _nonwhite(dxf.text) or _nonwhite(dxf.tail):_semantic_fail("invalid-x14-cf-dxf",part,"dxf","content")
    dxf_children=list(dxf)
    for child in dxf_children:
        if _nonwhite(child.tail):_semantic_fail("invalid-x14-cf-dxf",part,"dxf","tail")
        if child.tag not in {f"{{{_SML}}}font",f"{{{_SML}}}fill"}:
            _semantic_fail("unknown-x14-cf-child",part,"tag",str(child.tag))
    tags=[child.tag for child in dxf_children]
    if tags not in ([],[f"{{{_SML}}}font"],[f"{{{_SML}}}font",f"{{{_SML}}}fill"]):_semantic_fail("invalid-x14-cf-dxf",part,"child","font,fill")
    return X14CfRuleEnvelope(f"{owner.owner_path}/cfRule[{index}]",document_order,"expression",priority,boolean,rule_id,formula.text,True)

def _container_envelope(node:ET.Element,owner:X14CfContainerOwner,part:CanonicalPartURI,offset:int,priorities:set[int]):
    children=list(node)
    if not children:_semantic_fail("invalid-x14-cf-cardinality",part,"conditionalFormatting","cfRule,sqref")
    if children[-1].tag!=_SQREF or any(child.tag!=_RULE for child in children[:-1]):_semantic_fail("invalid-x14-cf-order",part,"conditionalFormatting","cfRule,sqref")
    rules=[]
    for index,rule in enumerate(children[:-1],1):
        envelope=_rule_envelope(rule,owner,index,offset+index,part)
        if envelope.priority in priorities:_semantic_fail("duplicate-x14-cf-priority",part,"priority",str(envelope.priority))
        priorities.add(envelope.priority); rules.append(envelope)
    if not rules:_semantic_fail("invalid-x14-cf-cardinality",part,"conditionalFormatting","cfRule")
    sqref=children[-1]
    if sqref.attrib or list(sqref) or not sqref.text or not sqref.text.strip() or _nonwhite(sqref.tail):_semantic_fail("invalid-x14-cf-sqref",part,"sqref","content")
    return X14CfContainerEnvelope(owner,sqref.text,tuple(rules)),offset+len(rules)

def read_worksheet_x14_cf_envelope(package_path:os.PathLike[str]|str)->WorkbookX14CfEnvelope:
    topology,validated=_accepted(package_path)
    worksheets=[]
    for topology_sheet,(_,part,owners,nodes) in zip(topology.worksheets,validated):
        priorities=set(); offset=0; containers=[]
        for owner,node in zip(owners,nodes):
            container,offset=_container_envelope(node,owner,part,offset,priorities)
            containers.append(container)
        worksheets.append(WorksheetX14CfEnvelope(topology_sheet.worksheet,tuple(containers)))
    return WorkbookX14CfEnvelope(tuple(worksheets))
