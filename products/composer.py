from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from .capability_catalog import CapabilityCatalog, COMMERCIAL_STATES
from .models import AI_MODES, PLATFORM_TARGETS, PRODUCT_TYPES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _loads(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from", "i", "in", "is", "it",
    "me", "my", "of", "on", "or", "our", "that", "the", "their", "this", "to", "we", "will", "with",
    "want", "need", "needs", "should", "system", "thing", "product", "client", "customer",
}
SYNONYMS = {
    "sales": {"lead", "crm", "outreach", "prospect", "pipeline"},
    "lead": {"sales", "prospect", "research", "enrichment"},
    "research": {"search", "browser", "discover", "analysis"},
    "email": {"mail", "gmail", "outreach", "message"},
    "crm": {"sales", "hubspot", "salesforce", "pipeline"},
    "recruitment": {"recruiting", "candidate", "cv", "resume", "interview", "hr"},
    "hr": {"human", "recruitment", "candidate", "employee"},
    "invoice": {"billing", "finance", "payment", "accounting"},
    "document": {"file", "pdf", "ocr", "extract", "read"},
    "ocr": {"document", "image", "scan", "extract", "read"},
    "automation": {"workflow", "schedule", "trigger", "job"},
    "workflow": {"automation", "process", "steps", "orchestration"},
    "agent": {"employee", "assistant", "worker", "autonomous"},
    "employee": {"agent", "assistant", "worker"},
    "saas": {"web", "subscription", "platform", "app"},
    "integration": {"connector", "api", "sync"},
    "calendar": {"meeting", "schedule", "appointment"},
    "knowledge": {"rag", "search", "documents", "assistant"},
    "browser": {"web", "research", "navigate", "scrape"},
    "valuation": {"appraisal", "property", "real", "estate"},
}
DOMAIN_REQUIREMENTS = (
    ("lead research", ("lead", "prospect", "company research", "decision maker")),
    ("contact enrichment", ("enrich", "email finder", "contact details", "linkedin")),
    ("outreach", ("outreach", "cold email", "personalized email", "send email")),
    ("crm integration", ("crm", "hubspot", "salesforce", "pipedrive")),
    ("calendar scheduling", ("calendar", "appointment", "meeting", "schedule interview")),
    ("reporting", ("report", "dashboard", "weekly summary", "analytics")),
    ("browser research", ("browser", "web research", "browse", "scrape")),
    ("document processing", ("document", "pdf", "docx", "file processing")),
    ("ocr", ("ocr", "scan", "image text", "read image")),
    ("knowledge assistant", ("knowledge", "rag", "internal docs", "knowledge base")),
    ("workflow automation", ("workflow", "automation", "trigger", "scheduled")),
    ("api integration", ("api", "webhook", "connector", "integration")),
    ("database", ("database", "postgres", "sqlite", "mysql", "store records")),
    ("recruitment", ("recruit", "candidate", "resume", "cv", "interview", "ats")),
    ("finance", ("invoice", "billing", "payment", "finance", "accounting")),
    ("customer support", ("support", "ticket", "helpdesk", "customer service")),
    ("property valuation", ("property valuation", "property appraisal", "real estate valuation", "real-estate valuation")),
)


def _tokenize(value: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(token) > 1 and token not in STOP
    }
    expanded = set(tokens)
    for token in tuple(tokens):
        expanded.update(SYNONYMS.get(token, ()))
    return expanded


def _capability_text(capability: dict) -> str:
    return " ".join(
        [
            str(capability.get("name") or ""),
            str(capability.get("description") or ""),
            str(capability.get("capability_type") or ""),
            " ".join(map(str, capability.get("tags") or [])),
            str(capability.get("source_kind") or ""),
            str(capability.get("source_ref") or ""),
        ]
    )


def _score(requirement: str, capability: dict) -> float:
    req = _tokenize(requirement)
    cap = _tokenize(_capability_text(capability))
    if not req or not cap:
        return 0.0
    overlap = len(req & cap)
    precision = overlap / max(1, len(req))
    coverage = overlap / max(1, min(len(cap), len(req) + 3))
    phrase = 0.2 if requirement.casefold() in _capability_text(capability).casefold() else 0.0
    qualified = 0.06 if capability.get("qualification_state") == "qualified" else 0.0
    template = 0.05 if capability.get("capability_type") == "product_template" else 0.0
    return round(min(1.0, precision * 0.62 + coverage * 0.22 + phrase + qualified + template), 4)


