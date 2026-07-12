from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, desc, asc
import json
import re
from app.database import Person, Company, EmploymentEdge, TechEdge

def parse_search_query(query_text: str) -> list:
    if not query_text:
        return []
    # Clean and split
    text = query_text.lower().strip()
    
    # Filter out common filler/stop words
    filler_words = {"people", "person", "companies", "company", "from", "named", "with", "in", "using", "at", "who", "are"}
    
    # Extract keywords
    words = re.findall(r'[a-zA-Z0-9]+', text)
    keywords = [w for w in words if w not in filler_words and len(w) > 1]
    
    if not keywords:
        keywords = [w for w in words if len(w) > 0]
        
    return keywords

def apply_people_search_filters(db: Session, base_query, query_text: str, filters: dict):
    q = base_query
    
    # 1. Text Query (Search names, titles, industries, company names)
    if query_text:
        keywords = parse_search_query(query_text)
        if keywords:
            for kw in keywords:
                kw_filter = or_(
                    Person.full_name.ilike(f"%{kw}%"),
                    Person.title.ilike(f"%{kw}%"),
                    Company.legal_name.ilike(f"%{kw}%"),
                    Company.industry.ilike(f"%{kw}%"),
                    Person.location.ilike(f"%{kw}%"),
                    Company.hq_country.ilike(f"%{kw}%")
                )
                q = q.filter(kw_filter)
        
    # 2. Filters
    # 2a. company_locations
    if "company_locations" in filters and filters["company_locations"]:
        loc_filters = []
        for loc in filters["company_locations"]:
            loc_filters.append(Company.hq_country.ilike(f"%{loc}%"))
            loc_filters.append(Company.hq_state.ilike(f"%{loc}%"))
            loc_filters.append(Company.hq_city.ilike(f"%{loc}%"))
            loc_filters.append(Person.location.ilike(f"%{loc}%"))
        q = q.filter(or_(*loc_filters))
        
    # 2b. employee_ranges
    if "employee_ranges" in filters and filters["employee_ranges"]:
        q = q.filter(Company.employee_range.in_(filters["employee_ranges"]))
        
    # 2c. technologies_any
    if "technologies_any" in filters and filters["technologies_any"]:
        # Query matching tech edges
        tech_subs = db.query(TechEdge.company_id).filter(
            func.lower(TechEdge.tech_slug).in_([t.lower() for t in filters["technologies_any"]])
        )
        q = q.filter(Person.company_id.in_(tech_subs))
        
    # 2d. seniorities
    if "seniorities" in filters and filters["seniorities"]:
        q = q.filter(Person.seniority.in_(filters["seniorities"]))
        
    # 2e. email_status
    if "email_status" in filters and filters["email_status"]:
        q = q.filter(Person.email_status.in_(filters["email_status"]))
        
    # 2f. industries
    if "industries" in filters and filters["industries"]:
        q = q.filter(Company.industry.in_(filters["industries"]))

    # Suppression filter: exclude suppressed by default unless requested
    q = q.filter(Person.is_suppressed == False)
    return q

def search_people_engine(db: Session, search_payload: dict) -> dict:
    """
    Parses OpenSearch-style search DSL and queries SQLite.
    Computes facets and paginated data matching the PDF schema format.
    """
    query_text = search_payload.get("query", "").strip()
    filters = search_payload.get("filters", {})
    sort_rules = search_payload.get("sort", [])
    page = max(1, search_payload.get("page", 1))
    page_size = max(1, search_payload.get("page_size", 25))

    # Base query joining Person and Company
    q = db.query(Person).join(Company, Person.company_id == Company.company_id, isouter=True)
    q = apply_people_search_filters(db, q, query_text, filters)
    
    # Base query for facets (select explicit columns to ensure they are inside the subquery)
    facet_q = db.query(
        Person.person_id,
        Person.seniority,
        Person.email_status,
        Company.hq_country,
        Company.industry
    ).join(Company, Person.company_id == Company.company_id, isouter=True)
    facet_q = apply_people_search_filters(db, facet_q, query_text, filters)

    # 3. Calculate Facets BEFORE sorting & pagination (on the filtered base query)
    facets = calculate_people_facets(db, facet_q.subquery())

    # 4. Sorting
    if sort_rules:
        for rule in sort_rules:
            field = rule.get("field")
            direction = rule.get("direction", "desc")
            
            # Map fields
            order_col = None
            if field in ["lead_score", "score"]:
                order_col = Person.confidence_score
            elif field in ["confidence"]:
                order_col = Person.confidence_score
            elif field == "last_verified_at":
                order_col = Person.last_verified_at
                
            if order_col is not None:
                q = q.order_by(desc(order_col) if direction == "desc" else asc(order_col))
    else:
        # Default sort by confidence score
        q = q.order_by(desc(Person.confidence_score))

    # 5. Pagination
    total_count = q.count()
    offset = (page - 1) * page_size
    people_records = q.offset(offset).limit(page_size).all()
    
    # 6. Format output list matching PDF schema
    data = []
    for p in people_records:
        comp = p.company
        
        # Calculate fit/intent scores
        fit_score = round(p.confidence_score * 0.9, 2)
        intent_score = round(p.confidence_score * 0.85, 2)
        lead_score = round((fit_score + intent_score) / 2.0, 2)
        
        record = {
            "lead_id": f"ld_{p.person_id.split('_')[1]}",
            "person": {
                "person_id": p.person_id,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "full_name": p.full_name,
                "title": p.title,
                "seniority": p.seniority,
                "department": p.department,
                "linkedin_url": p.linkedin_url
            },
            "company": {
                "company_id": comp.company_id if comp else None,
                "name": comp.legal_name if comp else None,
                "domain": comp.domain if comp else None,
                "employee_range": comp.employee_range if comp else None,
                "hq_country": comp.hq_country if comp else None,
                "industry": comp.industry if comp else None,
                "technologies": comp.technologies if comp else []
            },
            "contactability": {
                "work_email": p.email,
                "email_status": p.email_status,
                "phone": p.phone,
                "phone_status": p.phone_status
            },
            "scores": {
                "confidence": p.confidence_score,
                "fit": fit_score,
                "intent": intent_score,
                "lead_score": lead_score
            }
        }
        data.append(record)
        
    return {
        "data": data,
        "facets": facets,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total_estimate": total_count
        }
    }

