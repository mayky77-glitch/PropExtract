"""Read-only namespace-aware typed semantic model for XLSX OPC packages."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS={"ct":"http://schemas.openxmlformats.org/package/2006/content-types","pr":"http://schemas.openxmlformats.org/package/2006/relationships","x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main","r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL="http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
REL_OFFICE_DOCUMENT,REL_WORKSHEET,REL_SHARED_STRINGS,REL_STYLES,REL_HYPERLINK=(REL+x for x in ("officeDocument","worksheet","sharedStrings","styles","hyperlink"))
@dataclass(frozen=True)
class Finding: code:str; part:str; detail:str
class OPCWorkbookError(ValueError):
 def __init__(self,code,part,detail): self.finding=Finding(code,part,detail);super().__init__(f"{code}: {part}: {detail}")
@dataclass(frozen=True)
class Relationship: id:str;type:str;target:str;target_mode:str;resolved_target:str|None
@dataclass(frozen=True)
class ContentType: part_name:str|None;extension:str|None;content_type:str
@dataclass(frozen=True)
class Color: attributes:tuple[tuple[str,str],...]
@dataclass(frozen=True)
class Font: name:str|None;size:float|None;bold:bool;italic:bool;color:Color|None;attributes:tuple[tuple[str,str],...];elements:tuple[tuple[str,tuple[tuple[str,str],...]],...]
@dataclass(frozen=True)
class Fill: pattern_type:str|None;foreground_color:Color|None;background_color:Color|None;attributes:tuple[tuple[str,str],...];elements:tuple[tuple[str,tuple[tuple[str,str],...]],...]
@dataclass(frozen=True)
class BorderSide: style:str|None;color:Color|None;attributes:tuple[tuple[str,str],...]
@dataclass(frozen=True)
class Border: left:BorderSide|None;right:BorderSide|None;top:BorderSide|None;bottom:BorderSide|None;diagonal:BorderSide|None;attributes:tuple[tuple[str,str],...];elements:tuple[tuple[str,tuple[tuple[str,str],...]],...]
@dataclass(frozen=True)
class CellStyle:
 number_format:str;num_fmt_id:int;font_id:int;fill_id:int;border_id:int;font:Font|None;fill:Fill|None;border:Border|None;alignment:tuple[tuple[str,str],...];protection:tuple[tuple[str,str],...];attributes:tuple[tuple[str,str],...];fingerprint:str
@dataclass(frozen=True)
class Formula: text:str;kind:str|None;shared_index:int|None;ref:str|None
@dataclass(frozen=True)
class Cell:
 coordinate:str;cell_type:str|None;raw_value:str|None;value:str|None;shared_string_index:int|None;inline_string:str|None;error:str|None;formula:Formula|None;cached_value:str|None;style_index:int|None;style_fingerprint:str|None
@dataclass(frozen=True)
class Row: index:int;height:float|None;hidden:bool;outline_level:int;style_index:int|None;cells:tuple[Cell,...]
@dataclass(frozen=True)
class Column: minimum:int;maximum:int;width:float|None;hidden:bool;outline_level:int;style_index:int|None
@dataclass(frozen=True)
class Hyperlink: reference:str;location:str|None;display:str|None;tooltip:str|None;relationship:Relationship|None
@dataclass(frozen=True)
class DefinedName: name:str;text:str;local_sheet_id:int|None;hidden:bool
@dataclass(frozen=True)
class Worksheet:
 name:str;sheet_id:int;state:str;part:str;dimension:str|None;rows:tuple[Row,...];columns:tuple[Column,...];hyperlinks:tuple[Hyperlink,...];merges:tuple[str,...];auto_filter:str|None;findings:tuple[Finding,...]
@dataclass(frozen=True)
class WorkbookModel:
 contract_version:str;content_types:tuple[ContentType,...];package_relationships:tuple[Relationship,...];sheets:tuple[Worksheet,...];defined_names:tuple[DefinedName,...];styles:tuple[CellStyle,...];relationships:tuple[Relationship,...];part_digests:tuple[tuple[str,str],...];findings:tuple[Finding,...]

def _xml(raw,part):
 try:return ET.fromstring(raw)
 except ET.ParseError as error:raise OPCWorkbookError("malformed-xml",part,str(error)) from error
def _attrs(node):return () if node is None else tuple(sorted(node.attrib.items()))
def _text(node):return None if node is None else "".join(node.itertext())
def _bool(value):return value in {"1","true","True"}
def _integer(value,part,detail,default=0):
 try:return default if value is None else int(value)
 except ValueError as error:raise OPCWorkbookError("invalid-integer",part,detail) from error
def _float(value,part,detail):
 try:return None if value is None else float(value)
 except ValueError as error:raise OPCWorkbookError("invalid-float",part,detail) from error
def _color(node):return None if node is None else Color(_attrs(node))
def _elements(node):return tuple((child.tag.rsplit("}",1)[-1],_attrs(child)) for child in node)
def _normal_part(name,source):
 if not name or name.startswith("/") or "\\" in name:raise OPCWorkbookError("invalid-part-path",source,name)
 stack=[]
 for piece in name.split("/"):
  if piece in {"","."}:continue
  if piece=="..":
   if not stack:raise OPCWorkbookError("part-traversal",source,name)
   stack.pop()
  else:stack.append(piece)
 if not stack:raise OPCWorkbookError("part-traversal",source,name)
 return "/".join(stack)
def _valid_uri(target,part,external):
 if not target or any(c.isspace() or ord(c)<32 for c in target):raise OPCWorkbookError("invalid-relationship-target",part,target)
 chunks=target.split("%")[1:]
 if any(len(chunk)<2 or any(c not in "0123456789abcdefABCDEF" for c in chunk[:2]) for chunk in chunks):raise OPCWorkbookError("invalid-relationship-target",part,target)
 parsed=urlsplit(target)
 if external and (not parsed.scheme or parsed.scheme.lower() in {"http","https","ftp"} and not parsed.netloc):raise OPCWorkbookError("invalid-external-relationship-target",part,target)
 if not external and (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment):raise OPCWorkbookError("invalid-relationship-target",part,target)
def _resolve_target(source,target,root=False):
 _valid_uri(target,source,False);base="" if root else str(PurePosixPath(source).parent);return _normal_part(f"{base}/{target}" if base else target,source)
def _relationships(raw,relationship_part,source_part,parts,root=False):
 document=_xml(raw,relationship_part)
 if document.tag!=f"{{{NS['pr']}}}Relationships":raise OPCWorkbookError("malformed-relationships",relationship_part,document.tag)
 result=[];seen=set()
 for node in document.findall("pr:Relationship",NS):
  ident,kind,target,mode=node.get("Id"),node.get("Type"),node.get("Target"),node.get("TargetMode","Internal")
  if not ident or not kind or target is None or ident in seen or mode not in {"Internal","External"}:raise OPCWorkbookError("malformed-relationship",relationship_part,ET.tostring(node,encoding="unicode"))
  seen.add(ident)
  if mode=="External":_valid_uri(target,source_part,True);resolved=None
  else:
   resolved=_resolve_target(source_part,target,root)
   if resolved not in parts:raise OPCWorkbookError("missing-relationship-target",source_part,resolved)
  result.append(Relationship(ident,kind,target,mode,resolved))
 return tuple(result)
def _content_types(raw):
 root=_xml(raw,"[Content_Types].xml")
 if root.tag!=f"{{{NS['ct']}}}Types":raise OPCWorkbookError("invalid-content-types","[Content_Types].xml",root.tag)
 result=[]
 for node in root:
  ct=node.get("ContentType")
  if node.tag==f"{{{NS['ct']}}}Default":
   if not node.get("Extension") or not ct:raise OPCWorkbookError("invalid-content-type","[Content_Types].xml",ET.tostring(node,encoding="unicode"))
   result.append(ContentType(None,node.get("Extension"),ct))
  elif node.tag==f"{{{NS['ct']}}}Override":
   name=node.get("PartName")
   if not name or not name.startswith("/") or not ct:raise OPCWorkbookError("invalid-content-type","[Content_Types].xml",ET.tostring(node,encoding="unicode"))
   result.append(ContentType(_normal_part(name[1:],"[Content_Types].xml"),None,ct))
 return tuple(result)
def _style_index(value,styles,part,owner):
 if value is None:return None
 index=_integer(value,part,owner)
 if index<0 or index>=len(styles):raise OPCWorkbookError("style-index-out-of-range",part,owner)
 return index
def _styles(raw,part):
 if raw is None:return ()
 root=_xml(raw,part);formats={0:"General",14:"mm-dd-yy",22:"m/d/yy h:mm"}
 for node in root.findall("x:numFmts/x:numFmt",NS):formats[_integer(node.get("numFmtId"),part,"numFmtId")]=node.get("formatCode","")
 fonts=tuple(Font(node.find("x:name",NS).get("val") if node.find("x:name",NS) is not None else None,_float(node.find("x:sz",NS).get("val") if node.find("x:sz",NS) is not None else None,part,"font-size"),node.find("x:b",NS) is not None,node.find("x:i",NS) is not None,_color(node.find("x:color",NS)),_attrs(node),_elements(node)) for node in root.findall("x:fonts/x:font",NS))
 fills=tuple(Fill(node.find("x:patternFill",NS).get("patternType") if node.find("x:patternFill",NS) is not None else None,_color(node.find("x:patternFill/x:fgColor",NS)),_color(node.find("x:patternFill/x:bgColor",NS)),_attrs(node),_elements(node)) for node in root.findall("x:fills/x:fill",NS))
 def side(node):return None if node is None else BorderSide(node.get("style"),_color(node.find("x:color",NS)),_attrs(node))
 borders=tuple(Border(side(node.find("x:left",NS)),side(node.find("x:right",NS)),side(node.find("x:top",NS)),side(node.find("x:bottom",NS)),side(node.find("x:diagonal",NS)),_attrs(node),_elements(node)) for node in root.findall("x:borders/x:border",NS))
 styles=[]
 for node in root.findall("x:cellXfs/x:xf",NS):
  num,font,fill,border=(_integer(node.get(key),part,key) for key in ("numFmtId","fontId","fillId","borderId"))
  if font<0 or font>=len(fonts) or fill<0 or fill>=len(fills) or border<0 or border>=len(borders):raise OPCWorkbookError("style-component-index-out-of-range",part,ET.tostring(node,encoding="unicode"))
  semantic=(formats.get(num,f"builtin:{num}"),num,font,fill,border,fonts[font],fills[fill],borders[border],_attrs(node.find("x:alignment",NS)),_attrs(node.find("x:protection",NS)),_attrs(node));styles.append(CellStyle(*semantic,sha256(repr(semantic).encode()).hexdigest()))
 return tuple(styles)
def _strings(raw,part):return () if raw is None else tuple(_text(n) or "" for n in _xml(raw,part).findall("x:si",NS))
def _unsupported(root,part):return tuple(Finding("unsupported-feature",part,name) for name in ("conditionalFormatting","dataValidations","tableParts","drawing","legacyDrawing","extLst","sheetProtection") if root.find(f"x:{name}",NS) is not None)
def _col(coordinate):
 value=0
 for char in "".join(c for c in coordinate if c.isalpha()).upper():value=value*26+ord(char)-64
 return value
def _cell(node,strings,styles,part,effective):
 coordinate=node.get("r")
 if not coordinate:raise OPCWorkbookError("missing-cell-coordinate",part,ET.tostring(node,encoding="unicode"))
 raw,inline,kind=_text(node.find("x:v",NS)),_text(node.find("x:is",NS)),node.get("t");formula_node=node.find("x:f",NS)
 formula=None if formula_node is None else Formula(_text(formula_node) or "",formula_node.get("t"),_integer(formula_node.get("si"),part,coordinate) if formula_node.get("si") is not None else None,formula_node.get("ref"));shared=None;value=raw
 if kind=="s":
  if raw is None:raise OPCWorkbookError("missing-shared-string-index",part,coordinate)
  shared=_integer(raw,part,coordinate)
  if not 0<=shared<len(strings):raise OPCWorkbookError("shared-string-index-out-of-range",part,coordinate)
  value=strings[shared]
 elif kind=="inlineStr":value=inline
 return Cell(coordinate,kind,raw,value,shared,inline,raw if kind=="e" else None,formula,raw if formula else None,effective,styles[effective].fingerprint if effective is not None else None)
def _worksheet(raw,name,sheet_id,state,part,strings,styles,relationships):
 root=_xml(raw,part)
 cols=tuple(Column(_integer(n.get("min"),part,"col-min"),_integer(n.get("max"),part,"col-max"),_float(n.get("width"),part,"col-width"),_bool(n.get("hidden")),_integer(n.get("outlineLevel"),part,"col-outline"),_style_index(n.get("style"),styles,part,"column-style")) for n in root.findall("x:cols/x:col",NS));rows=[]
 for n in root.findall("x:sheetData/x:row",NS):
  row_style=_style_index(n.get("s"),styles,part,"row-style");cells=[]
  for cell in n.findall("x:c",NS):
   declared=_style_index(cell.get("s"),styles,part,cell.get("r","cell"));column_style=next((c.style_index for c in cols if c.minimum<=_col(cell.get("r",""))<=c.maximum and c.style_index is not None),None);effective=declared if declared is not None else row_style if row_style is not None else column_style if column_style is not None else 0 if styles else None;cells.append(_cell(cell,strings,styles,part,effective))
  rows.append(Row(_integer(n.get("r"),part,"row-index"),_float(n.get("ht"),part,"row-height"),_bool(n.get("hidden")),_integer(n.get("outlineLevel"),part,"row-outline"),row_style,tuple(cells)))
 by_id={r.id:r for r in relationships};links=[]
 for n in root.findall("x:hyperlinks/x:hyperlink",NS):
  ref,ident=n.get("ref"),n.get(f"{{{NS['r']}}}id")
  if not ref:raise OPCWorkbookError("invalid-hyperlink",part,"missing-ref")
  relation=by_id.get(ident) if ident else None
  if ident and (relation is None or relation.type!=REL_HYPERLINK or relation.target_mode!="External"):raise OPCWorkbookError("invalid-hyperlink-relationship",part,ident)
  links.append(Hyperlink(ref,n.get("location"),n.get("display"),n.get("tooltip"),relation))
 dim,auto=root.find("x:dimension",NS),root.find("x:autoFilter",NS)
 return Worksheet(name,sheet_id,state,part,dim.get("ref") if dim is not None else None,tuple(rows),cols,tuple(links),tuple(n.get("ref","") for n in root.findall("x:mergeCells/x:mergeCell",NS)),auto.get("ref") if auto is not None else None,_unsupported(root,part))
def read_opc_workbook(path):
 with ZipFile(path) as archive:
  parts={}
  for member in archive.infolist():
   name=_normal_part(member.filename,member.filename)
   if name in parts:raise OPCWorkbookError("duplicate-normalized-part",name,member.filename)
   parts[name]=archive.read(member)
 if "[Content_Types].xml" not in parts or "_rels/.rels" not in parts:raise OPCWorkbookError("missing-opc-root","","[Content_Types].xml or _rels/.rels")
 content=_content_types(parts["[Content_Types].xml"]);package=_relationships(parts["_rels/.rels"],"_rels/.rels","",set(parts),True);office=next((r for r in package if r.type==REL_OFFICE_DOCUMENT),None)
 if office is None or office.resolved_target is None:raise OPCWorkbookError("missing-office-document","_rels/.rels","officeDocument")
 workbook_part=office.resolved_target;workbook_rels=str(PurePosixPath(workbook_part).parent/"_rels"/f"{PurePosixPath(workbook_part).name}.rels")
 if workbook_rels not in parts:raise OPCWorkbookError("missing-workbook-relationships",workbook_part,workbook_rels)
 rels=_relationships(parts[workbook_rels],workbook_rels,workbook_part,set(parts));by_id={r.id:r for r in rels};strings_rel=next((r for r in rels if r.type==REL_SHARED_STRINGS),None);styles_rel=next((r for r in rels if r.type==REL_STYLES),None);strings=_strings(parts[strings_rel.resolved_target],strings_rel.resolved_target) if strings_rel and strings_rel.resolved_target else ();styles=_styles(parts[styles_rel.resolved_target],styles_rel.resolved_target) if styles_rel and styles_rel.resolved_target else ();workbook=_xml(parts[workbook_part],workbook_part);sheets=[]
 for n in workbook.findall("x:sheets/x:sheet",NS):
  ident=n.get(f"{{{NS['r']}}}id");relation=by_id.get(ident)
  if relation is None or relation.type!=REL_WORKSHEET or relation.resolved_target is None:raise OPCWorkbookError("invalid-sheet-relationship",workbook_part,ident or "")
  part=relation.resolved_target;rel_part=str(PurePosixPath(part).parent/"_rels"/f"{PurePosixPath(part).name}.rels");sheet_rels=_relationships(parts[rel_part],rel_part,part,set(parts)) if rel_part in parts else ();sheets.append(_worksheet(parts[part],n.get("name",""),_integer(n.get("sheetId"),workbook_part,"sheetId"),n.get("state","visible"),part,strings,styles,sheet_rels))
 names=tuple(DefinedName(n.get("name",""),_text(n) or "",_integer(n.get("localSheetId"),workbook_part,"localSheetId") if n.get("localSheetId") is not None else None,_bool(n.get("hidden"))) for n in workbook.findall("x:definedNames/x:definedName",NS));findings=tuple(f for sheet in sheets for f in sheet.findings)
 return WorkbookModel("opc-workbook-model-v1",content,package,tuple(sheets),names,styles,rels,tuple(sorted((n,sha256(raw).hexdigest()) for n,raw in parts.items())),findings)
read_workbook=read_opc_workbook
