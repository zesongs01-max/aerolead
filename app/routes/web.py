import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import secrets

from app.database import (
    SessionLocal, Tenant, User, Person, Company,
    SavedList, SavedAudience, CRMSync, AuditLog, FieldMetadata
)
from app.search import search_people_engine, search_companies_engine
from app.adapters import EnrichmentWaterfallManager
from app.config import BILLING_PLANS

router = APIRouter(prefix="/web")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Request Pydantic Models
class CreateListRequest(BaseModel):
    tenant_id: str
    name: str
    type: str  # people, companies

class AddToListRequest(BaseModel):
    list_id: str
    entity_ids: List[str]

class CreateAudienceRequest(BaseModel):
    tenant_id: str
    name: str
    filter_json: Dict[str, Any]

class CRMConfigureRequest(BaseModel):
    tenant_id: str
    crm_type: str  # salesforce, hubspot
    field_mapping: Dict[str, str]
    conflict_policy: str  # preserve, overwrite
    credentials: Optional[Dict[str, str]] = None

class TopupRequest(BaseModel):
    tenant_id: str
    credits: float

class ChangePlanRequest(BaseModel):
    tenant_id: str
    plan: str  # starter, growth, pro

class GenerateApiKeyRequest(BaseModel):
    tenant_id: str

# Endpoints
@router.get("/tenants")
def get_tenants(db: Session = Depends(get_db)):
    """Fetch all tenants to let the user switch between organizations in the UI."""
    return db.query(Tenant).all()

@router.get("/stats/{tenant_id}")
def get_stats(tenant_id: str, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    total_people = db.query(Person).count()
    total_companies = db.query(Company).count()
    total_lists = db.query(SavedList).filter(SavedList.tenant_id == tenant_id).count()
    total_audiences = db.query(SavedAudience).filter(SavedAudience.tenant_id == tenant_id).count()
    
    # Active CRM Sync details
    crm = db.query(CRMSync).filter(CRMSync.tenant_id == tenant_id, CRMSync.is_active == True).first()
    crm_status = f"{crm.crm_type.capitalize()} (Active)" if crm else "Not Connected"
    
    # Audit log counts
    enrich_count = db.query(AuditLog).filter(
        AuditLog.tenant_id == tenant_id,
        AuditLog.action.in_(["enrich_person", "enrich_company", "api_enrich_person"])
    ).count()

    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "billing_plan": tenant.billing_plan,
        "credit_balance": tenant.credit_balance,
        "seat_count": tenant.seat_count,
        "api_key": tenant.api_key,
        "database_metrics": {
            "total_people": total_people,
            "total_companies": total_companies,
            "enrichments_processed": enrich_count,
            "lists_created": total_lists,
            "saved_audiences": total_audiences
        },
        "integrations": {
            "crm_status": crm_status,
            "last_sync": crm.last_sync_at.isoformat() if crm and crm.last_sync_at else None
        }
    }

@router.post("/search/people")
def web_search_people(payload: Dict[str, Any], db: Session = Depends(get_db)):
    # Same engine, no credentials barrier
    return search_people_engine(db, payload)

@router.post("/search/companies")
def web_search_companies(payload: Dict[str, Any], db: Session = Depends(get_db)):
    return search_companies_engine(db, payload)

@router.post("/enrich/person")
def web_enrich_person(payload: Dict[str, Any], db: Session = Depends(get_db)):
    tenant_id = payload.get("tenant_id")
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
        
    if tenant.credit_balance < 1:
        raise HTTPException(402, "Insufficient credits")
        
    waterfall = EnrichmentWaterfallManager()
    resolved = waterfall.enrich_person_waterfall(
        db,
        name=payload.get("full_name"),
        domain=payload.get("company_domain"),
        linkedin_url=payload.get("linkedin_url"),
        email=payload.get("email")
    )
    
    tenant.credit_balance = round(tenant.credit_balance - 1, 2)
    
    # Audit log
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        user_id="web_session",
        action="enrich_person",
        target_type="person",
        target_id=resolved.person_id,
        details=f"Enriched contact: {resolved.full_name}"
    )
    db.add(audit)
    db.commit()
    
    return resolved

@router.post("/enrich/company")
def web_enrich_company(payload: Dict[str, Any], db: Session = Depends(get_db)):
    tenant_id = payload.get("tenant_id")
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
        
    if tenant.credit_balance < 1:
        raise HTTPException(402, "Insufficient credits")
        
    waterfall = EnrichmentWaterfallManager()
    resolved = waterfall.enrich_company_waterfall(db, domain=payload.get("domain"))
    
    tenant.credit_balance = round(tenant.credit_balance - 1, 2)
    
    # Audit log
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        user_id="web_session",
        action="enrich_company",
        target_type="company",
        target_id=resolved.company_id,
        details=f"Enriched company: {resolved.legal_name}"
    )
    db.add(audit)
    db.commit()
    
    return resolved

# Saved Lists endpoints
@router.get("/lists/{tenant_id}")
def get_lists(tenant_id: str, db: Session = Depends(get_db)):
    return db.query(SavedList).filter(SavedList.tenant_id == tenant_id).all()

