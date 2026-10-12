from __future__ import annotations

import hashlib, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable

from .models import VishnuBlock, VishnuDocument

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL = re.compile(r"\bhttps?://[^\s<>\"]+", re.I)
MONEY = re.compile(r"(?<!\w)([$€£₹])\s?([0-9][0-9,]*(?:\.\d{1,2})?)\b")
DATE = re.compile(r"\b((?:19|20)\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b")
ORG = re.compile(r"\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,5}\s+(?:Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?|GmbH|AG|PLC|LLP|Technologies|Systems|Group))\b")
PERSON = re.compile(r"\b([A-Z][a-z]+(?:[-'][A-Za-z]+)?\s+[A-Z][a-z]+(?:[-'][A-Za-z]+)?(?:\s+[A-Z][a-z]+)?)\b")
WORKS_FOR = re.compile(r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2})\s+(?:works|worked)\s+(?:at|for)\s+([A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+){0,5})\b")
SIGNED_BY = re.compile(r"\b(?:signed|approved)\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2})\b", re.I)


def _now(): return datetime.now(timezone.utc).isoformat()
def _norm(v): return re.sub(r"\s+", " ", str(v or "").strip()).casefold()
def _eid(kind, value): return "ent_" + hashlib.sha256(f"{kind}\0{_norm(value)}".encode()).hexdigest()[:24]
def _rid(*parts): return "rel_" + hashlib.sha256("\0".join(map(str, parts)).encode()).hexdigest()[:24]


def _entity(kind: str, value: str) -> dict:
    canonical = re.sub(r"\s+", " ", str(value).strip().strip(".,;:()[]{}"))
    normalized = _norm(canonical)
    if kind == "date":
        m = DATE.search(canonical)
        if m:
            try: normalized = datetime(int(m[1]), int(m[2]), int(m[3])).date().isoformat()
            except ValueError: pass
    return {"entity_id": _eid(kind, normalized), "kind": kind, "canonical": canonical, "normalized": normalized}


def extract_entities(text: str) -> list[dict]:
    text = str(text or "")
    out: dict[tuple[str, str], dict] = {}
    def add(kind, value):
        item = _entity(kind, value)
        if len(item["canonical"]) >= 2: out.setdefault((kind, item["normalized"]), item)
    for m in EMAIL.finditer(text): add("email", m[0])
    for m in URL.finditer(text): add("url", m[0].rstrip(".,)"))
    for m in MONEY.finditer(text): add("money", m[1] + m[2].replace(",", ""))
    for m in DATE.finditer(text): add("date", m[0])
    for m in ORG.finditer(text): add("organization", m[1])
    for m in PERSON.finditer(text):
        if m[1].casefold() not in {"invoice no", "purchase order", "project status", "total amount"}: add("person", m[1])
    return list(out.values())


def _value_kind(key: str, value: str) -> str:
    k = _norm(key)
    if EMAIL.fullmatch(value.strip()): return "email"
    if any(x in k for x in ("company", "organization", "organisation", "vendor", "employer")): return "organization"
    if any(x in k for x in ("person", "owner", "assignee", "signer", "contact", "employee", "author")): return "person"
    if any(x in k for x in ("date", "deadline", "due")): return "date"
    if any(x in k for x in ("amount", "total", "price", "cost", "value")): return "money"
    return "value"


