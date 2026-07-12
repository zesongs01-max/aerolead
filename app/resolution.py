import datetime
import re
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.config import PROVIDER_QUALITY
from app.database import Company, Person, FieldMetadata, DomainEdge, EmploymentEdge, TechEdge

def normalize_domain(domain: str) -> str:
    if not domain:
        return ""
    domain = domain.lower().strip()
    domain = re.sub(r'^(https?://)?(www\d?\.)?', '', domain)
    domain = domain.split('/')[0]
    return domain

def calculate_string_similarity(s1: str, s2: str) -> float:
    """Simple Jaro-Winkler or Levenshtein approximation for name matching."""
    if not s1 or not s2:
        return 0.0
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    if s1 == s2:
        return 1.0
    
    # Simple token sorting similarity
    tokens1 = set(s1.split())
    tokens2 = set(s2.split())
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    if not union:
        return 0.0
    return len(intersection) / len(union)

def update_field_with_provenance(db: Session, entity_type: str, entity_id: str, field_name: str, value, source_name: str) -> bool:
    """
    Updates a single field on a record based on field-level survivorship rules:
    - Never overwrite 'manual_verification' source unless source_name is 'manual_verification'.
    - Overwrite if the new source has a HIGHER quality score than the current source.
    - Overwrite if the current field is empty/null.
    """
    if value is None or value == "" or value == []:
        return False
        
    source_quality = PROVIDER_QUALITY.get(source_name, 0.3)
    
    # Check if there is existing metadata for this field
    existing_meta = db.query(FieldMetadata).filter(
        FieldMetadata.entity_type == entity_type,
        FieldMetadata.entity_id == entity_id,
        FieldMetadata.field_name == field_name
    ).first()
    
    should_update = False
    
    if not existing_meta:
        # No existing source provenance, create one and approve update
        new_meta = FieldMetadata(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            source=source_name,
            confidence_score=source_quality,
            last_updated_at=datetime.datetime.utcnow()
        )
        db.add(new_meta)
        should_update = True
    else:
        # Existing metadata. Run survivorship logic:
        # 1. Manual verification source always wins
        if existing_meta.source == "manual_verification" and source_name != "manual_verification":
            should_update = False
        # 2. Update if new source has equal or higher confidence, or if value was updated long ago (e.g. stale)
        elif source_quality > existing_meta.confidence_score:
            existing_meta.source = source_name
            existing_meta.confidence_score = source_quality
            existing_meta.last_updated_at = datetime.datetime.utcnow()
            should_update = True
        elif source_quality == existing_meta.confidence_score:
            # Refresh timestamp and update value
            existing_meta.last_updated_at = datetime.datetime.utcnow()
            should_update = True
            
    if should_update:
        # Apply change to actual model
        if entity_type == "company":
            company = db.query(Company).filter(Company.company_id == entity_id).first()
            if company:
                setattr(company, field_name, value)
        elif entity_type == "person":
            person = db.query(Person).filter(Person.person_id == entity_id).first()
            if person:
                setattr(person, field_name, value)
                
    return should_update