@router.post("/lists")
def create_list(payload: CreateListRequest, db: Session = Depends(get_db)):
    list_id = f"lst_{db.query(func.count(SavedList.list_id)).scalar() + 201}"
    saved_list = SavedList(
        list_id=list_id,
        tenant_id=payload.tenant_id,
        user_id="web_session",
        name=payload.name,
        type=payload.type,
        entity_ids=[]
    )
    db.add(saved_list)
    db.commit()
    return saved_list

@router.post("/lists/add")
def add_to_list(payload: AddToListRequest, db: Session = Depends(get_db)):
    saved_list = db.query(SavedList).filter(SavedList.list_id == payload.list_id).first()
    if not saved_list:
        raise HTTPException(404, "List not found")
        
    current_ids = set(saved_list.entity_ids or [])
    new_ids = set(payload.entity_ids)
    saved_list.entity_ids = list(current_ids.union(new_ids))
    
    db.commit()
    return {"status": "success", "count": len(saved_list.entity_ids)}

# Saved Audiences
@router.get("/audiences/{tenant_id}")
def get_audiences(tenant_id: str, db: Session = Depends(get_db)):
    return db.query(SavedAudience).filter(SavedAudience.tenant_id == tenant_id).all()

@router.post("/audiences")
def create_audience(payload: CreateAudienceRequest, db: Session = Depends(get_db)):
    aud_id = f"aud_{db.query(func.count(SavedAudience.audience_id)).scalar() + 301}"
    audience = SavedAudience(
        audience_id=aud_id,
        tenant_id=payload.tenant_id,
        user_id="web_session",
        name=payload.name,
        filter_json=payload.filter_json
    )
    db.add(audience)
    db.commit()
    return audience

# CRM Sync Simulator endpoints
@router.get("/crm-sync/{tenant_id}")
def get_crm_sync(tenant_id: str, db: Session = Depends(get_db)):
    return db.query(CRMSync).filter(CRMSync.tenant_id == tenant_id).all()

@router.post("/crm-sync/configure")
def configure_crm(payload: CRMConfigureRequest, db: Session = Depends(get_db)):
    # Find existing CRM sync for this tenant
    sync = db.query(CRMSync).filter(
        CRMSync.tenant_id == payload.tenant_id,
        CRMSync.crm_type == payload.crm_type
    ).first()
    
    if not sync:
        sync_id = f"syn_{db.query(func.count(CRMSync.sync_id)).scalar() + 401}"
        sync = CRMSync(
            sync_id=sync_id,
            tenant_id=payload.tenant_id,
            crm_type=payload.crm_type,
            is_active=True,
            field_mapping=payload.field_mapping,
            conflict_policy=payload.conflict_policy,
            credentials=payload.credentials or {"token": "mock-token-1234"},
            sync_logs=[]
        )
        db.add(sync)
    else:
        sync.is_active = True
        sync.field_mapping = payload.field_mapping
        sync.conflict_policy = payload.conflict_policy
        if payload.credentials:
            sync.credentials = payload.credentials
            
    db.commit()
    return sync

@router.post("/crm-sync/trigger")
def trigger_crm_sync(payload: Dict[str, str], db: Session = Depends(get_db)):
    tenant_id = payload.get("tenant_id")
    crm_type = payload.get("crm_type")
    
    sync = db.query(CRMSync).filter(
        CRMSync.tenant_id == tenant_id,
        CRMSync.crm_type == crm_type,
        CRMSync.is_active == True
    ).first()
    
    if not sync:
        raise HTTPException(400, f"CRM {crm_type} is not configured or active for this tenant.")

    # Simulate syncing list of leads
    all_people = db.query(Person).all()
    synced_count = len(all_people)
    
    # Generate mock log entry
    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "synced_leads": synced_count,
        "status": "success",
        "conflicts_resolved": int(synced_count * 0.15)  # Simulate 15% conflicts
    }
    
    current_logs = list(sync.sync_logs or [])
    current_logs.insert(0, log_entry)
    sync.sync_logs = current_logs[:10]  # keep last 10
    sync.last_sync_at = datetime.datetime.utcnow()
    
    # Audit log
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant_id,
        user_id="web_session",
        action="crm_sync_trigger",
        target_type="integration",
        details=f"Synced {synced_count} records to {crm_type.capitalize()}. Conflicts resolved: {log_entry['conflicts_resolved']}."
    )
    db.add(audit)
    db.commit()
    
    return {"status": "success", "synced_leads": synced_count, "log": log_entry}

# Billing & Plans
@router.post("/billing/topup")
def topup_credits(payload: TopupRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.tenant_id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
        
    tenant.credit_balance = round(tenant.credit_balance + payload.credits, 2)
    
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=payload.tenant_id,
        user_id="web_session",
        action="billing_topup",
        target_type="billing",
        details=f"Purchased {payload.credits} credits."
    )
    db.add(audit)
    db.commit()
    return tenant

