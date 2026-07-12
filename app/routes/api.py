import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from app.database import SessionLocal, Tenant, Person, AuditLog, Company
from app.search import search_people_engine
from app.adapters import EnrichmentWaterfallManager
from app.config import CREDIT_COSTS

router = APIRouter(prefix="/v1")

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# API authentication dependency
def verify_api_key(db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)) -> Tenant:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header"
        )
    
    tenant = db.query(Tenant).filter(Tenant.api_key == x_api_key).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
        
    # Check plan permissions for API Access (requires Growth or Pro)
    if tenant.billing_plan not in ["growth", "pro"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public API access is restricted to Growth and Pro tiers. Please upgrade."
        )
        
    return tenant

# Pydantic Schemas for validation
class PeopleSearchFilter(BaseModel):
    company_locations: Optional[List[str]] = None
    employee_ranges: Optional[List[str]] = None
    technologies_any: Optional[List[str]] = None
    intent_topics_any: Optional[List[str]] = None
    seniorities: Optional[List[str]] = None
    email_status: Optional[List[str]] = None
    industries: Optional[List[str]] = None

class SortRule(BaseModel):
    field: str
    direction: str = "desc"

class PeopleSearchRequest(BaseModel):
    query: Optional[str] = ""
    filters: Optional[PeopleSearchFilter] = Field(default_factory=PeopleSearchFilter)
    sort: Optional[List[SortRule]] = Field(default_factory=list)
    page: Optional[int] = 1
    page_size: Optional[int] = 25

class EnrichPersonInput(BaseModel):
    full_name: Optional[str] = None
    company_domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None

class OverwritePolicy(BaseModel):
    manual_fields: Optional[str] = "preserve"  # preserve, overwrite
    verified_contact_fields: Optional[str] = "replace_if_newer"  # replace_if_newer, preserve

class EnrichPersonRequest(BaseModel):
    input: EnrichPersonInput
    overwrite_policy: Optional[OverwritePolicy] = Field(default_factory=OverwritePolicy)


# Endpoints
@router.post("/search/people")
def search_people(
    payload: PeopleSearchRequest,
    tenant: Tenant = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    # Charge API search cost
    cost = CREDIT_COSTS["api_search_hit"]
    if tenant.credit_balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credit balance to perform search."
        )
    
    # Run search
    results = search_people_engine(db, payload.dict())
    
    # Decrement credits
    tenant.credit_balance = round(tenant.credit_balance - cost, 2)
    
    # Log Audit Trail
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant.tenant_id,
        user_id="api_key_auth",
        action="api_search_people",
        target_type="person",
        details=f"Search Query: {payload.query}. Charged {cost} credit."
    )
    db.add(audit)
    db.commit()
    
    return results

@router.post("/enrich/person")
def enrich_person(
    payload: EnrichPersonRequest,
    tenant: Tenant = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    cost = CREDIT_COSTS["enrich_person"]
    if tenant.credit_balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient credit balance to perform enrichment."
        )

    # Instantiate Waterfall manager
    waterfall = EnrichmentWaterfallManager()
    
    # Execute waterfall
    resolved = waterfall.enrich_person_waterfall(
        db,
        name=payload.input.full_name,
        domain=payload.input.company_domain,
        linkedin_url=payload.input.linkedin_url,
        email=payload.input.email
    )
    
    # Deduct credits
    tenant.credit_balance = round(tenant.credit_balance - cost, 2)
    
    # Log Audit
    audit = AuditLog(
        log_id=f"lg_{uuid.uuid4().hex[:16]}",
        tenant_id=tenant.tenant_id,
        user_id="api_key_auth",
        action="api_enrich_person",
        target_type="person",
        target_id=resolved.person_id,
        details=f"Enriched: {resolved.full_name}. Charged {cost} credit."
    )
    db.add(audit)
    db.commit()

    # Form response payload matching PDF page 18-19 schema
    comp = resolved.company
    
    # Fetch field level sources
    from app.database import FieldMetadata
    sources_meta = db.query(FieldMetadata).filter(
        FieldMetadata.entity_type == "person",
        FieldMetadata.entity_id == resolved.person_id
    ).all()
    
    sources = [{"provider": m.source, "field": m.field_name, "confidence": m.confidence_score} for m in sources_meta]

    return {
        "match": {
            "matched": True,
            "match_confidence": resolved.confidence_score,
            "match_reasons": ["email_exact" if payload.input.email and resolved.email == payload.input.email.lower() else "fuzzy_match"]
        },
        "person": {
            "person_id": resolved.person_id,
            "full_name": resolved.full_name,
            "title": resolved.title,
            "job_title_normalized": resolved.title.lower().replace(" ", "_") if resolved.title else "",
            "department": resolved.department,
            "seniority": resolved.seniority,
            "work_email": resolved.email,
            "email_status": resolved.email_status,
            "mobile_phone": resolved.phone,
            "sources": sources
        },
        "company": {
            "company_id": comp.company_id if comp else None,
            "name": comp.legal_name if comp else None,
            "domain": comp.domain if comp else None,
            "industry": comp.industry if comp else None,
            "employee_range": comp.employee_range if comp else None
        }
    }

@router.get("/leads/{lead_id}")
def get_lead_profile(
    lead_id: str,
    tenant: Tenant = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
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
    
    # Mocking CRM links, intent signals and timeline updates as described on page 19 of PDF
    return {
        "lead_id": lead_id,
        "owner_user_id": f"usr_{tenant.tenant_id.split('_')[1]}" if "_" in tenant.tenant_id else "usr_101",
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