def calculate_people_facets(db: Session, subquery) -> dict:
    """Runs aggregations to fetch facet counts for filters."""
    # We query distinct counts from the subquery of filtered people
    # Country facets
    countries = db.query(subquery.c.hq_country, func.count(subquery.c.person_id)).group_by(subquery.c.hq_country).all()
    # Seniority facets
    seniorities = db.query(subquery.c.seniority, func.count(subquery.c.person_id)).group_by(subquery.c.seniority).all()
    # Email status facets
    email_status = db.query(subquery.c.email_status, func.count(subquery.c.person_id)).group_by(subquery.c.email_status).all()
    # Industry facets
    industries = db.query(subquery.c.industry, func.count(subquery.c.person_id)).group_by(subquery.c.industry).all()
    
    return {
        "company_locations": {c[0]: c[1] for c in countries if c[0]},
        "seniorities": {s[0]: s[1] for s in seniorities if s[0]},
        "email_status": {e[0]: e[1] for e in email_status if e[0]},
        "industries": {i[0]: i[1] for i in industries if i[0]}
    }

def apply_company_search_filters(db: Session, base_query, query_text: str, filters: dict):
    q = base_query
    
    if query_text:
        keywords = parse_search_query(query_text)
        if keywords:
            for kw in keywords:
                kw_filter = or_(
                    Company.legal_name.ilike(f"%{kw}%"),
                    Company.domain.ilike(f"%{kw}%"),
                    Company.industry.ilike(f"%{kw}%")
                )
                q = q.filter(kw_filter)
        
    if "company_locations" in filters and filters["company_locations"]:
        loc_filters = []
        for loc in filters["company_locations"]:
            loc_filters.append(Company.hq_country.ilike(f"%{loc}%"))
            loc_filters.append(Company.hq_state.ilike(f"%{loc}%"))
            loc_filters.append(Company.hq_city.ilike(f"%{loc}%"))
        q = q.filter(or_(*loc_filters))
        
    if "employee_ranges" in filters and filters["employee_ranges"]:
        q = q.filter(Company.employee_range.in_(filters["employee_ranges"]))
        
    if "revenue_ranges" in filters and filters["revenue_ranges"]:
        q = q.filter(Company.revenue_range.in_(filters["revenue_ranges"]))
        
    if "industries" in filters and filters["industries"]:
        q = q.filter(Company.industry.in_(filters["industries"]))

    if "technologies_any" in filters and filters["technologies_any"]:
        tech_subs = db.query(TechEdge.company_id).filter(
            func.lower(TechEdge.tech_slug).in_([t.lower() for t in filters["technologies_any"]])
        )
        q = q.filter(Company.company_id.in_(tech_subs))
        
    return q

def calculate_company_facets(db: Session, subquery) -> dict:
    """Runs aggregations to fetch facet counts for companies."""
    countries = db.query(subquery.c.hq_country, func.count(subquery.c.company_id)).group_by(subquery.c.hq_country).all()
    employees = db.query(subquery.c.employee_range, func.count(subquery.c.company_id)).group_by(subquery.c.employee_range).all()
    revenues = db.query(subquery.c.revenue_range, func.count(subquery.c.company_id)).group_by(subquery.c.revenue_range).all()
    industries = db.query(subquery.c.industry, func.count(subquery.c.company_id)).group_by(subquery.c.industry).all()
    
    return {
        "company_locations": {c[0]: c[1] for c in countries if c[0]},
        "employee_ranges": {e[0]: e[1] for e in employees if e[0]},
        "revenue_ranges": {r[0]: r[1] for r in revenues if r[0]},
        "industries": {i[0]: i[1] for i in industries if i[0]}
    }

def search_companies_engine(db: Session, search_payload: dict) -> dict:
    """Search engine specifically for Company entities with full faceted aggregations."""
    query_text = search_payload.get("query", "").strip()
    filters = search_payload.get("filters", {})
    page = max(1, search_payload.get("page", 1))
    page_size = max(1, search_payload.get("page_size", 25))

    q = db.query(Company)
    q = apply_company_search_filters(db, q, query_text, filters)
    
    facet_q = db.query(
        Company.company_id,
        Company.hq_country,
        Company.employee_range,
        Company.revenue_range,
        Company.industry
    )
    facet_q = apply_company_search_filters(db, facet_q, query_text, filters)
    facets = calculate_company_facets(db, facet_q.subquery())

    total_count = q.count()
    offset = (page - 1) * page_size
    companies = q.order_by(desc(Company.confidence_score)).offset(offset).limit(page_size).all()
    
    data = []
    for c in companies:
        data.append({
            "company_id": c.company_id,
            "legal_name": c.legal_name,
            "domain": c.domain,
            "website_url": c.website_url,
            "linkedin_url": c.linkedin_url,
            "hq_country": c.hq_country,
            "hq_state": c.hq_state,
            "hq_city": c.hq_city,
            "employee_range": c.employee_range,
            "revenue_range": c.revenue_range,
            "industry": c.industry,
            "technologies": c.technologies or [],
            "confidence_score": c.confidence_score
        })
        
    return {
        "data": data,
        "facets": facets,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total_estimate": total_count
        }
    }