def _requirements(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    lower = raw.casefold()
    found: list[str] = []
    for label, patterns in DOMAIN_REQUIREMENTS:
        if any(pattern in lower for pattern in patterns):
            found.append(label)
    clauses = re.split(r"[\n.;]+|\s+(?:and then|then|plus|also)\s+", raw)
    for clause in clauses:
        clean = re.sub(r"\s+", " ", clause).strip(" ,-:\t")
        if len(clean) >= 8 and len(_tokenize(clean)) >= 2:
            found.append(clean[:180])
    if not found:
        found = [raw[:180]]
    unique = []
    seen = set()
    for item in found:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:20]


def _recommend_type(text: str) -> str:
    lower = str(text or "").casefold()
    if any(term in lower for term in ("ai employee", "employee", "worker that", "virtual employee")):
        return "ai_employee"
    if any(term in lower for term in ("agent team", "multi agent", "department")):
        return "agent_team"
    if "agent" in lower or "assistant" in lower:
        return "agent"
    if "automation" in lower:
        return "automation"
    if "workflow" in lower:
        return "workflow"
    if any(term in lower for term in ("saas", "platform", "complete system", "business system", "portal")):
        return "business_system"
    if "integration" in lower or "connector" in lower:
        return "integration"
    if "tool" in lower:
        return "tool"
    return "custom"