class LocalSemanticGraph:
    """Local, scope-isolated semantic graph backed by the existing Vishnu SQLite database."""
    def __init__(self, path: Path):
        self.path, self.lock = Path(path), RLock(); self.path.parent.mkdir(parents=True, exist_ok=True); self._init()
    def _con(self):
        c=sqlite3.connect(self.path, timeout=10); c.row_factory=sqlite3.Row; return c
    def _init(self):
        with self._con() as c: c.executescript("""
        CREATE TABLE IF NOT EXISTS semantic_graph_documents(document_id TEXT,scope_type TEXT,scope_id TEXT,checksum TEXT,title TEXT,indexed_at TEXT,PRIMARY KEY(document_id,scope_type,scope_id));
        CREATE TABLE IF NOT EXISTS semantic_entities(entity_id TEXT,scope_type TEXT,scope_id TEXT,kind TEXT,canonical TEXT,normalized TEXT,metadata_json TEXT DEFAULT '{}',PRIMARY KEY(entity_id,scope_type,scope_id));
        CREATE INDEX IF NOT EXISTS idx_semantic_entity ON semantic_entities(scope_type,scope_id,kind,normalized);
        CREATE TABLE IF NOT EXISTS semantic_mentions(id INTEGER PRIMARY KEY AUTOINCREMENT,entity_id TEXT,scope_type TEXT,scope_id TEXT,document_id TEXT,position INTEGER,title TEXT,source_json TEXT,excerpt TEXT,confidence REAL,UNIQUE(entity_id,scope_type,scope_id,document_id,position,source_json));
        CREATE INDEX IF NOT EXISTS idx_semantic_mention ON semantic_mentions(scope_type,scope_id,entity_id,document_id);
        CREATE TABLE IF NOT EXISTS semantic_relations(relation_id TEXT,scope_type TEXT,scope_id TEXT,subject_id TEXT,predicate TEXT,object_id TEXT,document_id TEXT,position INTEGER,title TEXT,source_json TEXT,confidence REAL,metadata_json TEXT DEFAULT '{}',PRIMARY KEY(relation_id,scope_type,scope_id));
        CREATE INDEX IF NOT EXISTS idx_semantic_rel_s ON semantic_relations(scope_type,scope_id,subject_id,predicate);
        CREATE INDEX IF NOT EXISTS idx_semantic_rel_o ON semantic_relations(scope_type,scope_id,object_id,predicate);
        """)
    def state(self, *, document_id, scope_type, scope_id):
        with self._con() as c: r=c.execute("SELECT * FROM semantic_graph_documents WHERE document_id=? AND scope_type=? AND scope_id=?",(str(document_id),str(scope_type),str(scope_id))).fetchone()
        return dict(r) if r else None
    def _upsert(self,c,e,st,si,metadata=None):
        c.execute("""INSERT INTO semantic_entities(entity_id,scope_type,scope_id,kind,canonical,normalized,metadata_json) VALUES(?,?,?,?,?,?,?) ON CONFLICT(entity_id,scope_type,scope_id) DO UPDATE SET canonical=excluded.canonical,kind=excluded.kind,metadata_json=excluded.metadata_json""",(e["entity_id"],st,si,e["kind"],e["canonical"],e["normalized"],json.dumps(metadata or {},ensure_ascii=False,default=str)))
    def _rel(self,c,st,si,s,p,o,doc,pos,title,source,confidence=1.0,metadata=None):
        p=re.sub(r"[^a-z0-9_]+","_",_norm(p)).strip("_")[:120] or "related_to"; self._upsert(c,s,st,si); self._upsert(c,o,st,si)
        c.execute("""INSERT OR REPLACE INTO semantic_relations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(_rid(st,si,s["entity_id"],p,o["entity_id"],doc,pos),st,si,s["entity_id"],p,o["entity_id"],doc,pos,title,json.dumps(source.compact(),ensure_ascii=False,default=str),float(confidence),json.dumps(metadata or {},ensure_ascii=False,default=str)))
    def index_blocks(self, *, document_id: str, title: str, blocks: Iterable[VishnuBlock], scope_type: str, scope_id: str, checksum: str="") -> dict:
        st,si=str(scope_type).strip(),str(scope_id).strip()
        if not st or not si: raise ValueError("Semantic graph requires explicit scope_type and scope_id")
        doc=_entity("document",document_id); doc["canonical"]=str(title or document_id)
        mentions=relations=0
        with self.lock,self._con() as c:
            c.execute("DELETE FROM semantic_mentions WHERE document_id=? AND scope_type=? AND scope_id=?",(document_id,st,si)); c.execute("DELETE FROM semantic_relations WHERE document_id=? AND scope_type=? AND scope_id=?",(document_id,st,si))
            c.execute("INSERT OR REPLACE INTO semantic_graph_documents VALUES(?,?,?,?,?,?)",(document_id,st,si,str(checksum or ""),str(title or "")[:500],_now())); self._upsert(c,doc,st,si,{"document":True})
            for pos,b in enumerate(blocks):
                text=str(b.text or "").strip()
                if not text: continue
                for e in extract_entities(text):
                    self._upsert(c,e,st,si); c.execute("INSERT OR IGNORE INTO semantic_mentions(entity_id,scope_type,scope_id,document_id,position,title,source_json,excerpt,confidence) VALUES(?,?,?,?,?,?,?,?,?)",(e["entity_id"],st,si,document_id,pos,title,json.dumps(b.source.compact(),ensure_ascii=False,default=str),text[:1000],b.confidence)); mentions+=1
                    self._rel(c,st,si,doc,"mentions",e,document_id,pos,title,b.source,b.confidence or 1.0); relations+=1
                if b.kind in {"key_value","form_field"} and isinstance(b.data,dict):
                    key=str(b.data.get("key") or b.data.get("name") or "field").strip(); value=b.data.get("value")
                    if value is not None and str(value).strip(): self._rel(c,st,si,doc,key,_entity(_value_kind(key,str(value)),str(value)),document_id,pos,title,b.source,b.confidence or 1.0,{"derived_from":b.kind}); relations+=1
                for m in WORKS_FOR.finditer(text): self._rel(c,st,si,_entity("person",m[1]),"works_for",_entity("organization",m[2]),document_id,pos,title,b.source,.9); relations+=1
                for m in SIGNED_BY.finditer(text): self._rel(c,st,si,doc,"signed_or_approved_by",_entity("person",m[1]),document_id,pos,title,b.source,.85); relations+=1
            entities=c.execute("SELECT COUNT(*) FROM semantic_entities WHERE scope_type=? AND scope_id=?",(st,si)).fetchone()[0]
        return {"entities":int(entities),"mentions":mentions,"relations":relations}
    def index_document(self, document: VishnuDocument, *, scope_type: str, scope_id: str, title: str|None=None):
        return self.index_blocks(document_id=document.document_id,title=title or document.filename,blocks=document.blocks,scope_type=scope_type,scope_id=scope_id,checksum=document.sha256)
    def _mentions(self,c,eid,st,si,limit=20):
        rows=c.execute("SELECT document_id,position,title,source_json,excerpt,confidence FROM semantic_mentions WHERE entity_id=? AND scope_type=? AND scope_id=? ORDER BY document_id,position LIMIT ?",(eid,st,si,max(1,min(limit,200)))).fetchall(); out=[]
        for r in rows:
            x=dict(r); x["source"]=json.loads(x.pop("source_json") or "{}"); x["citation"]={"document_id":x["document_id"],"title":x["title"],"position":x["position"],"source":x["source"]}; out.append(x)
        return out
    def _relation(self,r):
        x=dict(r); x["source"]=json.loads(x.pop("source_json") or "{}"); x["metadata"]=json.loads(x.pop("metadata_json") or "{}"); x["citation"]={"document_id":x["document_id"],"title":x["title"],"position":x["position"],"source":x["source"]}; return x
    def query(self, query: str, *, scope_type: str, scope_id: str, limit: int=30) -> dict:
        q=_norm(query)
        if not q: raise ValueError("Semantic query cannot be empty")
        limit=max(1,min(int(limit),100)); like=f"%{q}%"
        with self._con() as c:
            entities=[dict(r) for r in c.execute("SELECT entity_id,kind,canonical,normalized,metadata_json FROM semantic_entities WHERE scope_type=? AND scope_id=? AND (normalized LIKE ? OR lower(canonical) LIKE ?) ORDER BY kind,canonical LIMIT ?",(scope_type,scope_id,like,like,limit)).fetchall()]
            ids=[e["entity_id"] for e in entities]; relations=[]
            if ids:
                marks=",".join("?"*len(ids)); rows=c.execute(f"SELECT r.*,s.canonical subject,s.kind subject_kind,o.canonical object,o.kind object_kind FROM semantic_relations r JOIN semantic_entities s ON s.entity_id=r.subject_id AND s.scope_type=r.scope_type AND s.scope_id=r.scope_id JOIN semantic_entities o ON o.entity_id=r.object_id AND o.scope_type=r.scope_type AND o.scope_id=r.scope_id WHERE r.scope_type=? AND r.scope_id=? AND (r.subject_id IN ({marks}) OR r.object_id IN ({marks})) ORDER BY r.document_id,r.position LIMIT ?",[scope_type,scope_id,*ids,*ids,limit*4]).fetchall(); relations=[self._relation(r) for r in rows]
            for e in entities: e["metadata"]=json.loads(e.pop("metadata_json") or "{}"); e["mentions"]=self._mentions(c,e["entity_id"],scope_type,scope_id,10)
        return {"query":query,"scope_type":scope_type,"scope_id":scope_id,"entities":entities,"relations":relations}
    def cross_document_links(self, *, scope_type: str, scope_id: str, limit: int=100):
        with self._con() as c:
            rows=c.execute("SELECT e.entity_id,e.kind,e.canonical,COUNT(DISTINCT m.document_id) document_count FROM semantic_entities e JOIN semantic_mentions m ON m.entity_id=e.entity_id AND m.scope_type=e.scope_type AND m.scope_id=e.scope_id WHERE e.scope_type=? AND e.scope_id=? GROUP BY e.entity_id,e.kind,e.canonical HAVING COUNT(DISTINCT m.document_id)>1 ORDER BY document_count DESC,e.canonical LIMIT ?",(scope_type,scope_id,max(1,min(limit,200)))).fetchall(); return [{**dict(r),"mentions":self._mentions(c,r["entity_id"],scope_type,scope_id,100)} for r in rows]
    def contradictions(self, *, scope_type: str, scope_id: str, limit: int=100):
        with self._con() as c:
            groups=c.execute("SELECT subject_id,predicate,COUNT(DISTINCT object_id) variants FROM semantic_relations WHERE scope_type=? AND scope_id=? AND predicate!='mentions' GROUP BY subject_id,predicate HAVING COUNT(DISTINCT object_id)>1 ORDER BY variants DESC LIMIT ?",(scope_type,scope_id,max(1,min(limit,200)))).fetchall(); out=[]
            for g in groups:
                s=c.execute("SELECT canonical,kind FROM semantic_entities WHERE entity_id=? AND scope_type=? AND scope_id=?",(g["subject_id"],scope_type,scope_id)).fetchone(); rows=c.execute("SELECT r.*,o.canonical object,o.kind object_kind FROM semantic_relations r JOIN semantic_entities o ON o.entity_id=r.object_id AND o.scope_type=r.scope_type AND o.scope_id=r.scope_id WHERE r.scope_type=? AND r.scope_id=? AND r.subject_id=? AND r.predicate=? ORDER BY r.document_id,r.position",(scope_type,scope_id,g["subject_id"],g["predicate"])).fetchall(); out.append({"subject_id":g["subject_id"],"subject":s["canonical"] if s else g["subject_id"],"subject_kind":s["kind"] if s else None,"predicate":g["predicate"],"variant_count":g["variants"],"variants":[self._relation(r) for r in rows]})
            return out
    def timeline(self, *, scope_type: str, scope_id: str, limit: int=200):
        with self._con() as c: rows=c.execute("SELECT e.entity_id,e.canonical,e.normalized,m.document_id,m.position,m.title,m.source_json,m.excerpt,m.confidence FROM semantic_entities e JOIN semantic_mentions m ON m.entity_id=e.entity_id AND m.scope_type=e.scope_type AND m.scope_id=e.scope_id WHERE e.scope_type=? AND e.scope_id=? AND e.kind='date' ORDER BY e.normalized,m.document_id,m.position LIMIT ?",(scope_type,scope_id,max(1,min(limit,500)))).fetchall()
        out=[]
        for r in rows:
            x=dict(r); x["date"]=x.pop("normalized"); x["source"]=json.loads(x.pop("source_json") or "{}"); x["citation"]={"document_id":x["document_id"],"title":x["title"],"position":x["position"],"source":x["source"]}; out.append(x)
        return out