@router.post("/billing/plan")
def change_plan(payload: ChangePlanRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.tenant_id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
        
    if payload.plan not in BILLING_PLANS:
        raise HTTPException(400, "Invalid plan selected")
        
    old_plan = tenant.billing_plan
    tenant.billing_plan = payload.plan
    
    # Reset credits/caps or topup as part of upgrade
    extra_credits = BILLING_PLANS[payload.plan]["monthly_credits"]
    tenant.credit_balance = round(tenant.credit_balance + extra_credits, 2)
    
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=payload.tenant_id,
        user_id="web_session",
        action="billing_change_plan",
        target_type="billing",
        details=f"Upgraded plan from {old_plan} to {payload.plan}. Credited {extra_credits} credits."
    )
    db.add(audit)
    db.commit()
    return tenant

# API Keys generator
@router.post("/api-keys/generate")
def generate_api_key(payload: GenerateApiKeyRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.tenant_id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
        
    # Generate token
    new_key = f"apyl_{secrets.token_hex(20)}"
    tenant.api_key = new_key
    
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=payload.tenant_id,
        user_id="web_session",
        action="api_key_generate",
        target_type="api_key",
        details="Generated new public API Key"
    )
    db.add(audit)
    db.commit()
    return {"api_key": new_key}

# Audit Logs
@router.get("/audit-logs/{tenant_id}")
def get_audit_logs(tenant_id: str, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).order_by(AuditLog.timestamp.desc()).limit(50).all()
    return logs

@router.get("/companies/{company_id}")
def get_company_details(company_id: str, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
        
    employees = db.query(Person).filter(Person.company_id == company_id).all()
    
    from app.database import FieldMetadata
    sources_meta = db.query(FieldMetadata).filter(
        FieldMetadata.entity_type == "company",
        FieldMetadata.entity_id == company_id
    ).all()
    sources = [{"provider": m.source, "field": m.field_name, "confidence": m.confidence_score} for m in sources_meta]
    
    return {
        "company_id": company.company_id,
        "legal_name": company.legal_name,
        "display_name": company.display_name,
        "domain": company.domain,
        "website_url": company.website_url,
        "linkedin_url": company.linkedin_url,
        "hq_country": company.hq_country,
        "hq_state": company.hq_state,
        "hq_city": company.hq_city,
        "employee_range": company.employee_range,
        "revenue_range": company.revenue_range,
        "industry": company.industry,
        "sub_industry": company.sub_industry,
        "founded_year": company.founded_year,
        "public_private": company.public_private,
        "funding_stage": company.funding_stage,
        "technologies": company.technologies or [],
        "confidence_score": company.confidence_score,
        "employees": [
            {
                "person_id": p.person_id,
                "full_name": p.full_name,
                "title": p.title,
                "email": p.email,
                "email_status": p.email_status
            } for p in employees
        ],
        "sources": sources,
        "crm_links": [
            {"system": "salesforce", "record_type": "account", "record_id": "0015w00001Z9abc"},
            {"system": "hubspot", "record_type": "company", "record_id": "87612"}
        ]
    }

@router.get("/leads/{lead_id}")
def web_get_lead_profile(lead_id: str, db: Session = Depends(get_db)):
    # Retrieve person matching lead id
    p_id = lead_id
    if lead_id.startswith("ld_"):
        # Map ld_123 to pr_123
        p_id = f"pr_{lead_id.split('_')[1]}"
        
    person = db.query(Person).filter(Person.person_id == p_id).first()
    if not person:
        raise HTTPException(
            status_code=404,
            detail=f"Lead {lead_id} not found"
        )
        
    comp = person.company
    
    return {
        "lead_id": lead_id,
        "owner_user_id": "usr_101",
        "person": {
            "person_id": person.person_id,
            "full_name": person.full_name,
            "title": person.title,
            "email": person.email,
            "phone": person.phone,
            "linkedin_url": person.linkedin_url,
            "confidence_score": person.confidence_score
        },
        "company": {
            "company_id": comp.company_id if comp else None,
            "name": comp.legal_name if comp else None,
            "domain": comp.domain if comp else None,
            "industry": comp.industry if comp else None,
            "employee_range": comp.employee_range if comp else None,
            "hq_country": comp.hq_country if comp else None
        },
        "crm_links": [
            {"system": "salesforce", "record_type": "lead", "record_id": "00Q5w00001Z9abc"},
            {"system": "hubspot", "record_type": "contact", "record_id": "90812"}
        ],
        "signals": {
            "intent_topics": ["marketing automation", "growth hacking"],
            "website_visits_30d": 4,
            "jobs_related_30d": 2,
            "tech_changes_90d": [
                {"technology": "HubSpot", "change": "installed", "detected_at": datetime.date.today().isoformat()}
            ]
        },
        "timeline": [
            {"type": "enriched", "at": person.last_verified_at.isoformat() + "Z"},
            {"type": "synced_to_crm", "at": (person.last_verified_at + datetime.timedelta(seconds=5)).isoformat() + "Z"}
        ]
    }