def calculate_record_confidence(db: Session, entity_type: str, entity_id: str, key_match_strength: float = 0.5) -> float:
    """
    Scorecard:
    record_confidence = 0.30 * source_quality +
                        0.20 * key_match_strength +
                        0.20 * multi_source_agreement +
                        0.15 * recency +
                        0.10 * graph_consistency +
                        0.05 * manual_verification
    """
    # 1. Source Quality: Average of all active field confidences
    fields_meta = db.query(FieldMetadata).filter(
        FieldMetadata.entity_type == entity_type,
        FieldMetadata.entity_id == entity_id
    ).all()
    
    if not fields_meta:
        return 0.3  # Baseline
        
    source_quality = sum(m.confidence_score for m in fields_meta) / len(fields_meta)
    
    # 2. Multi-source agreement
    # Fraction of fields that have been confirmed by more than 1 source (mocked or tracked)
    unique_sources = set(m.source for m in fields_meta)
    multi_source_agreement = 0.5
    if len(unique_sources) > 1:
        multi_source_agreement = min(1.0, 0.5 + (len(unique_sources) * 0.1))
        
    # 3. Recency
    # Calculation based on newest field metadata update
    newest_update = max(m.last_updated_at for m in fields_meta)
    delta_days = (datetime.datetime.utcnow() - newest_update).days
    if delta_days <= 30:
        recency = 1.0
    elif delta_days <= 90:
        recency = 0.8
    else:
        recency = 0.5
        
    # 4. Graph consistency
    graph_consistency = 0.5
    if entity_type == "person":
        person = db.query(Person).filter(Person.person_id == entity_id).first()
        if person and person.company:
            p_domain = normalize_domain(person.email.split('@')[1]) if person.email and '@' in person.email else ""
            c_domain = normalize_domain(person.company.domain) if person.company else ""
            if p_domain and c_domain and p_domain == c_domain:
                graph_consistency = 1.0
    elif entity_type == "company":
        company = db.query(Company).filter(Company.company_id == entity_id).first()
        if company:
            # Check if domain edges align
            canon_edges = [e for e in company.domain_edges if e.is_canonical]
            if canon_edges and normalize_domain(canon_edges[0].domain) == normalize_domain(company.domain):
                graph_consistency = 1.0

    # 5. Manual Verification flag
    manual_verification = 1.0 if any(m.source == "manual_verification" for m in fields_meta) else 0.0
    
    # Calculate Score
    score = (
        0.30 * source_quality +
        0.20 * key_match_strength +
        0.20 * multi_source_agreement +
        0.15 * recency +
        0.10 * graph_consistency +
        0.05 * manual_verification
    )
    return round(min(1.0, max(0.0, score)), 2)