class ProductComposer:
    """Compose standalone Product Projects from safe, reusable Vishnu capabilities.

    The composer never exposes Vishnu. It references only catalog capabilities,
    creates a separate Project + Product record, and preserves client isolation.
    """

    def __init__(self, path: Path, catalog: CapabilityCatalog, product_store, project_store):
        self.path = Path(path)
        self.catalog = catalog
        self.product_store = product_store
        self.project_store = project_store
        self.lock = RLock()
        self._init()

    def con(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init(self):
        with self.con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS product_requests(
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    client_name TEXT NOT NULL DEFAULT '',
                    requirement TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    requested_product_type TEXT NOT NULL DEFAULT '',
                    requested_ai_mode TEXT NOT NULL DEFAULT 'disabled',
                    requested_targets_json TEXT NOT NULL DEFAULT '[]',
                    commercial_state TEXT NOT NULL DEFAULT 'client_specific',
                    blueprint_json TEXT NOT NULL DEFAULT '{}',
                    product_id TEXT,
                    project_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS product_request_matches(
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    requirement_text TEXT NOT NULL,
                    capability_id TEXT,
                    score REAL NOT NULL DEFAULT 0,
                    decision TEXT NOT NULL,
                    explanation TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_product_request_matches_request
                    ON product_request_matches(request_id,score DESC);
                CREATE TABLE IF NOT EXISTS product_lineage(
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    source_version TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_product_lineage_product
                    ON product_lineage(product_id,created_at);
                CREATE TABLE IF NOT EXISTS product_commercial_classification(
                    product_id TEXT PRIMARY KEY,
                    commercial_state TEXT NOT NULL DEFAULT 'internal_only',
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                DELETE FROM product_lineage
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM product_lineage
                    GROUP BY product_id,source_kind,source_ref,relation
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_product_lineage_unique
                    ON product_lineage(product_id,source_kind,source_ref,relation);
                """
            )

    @staticmethod
    def _request_row(row):
        if not row:
            return None
        item = dict(row)
        item["requested_targets"] = _loads(item.pop("requested_targets_json"), [])
        item["blueprint"] = _loads(item.pop("blueprint_json"), {})
        return item

    def create_request(
        self,
        *,
        title: str,
        requirement: str,
        client_name: str = "",
        product_type: str = "",
        ai_mode: str = "disabled",
        targets=None,
        commercial_state: str | None = None,
    ):
        title = str(title or "").strip()
        requirement = str(requirement or "").strip()
        client_name = str(client_name or "").strip()
        if not title or not requirement:
            raise ValueError("Request title and requirement are required")
        if product_type and product_type not in PRODUCT_TYPES:
            raise ValueError("Unsupported product type")
        if ai_mode not in AI_MODES:
            raise ValueError("Unsupported AI mode")
        target_values = list(dict.fromkeys(targets or []))
        if any(target not in PLATFORM_TARGETS for target in target_values):
            raise ValueError("Unsupported platform target")
        state = commercial_state or ("client_specific" if client_name else "internal_reusable")
        if state not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        request_id, stamp = str(uuid.uuid4()), _now()
        with self.lock, self.con() as con:
            con.execute(
                """INSERT INTO product_requests(
                   id,title,client_name,requirement,status,requested_product_type,requested_ai_mode,
                   requested_targets_json,commercial_state,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (request_id,title,client_name,requirement,"new",product_type,ai_mode,_json(target_values),state,stamp,stamp),
            )
        return self.get_request(request_id)

    def list_requests(self, status: str = "all", limit: int = 200):
        values = []
        where = ""
        if status != "all":
            where = " WHERE status=?"
            values.append(status)
        values.append(max(1, min(int(limit), 500)))
        with self.con() as con:
            rows = con.execute(f"SELECT * FROM product_requests{where} ORDER BY updated_at DESC LIMIT ?", values).fetchall()
        return [self._request_row(row) for row in rows]

    def get_request(self, request_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_requests WHERE id=?", (request_id,)).fetchone()
        return self._request_row(row)

    def request_matches(self, request_id: str):
        with self.con() as con:
            rows = con.execute("SELECT * FROM product_request_matches WHERE request_id=? ORDER BY score DESC,created_at", (request_id,)).fetchall()
        return [dict(row) for row in rows]

    def analyze(self, request_id: str):
        request = self.get_request(request_id)
        if not request:
            return None
        requirements = _requirements(request["requirement"])
        match_scope = request["client_name"] or "__vishnu_internal__"
        capabilities = self.catalog.list(client_scope=match_scope,reusable_only=True,exportable_only=True,limit=1000)
        analysis = []
        stamp = _now()
        with self.lock, self.con() as con:
            con.execute("DELETE FROM product_request_matches WHERE request_id=?", (request_id,))
            for requirement in requirements:
                scored = sorted(((_score(requirement, cap), cap) for cap in capabilities),key=lambda item:item[0],reverse=True)
                best_score, best = scored[0] if scored else (0.0, None)
                if best_score >= 0.72:
                    decision = "reuse"
                elif best_score >= 0.38:
                    decision = "extend"
                else:
                    decision = "create"
                explanation = (f"Reuse {best['name']}" if decision=="reuse" and best else f"Extend {best['name']} to cover the remaining gap" if decision=="extend" and best else "No sufficiently close reusable capability was found; create a new bounded capability")
                match = {"requirement":requirement,"decision":decision,"score":float(best_score),"capability":best,"explanation":explanation}
                analysis.append(match)
                con.execute("INSERT INTO product_request_matches VALUES(?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),request_id,requirement,best["id"] if best else None,float(best_score),decision,explanation,stamp))

            weights = {"reuse":1.0,"extend":0.5,"create":0.0}
            coverage = round(100*sum(weights[item["decision"]] for item in analysis)/max(1,len(analysis)))
            product_type = request["requested_product_type"] or _recommend_type(request["requirement"])
            targets = request["requested_targets"] or ["web"]
            missing_work = []
            for item in analysis:
                if item["decision"] == "extend":
                    missing_work.append({"kind":"extend","title":f"Extend capability for {item['requirement']}","requirement":item["requirement"],"capability_id":item["capability"]["id"] if item["capability"] else None})
                elif item["decision"] == "create":
                    missing_work.append({"kind":"create","title":f"Build capability for {item['requirement']}","requirement":item["requirement"],"capability_id":None})
            blueprint = {
                "schema":"vishnu.product-blueprint/v1","request_id":request_id,"title":request["title"],"client_name":request["client_name"],
                "recommended_product_type":product_type,"ai_mode":request["requested_ai_mode"],"targets":targets,"commercial_state":request["commercial_state"],
                "coverage_percent":coverage,"reuse_count":sum(1 for item in analysis if item["decision"]=="reuse"),"extend_count":sum(1 for item in analysis if item["decision"]=="extend"),"create_count":sum(1 for item in analysis if item["decision"]=="create"),
                "requirements":analysis,"missing_work":missing_work,"generated_at":stamp,
            }
            con.execute("UPDATE product_requests SET status='analyzed',blueprint_json=?,updated_at=? WHERE id=?",(_json(blueprint),stamp,request_id))
        return self.get_request(request_id)

    def _lineage(self, product_id: str, source_kind: str, source_ref: str, relation: str, *, source_version="", metadata=None):
        with self.lock, self.con() as con:
            con.execute(
                """INSERT INTO product_lineage(id,product_id,source_kind,source_ref,relation,source_version,metadata_json,created_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(product_id,source_kind,source_ref,relation)
                   DO UPDATE SET source_version=excluded.source_version,metadata_json=excluded.metadata_json""",
                (str(uuid.uuid4()),product_id,source_kind,source_ref,relation,str(source_version or ""),_json(metadata or {}),_now()),
            )

    def set_product_classification(self, product_id: str, commercial_state: str, notes: str = ""):
        if commercial_state not in COMMERCIAL_STATES:
            raise ValueError("Unsupported commercial state")
        if not self.product_store.get(product_id):
            return None
        with self.lock, self.con() as con:
            con.execute(
                """INSERT INTO product_commercial_classification(product_id,commercial_state,notes,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(product_id) DO UPDATE SET commercial_state=excluded.commercial_state,notes=excluded.notes,updated_at=excluded.updated_at""",
                (product_id,commercial_state,str(notes or "")[:2000],_now()),
            )
        return self.product_classification(product_id)

    def product_classification(self, product_id: str):
        with self.con() as con:
            row = con.execute("SELECT * FROM product_commercial_classification WHERE product_id=?",(product_id,)).fetchone()
        return dict(row) if row else {"product_id":product_id,"commercial_state":"internal_only","notes":"","updated_at":None}

    def lineage(self, product_id: str):
        with self.con() as con:
            rows = con.execute("SELECT * FROM product_lineage WHERE product_id=? ORDER BY created_at",(product_id,)).fetchall()
        result=[]
        for row in rows:
            item=dict(row);item["metadata"]=_loads(item.pop("metadata_json"),{});result.append(item)
        return result

    def _new_project(self, request: dict, blueprint: dict):
        if self.project_store is None:
            raise RuntimeError("Project workspace is unavailable")
        milestone_client_id="compose"
        tasks=[]
        for item in blueprint.get("missing_work") or []:
            tasks.append({"title":item["title"],"description":f"{item['kind'].title()} the missing Product Project capability for: {item['requirement']}","context_notes":"Created automatically by Our Products Product Composer. Keep client-private data isolated; promote only generalized reusable output.","priority":"high" if item["kind"]=="create" else "medium","owner":"vishnu","milestone_client_id":milestone_client_id})
        tasks.extend([
            {"title":"Integrate selected reusable capabilities","description":"Compose approved reusable capabilities into this Product Project without copying the full Vishnu owner system.","priority":"high","owner":"vishnu","milestone_client_id":milestone_client_id},
            {"title":"Run Product Project qualification","description":"Test component boundaries, permissions, AI/no-AI policy, client isolation and target readiness.","priority":"high","owner":"vishnu","milestone_client_id":milestone_client_id},
            {"title":"Prepare product release","description":"Freeze the qualified version, build selected targets, license/sign where required and prepare client delivery.","priority":"medium","owner":"vishnu","milestone_client_id":milestone_client_id},
        ])
        return self.project_store.create(
            name=request["title"],goal=request["requirement"],description=f"Product Project generated from Our Products request {request['id']}. Client: {request['client_name'] or 'Internal use'}.",project_type="software",
            success_criteria="Deliver a standalone Product Project satisfying the request without exposing Vishnu owner data, private system state or unrelated capabilities.",
            instructions="Reuse qualified capabilities first; extend when partially matched; create only missing pieces. Keep client-private knowledge, secrets and custom logic scoped to this Product Project.",
            context_notes=f"Product Composer coverage: {blueprint.get('coverage_percent',0)}%. Commercial state: {request['commercial_state']}.",
            milestones=[{"client_id":milestone_client_id,"title":"Product composition and qualification","outcome":"A tested, isolated Product Project ready for freeze/build or further owner review.","completion_criteria":"All missing work is complete, reusable dependencies are integrated, qualification passes and client boundaries are verified."}],tasks=tasks,
        )

    def _persist_request_links(self, request_id: str, *, project_id=None, product_id=None, status=None):
        values={"updated_at":_now()}
        if project_id is not None: values["project_id"]=project_id
        if product_id is not None: values["product_id"]=product_id
        if status is not None: values["status"]=status
        with self.lock, self.con() as con:
            con.execute("UPDATE product_requests SET "+",".join(f"{key}=?" for key in values)+" WHERE id=?",(*values.values(),request_id))

    def create_product_project(self, request_id: str):
        request=self.get_request(request_id)
        if not request:return None
        if self.project_store is None:raise RuntimeError("Project workspace is unavailable")
        if not request.get("blueprint"):request=self.analyze(request_id)
        blueprint=request["blueprint"]
        had_product=bool(request.get("product_id"))
        project=self.project_store.get(request["project_id"]) if request.get("project_id") else None
        if project is None:
            project=self._new_project(request,blueprint);self._persist_request_links(request_id,project_id=project["id"],status="project_created");request=self.get_request(request_id)
        product=self.product_store.get(request["product_id"]) if request.get("product_id") else None
        if product is None:product=self.product_store.find_by_source_project(project["id"])
        if product is None:product=self.product_store.create_from_project(project,product_type=blueprint.get("recommended_product_type") or "custom",client_name=request["client_name"])
        self._persist_request_links(request_id,project_id=project["id"],product_id=product["id"],status="product_project_created")
        ai_mode=blueprint.get("ai_mode") or "disabled"
        self.product_store.set_ai_policy(product["id"],{"mode":ai_mode})
        self.product_store.set_targets(product["id"],[{"target":target,"enabled":True,"config":{}} for target in blueprint.get("targets") or ["web"]])
        existing_components=self.product_store.components(product["id"])
        existing_capability_ids={str((component.get("config") or {}).get("capability_id") or component.get("component_ref") or "") for component in existing_components}
        for item in blueprint.get("requirements") or []:
            capability=item.get("capability")
            if not capability or item.get("decision")=="create":continue
            capability_id=str(capability.get("id") or "")
            if capability_id and capability_id not in existing_capability_ids:
                self.product_store.add_component(product["id"],component_type=capability.get("capability_type") or "custom",name=capability.get("name") or item.get("requirement") or "Capability",component_ref=capability_id,config={"capability_id":capability_id,"composer_decision":item.get("decision"),"match_score":item.get("score"),"source_kind":capability.get("source_kind"),"source_ref":capability.get("source_ref")});existing_capability_ids.add(capability_id)
            self._lineage(product["id"],"capability",capability_id,item.get("decision") or "reuse",source_version=str((capability.get("metadata") or {}).get("version") or ""),metadata={"requirement":item.get("requirement"),"score":item.get("score")})
        self.set_product_classification(product["id"],request["commercial_state"],"Created by Product Composer")
        self._lineage(product["id"],"product_request",request_id,"created_from")
        self._lineage(product["id"],"project",project["id"],"implemented_by")
        return {"request":self.get_request(request_id),"product":self.product_store.get(product["id"]),"project":self.project_store.get(project["id"]),"existing":had_product}

    def promote_component(self, *, product_id: str, component_id: str, commercial_state: str="internal_reusable", generalized: bool=False, notes: str=""):
        product=self.product_store.get(product_id);component=self.product_store.component(component_id)
        if not product or not component or component.get("product_id")!=product_id:return None
        if commercial_state not in COMMERCIAL_STATES:raise ValueError("Unsupported commercial state")
        client=str(product.get("client_name") or "").strip();notes=str(notes or "").strip()
        if client and generalized and not notes:raise ValueError("Generalizing a client capability requires notes confirming that client-private data and rules were removed")
        client_scope="shared" if client and generalized else (client or "shared")
        if client and client_scope=="shared" and commercial_state=="client_specific":raise ValueError("Client-specific capability cannot be promoted to shared scope")
        name=str(component.get("name") or "Product capability").strip()
        if client and generalized:name=re.sub(re.escape(client),"",name,flags=re.IGNORECASE).strip(" -·:") or "Reusable product capability"
        return self.catalog.upsert(
            name=name,capability_type=component.get("component_type") or "custom",source_kind="promoted_product_component",source_ref=f"{product_id}:{component_id}",description=notes or f"Promoted from {product.get('name')}",client_scope=client_scope,commercial_state=commercial_state,
            qualification_state="qualified" if product.get("status") in {"qualified","released","live"} else "tested",exportable=True,reusable=True,
            metadata={"product_id":product_id,"component_id":component_id,"generalized":bool(generalized),"client_private_source":bool(client)},preserve_owner_classification=False,
        )

    def summary(self):
        with self.con() as con:
            request_total=con.execute("SELECT count(*) c FROM product_requests").fetchone()["c"]
            open_requests=con.execute("SELECT count(*) c FROM product_requests WHERE status NOT IN ('product_project_created','closed')").fetchone()["c"]
            created=con.execute("SELECT count(*) c FROM product_requests WHERE product_id IS NOT NULL").fetchone()["c"]
        return {"requests":int(request_total),"open_requests":int(open_requests),"product_projects_created":int(created),"capabilities":self.catalog.summary()}
