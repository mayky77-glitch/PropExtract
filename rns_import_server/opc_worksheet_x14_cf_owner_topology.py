"""Strict, immutable X14 conditional-formatting owner topology reader."""
from __future__ import annotations
from dataclasses import dataclass
import os
from typing import Final
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, LargeZipFile, ZipFile
import zlib
from .opc_part_uri import CanonicalPartURI, OPCPartURIError, canonicalize_part_uri
from .opc_workbook_topology import WorksheetDescriptor, read_workbook_topology

_SML: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"; _X14: Final = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"; _XM: Final = "http://schemas.microsoft.com/office/excel/2006/main"
_WORKSHEET=f"{{{_SML}}}worksheet"; _EXTLST=f"{{{_SML}}}extLst"; _EXT=f"{{{_SML}}}ext"; _FORMS=f"{{{_X14}}}conditionalFormattings"; _FORM=f"{{{_X14}}}conditionalFormatting"; _RULE=f"{{{_X14}}}cfRule"; _DXF=f"{{{_X14}}}dxf"; _DV=f"{{{_X14}}}dataValidations"; _F=f"{{{_XM}}}f"; _SQREF=f"{{{_XM}}}sqref"
_CF_URI="{78C0D931-6437-407d-A8EE-F0AAD7539E65}"; _DV_URI="{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}"
_OWNED=frozenset({_FORMS,_FORM,_RULE,_DXF,_F,_SQREF}); _LOCALS=frozenset({"conditionalFormattings","conditionalFormatting","cfRule","dxf","f","sqref"})
__all__=("OPCWorksheetX14CfOwnerTopologyError","X14CfContainerOwner","WorksheetX14CfOwnerTopology","WorkbookX14CfOwnerTopology","read_worksheet_x14_cf_owner_topology")

@dataclass(frozen=True)
class X14CfContainerOwner: owner_path: str; document_order: int
@dataclass(frozen=True)
class WorksheetX14CfOwnerTopology: worksheet: WorksheetDescriptor; containers: tuple[X14CfContainerOwner,...]
@dataclass(frozen=True)
class WorkbookX14CfOwnerTopology: worksheets: tuple[WorksheetX14CfOwnerTopology,...]
@dataclass
class OPCWorksheetX14CfOwnerTopologyError(ValueError):
    code:str; subject:str; field:str; detail:str
    def __post_init__(self): ValueError.__init__(self,self.code,self.subject,self.field,self.detail)
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
        bad="unknown encoding" in str(error).lower();_fail("unsupported-xml-encoding" if bad else "malformed-worksheet-xml",part.value,"xml","encoding" if bad else "xml")
    except UnicodeError:_fail("malformed-worksheet-xml",part.value,"xml","xml")
def _local(tag:object)->str:return tag.rsplit("}",1)[-1] if isinstance(tag,str) else ""
def _nonwhite(value:str|None)->bool:return bool(value and not value.isspace())
def _native_allowed(tag:object,parent:ET.Element|None)->bool:return (tag==f"{{{_SML}}}conditionalFormatting" and parent is not None and parent.tag==_WORKSHEET) or (tag==f"{{{_SML}}}cfRule" and parent is not None and parent.tag==f"{{{_SML}}}conditionalFormatting") or (tag==f"{{{_SML}}}f" and parent is not None and parent.tag in {f"{{{_SML}}}c",f"{{{_SML}}}cfRule"})