def resolve_company(db: Session, payload: dict, source_name: str) -> Company:
    """
    Finds or creates a Company entity based on deterministic and probabilistic rules.
    1. Deterministic match on domain or legal_name/registry_id.
    2. Overwrites fields following survivorship.
    """
    domain = normalize_domain(payload.get("domain", ""))
    legal_name = payload.get("legal_name", "")
    
    company = None
    key_match_strength = 0.5
    
    if domain:
        # Check domain edge table for canonical or alternate matches
        edge = db.query(DomainEdge).filter(DomainEdge.domain == domain).first()
        if edge:
            company = db.query(Company).filter(Company.company_id == edge.company_id).first()
            key_match_strength = 1.0
            
    if not company and legal_name:
        # Check exact legal name
        company = db.query(Company).filter(func.lower(Company.legal_name) == legal_name.lower()).first()
        if company:
            key_match_strength = 0.9

    if not company:
        # Create new company
        company_id = f"co_{db.query(func.count(Company.company_id)).scalar() + 101}"
        company = Company(
            company_id=company_id,
            legal_name=legal_name or payload.get("display_name", "Unknown Corp"),
            domain=domain or "unknown.com"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        
        # Write canonical domain edge
        if domain:
            edge = DomainEdge(company_id=company.company_id, domain=domain, is_canonical=True)
            db.add(edge)
            db.commit()
            
    # Apply fields with field-level survivorship
    fields_to_update = [
        "legal_name", "display_name", "domain", "website_url", "linkedin_url",
        "hq_country", "hq_state", "hq_city", "employee_range", "revenue_range",
        "industry", "sub_industry", "founded_year", "public_private", "funding_stage"
    ]
    for field in fields_to_update:
        if field in payload:
            update_field_with_provenance(db, "company", company.company_id, field, payload[field], source_name)
            
    if "technologies" in payload and payload["technologies"]:
        # Update JSON array of technologies
        current_techs = set(company.technologies or [])
        new_techs = set(payload["technologies"])
        combined_techs = list(current_techs.union(new_techs))
        update_field_with_provenance(db, "company", company.company_id, "technologies", combined_techs, source_name)
        
        # Write individual tech edges
        for tech in payload["technologies"]:
            existing_edge = db.query(TechEdge).filter(
                TechEdge.company_id == company.company_id,
                TechEdge.tech_slug == tech.lower()
            ).first()
            if not existing_edge:
                tech_edge = TechEdge(
                    company_id=company.company_id,
                    tech_slug=tech.lower(),
                    category=payload.get("tech_category", "unknown"),
                    confidence=PROVIDER_QUALITY.get(source_name, 0.8)
                )
                db.add(tech_edge)
        db.commit()

    # Recalculate record confidence score
    company.confidence_score = calculate_record_confidence(db, "company", company.company_id, key_match_strength)
    company.last_verified_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(company)
    return company

def resolve_person(db: Session, payload: dict, source_name: str) -> Person:
    """
    Finds or creates a Person entity based on:
    1. Deterministic match on verified work email or linkedin_url.
    2. Overwrites fields following survivorship.
    """
    email = payload.get("email", "").lower().strip() if payload.get("email") else ""
    linkedin_url = payload.get("linkedin_url", "")
    first_name = payload.get("first_name", "")
    last_name = payload.get("last_name", "")
    full_name = payload.get("full_name") or f"{first_name} {last_name}".strip()
    
    person = None
    key_match_strength = 0.5
    
    if email:
        person = db.query(Person).filter(func.lower(Person.email) == email).first()
        if person:
            key_match_strength = 1.0
            
    if not person and linkedin_url:
        person = db.query(Person).filter(Person.linkedin_url == linkedin_url).first()
        if person:
            key_match_strength = 0.95
            
    if not person and first_name and last_name and payload.get("company_domain"):
        # Match by name and company domain
        norm_dom = normalize_domain(payload.get("company_domain"))
        matching_companies = db.query(Company).filter(Company.domain == norm_dom).all()
        company_ids = [c.company_id for c in matching_companies]
        
        candidates = db.query(Person).filter(
            func.lower(Person.first_name) == first_name.lower(),
            func.lower(Person.last_name) == last_name.lower(),
            Person.company_id.in_(company_ids)
        ).all()
        if candidates:
            person = candidates[0]
            key_match_strength = 0.8

    # Ground Company association first
    company = None
    if payload.get("company"):
        # If payload contains company sub-object/details
        company = resolve_company(db, payload["company"], source_name)
    elif payload.get("company_domain") or payload.get("company_name"):
        company = resolve_company(db, {
            "domain": payload.get("company_domain", ""),
            "legal_name": payload.get("company_name", "")
        }, source_name)

    if not person:
        # Create new person
        person_id = f"pr_{db.query(func.count(Person.person_id)).scalar() + 501}"
        person = Person(
            person_id=person_id,
            first_name=first_name or "Unknown",
            last_name=last_name or "Person",
            full_name=full_name or "Unknown Person",
            company_id=company.company_id if company else None
        )
        db.add(person)
        db.commit()
        db.refresh(person)
        
    # Link to company if it was resolved
    if company and person.company_id != company.company_id:
        person.company_id = company.company_id
        db.commit()
        
    # Link employment edge
    if company:
        existing_edge = db.query(EmploymentEdge).filter(
            EmploymentEdge.person_id == person.person_id,
            EmploymentEdge.company_id == company.company_id,
            EmploymentEdge.is_current == True
        ).first()
        if not existing_edge:
            # Terminate old employment edges
            db.query(EmploymentEdge).filter(
                EmploymentEdge.person_id == person.person_id
            ).update({"is_current": False})
            
            employment = EmploymentEdge(
                person_id=person.person_id,
                company_id=company.company_id,
                title=payload.get("title", person.title),
                is_current=True
            )
            db.add(employment)
            db.commit()

    # Update attributes with provenance
    fields_to_update = [
        "first_name", "last_name", "full_name", "title", "seniority",
        "department", "email", "email_status", "phone", "phone_status",
        "location", "linkedin_url"
    ]
    for field in fields_to_update:
        if field in payload:
            update_field_with_provenance(db, "person", person.person_id, field, payload[field], source_name)

    # Recalculate record confidence score
    person.confidence_score = calculate_record_confidence(db, "person", person.person_id, key_match_strength)
    person.last_verified_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(person)
    return person