def _inspect(root:ET.Element,part:CanonicalPartURI,base:int):
    faults=[]; owners=[]; event=base; cf_count=0; extlst_seen=0
    def walk(node,parent,extlst_index,ext_index,forms_valid,dv_valid):
        nonlocal event,cf_count,extlst_seen
        event+=1; start=event; tag=node.tag; local=_local(tag)
        direct_extlst=parent is root and tag==_EXTLST; direct_ext=parent is not None and parent.tag==_EXTLST and tag==_EXT
        if direct_extlst: extlst_seen+=1; extlst_index=extlst_seen
        cf_ext=direct_ext and node.attrib.get("uri","")==_CF_URI
        dv_ext=direct_ext and node.attrib=={"uri":_DV_URI}
        def add(tier,code,field,detail):faults.append((tier,event,(code,part.value,field,detail)))
        if local in _LOCALS and tag not in _OWNED and not _native_allowed(tag,parent):add(1,"x14-cf-namespace-collision","tag",str(tag))
        elif tag==_FORMS and not forms_valid:add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag==_FORM and (parent is None or parent.tag!=_FORMS or not forms_valid):add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag==_RULE and (parent is None or parent.tag!=_FORM):add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag==_DXF and (parent is None or parent.tag!=_RULE):add(1,"invalid-x14-cf-parent","tag",str(tag))
        elif tag in {_F,_SQREF} and not dv_valid and not ((tag==_F and parent is not None and parent.tag==_RULE) or (tag==_SQREF and parent is not None and parent.tag==_FORM)):add(1,"invalid-x14-cf-parent","tag",str(tag))
        if direct_ext and any(child.tag==_FORMS for child in node) and not cf_ext:add(1,"unsupported-x14-cf-extension-uri","uri",node.attrib.get("uri", ""))
        if direct_extlst and node.attrib:add(2,"unknown-x14-cf-attribute","attribute",sorted(node.attrib)[0])
        forms=[child for child in node if child.tag==_FORMS] if cf_ext else []
        if cf_ext:
            cf_count+=1
            if set(node.attrib)!={"uri"}:add(2,"unknown-x14-cf-attribute","attribute",sorted(set(node.attrib)-{"uri"})[0] if set(node.attrib)-{"uri"} else "uri")
            if len(forms)!=1:add(1,"invalid-x14-cf-cardinality","ext","conditionalFormattings")
        if tag==_FORMS and forms_valid:
            if node.attrib:add(2,"unknown-x14-cf-attribute","attribute",sorted(node.attrib)[0])
            if not any(child.tag==_FORM for child in node):add(1,"invalid-x14-cf-cardinality","conditionalFormattings","conditionalFormatting")
        if tag==_FORM and forms_valid:
            if node.attrib:add(2,"unknown-x14-cf-attribute","attribute",sorted(node.attrib)[0])
            owners.append((start,extlst_index,ext_index))
        if _nonwhite(node.text) and tag in {_EXTLST,_FORMS,_FORM} | ({_EXT} if cf_ext else set()):add(2,"invalid-x14-cf-content",local,"text")
        child_ext=0
        for child in node:
            if tag==_EXTLST and child.tag==_EXT:child_ext+=1
            child_forms_valid=(cf_ext and child.tag==_FORMS) or (forms_valid and child.tag==_FORM)
            child_dv_valid=dv_valid or (dv_ext and child.tag==_DV)
            walk(child,node,extlst_index,child_ext if tag==_EXTLST and child.tag==_EXT else ext_index,child_forms_valid,child_dv_valid)
            event+=1
            if _nonwhite(child.tail) and tag in {_EXTLST,_FORMS,_FORM} | ({_EXT} if cf_ext else set()):add(2,"invalid-x14-cf-content",local,"tail")
        if cf_ext:
            for child in node:
                if child.tag!=_FORMS:add(2,"unknown-x14-cf-child","tag",str(child.tag))
        if tag==_FORMS and forms_valid:
            for child in node:
                if child.tag!=_FORM:add(2,"unknown-x14-cf-child","tag",str(child.tag))
        if tag==_FORM and forms_valid:
            for child in node:
                if child.tag not in {_RULE,_SQREF}:add(2,"unknown-x14-cf-child","tag",str(child.tag))
        if tag==_RULE and parent is not None and parent.tag==_FORM:
            for child in node:
                if child.tag not in {_F,_DXF}:add(2,"unknown-x14-cf-child","tag",str(child.tag))
        event+=1
    walk(root,None,None,None,False,False)
    if cf_count>1:faults.append((1,base,("duplicate-x14-cf-extension",part.value,"uri",_CF_URI)))
    return faults,owners,event

def read_worksheet_x14_cf_owner_topology(package_path:os.PathLike[str]|str)->WorkbookX14CfOwnerTopology:
    path=_path(package_path); topology=read_workbook_topology(path)
    trees=[(sheet,sheet.worksheet_part,_xml(_member(path,sheet.worksheet_part),sheet.worksheet_part)) for sheet in topology.worksheets]
    for _,part,root in trees:
        if root.tag!=_WORKSHEET:_fail("invalid-worksheet-root",part.value,"root",str(root.tag))
    faults=[]; inspected=[]; base=0
    for sheet,part,root in trees:
        current,owners,base=_inspect(root,part,base);faults.extend(current);inspected.append((sheet,part,owners))
    if faults:
        tier=min(item[0] for item in faults);_fail(*min((item for item in faults if item[0]==tier),key=lambda item:item[1])[2])
    worksheets=[]
    for sheet,part,specs in inspected:
        counts={}; owners=[]
        for document_order,(_,extlst,ext) in enumerate(specs,1):
            key=(extlst,ext);counts[key]=counts.get(key,0)+1
            owners.append(X14CfContainerOwner(f"{part.value}/worksheet/extLst[{extlst}]/ext[{ext}]/conditionalFormattings[1]/conditionalFormatting[{counts[key]}]",document_order))
        worksheets.append(WorksheetX14CfOwnerTopology(sheet,tuple(owners)))
    return WorkbookX14CfOwnerTopology(tuple(worksheets))
