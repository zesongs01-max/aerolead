import os
import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.config import PROVIDER_QUALITY
from app.database import (
    init_db, SessionLocal, Tenant, User, Company, Person,
    DomainEdge, EmploymentEdge, TechEdge, FieldMetadata, CRMSync
)
from app.routes import api, web

app = FastAPI(
    title="Apollo-Like Lead Intelligence Platform",
    description="Multi-tenant B2B Lead-Intelligence SaaS MVP with Enrichment Waterfall and Custom Search Engine",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api.router)
app.include_router(web.router)

# Serve Frontend static assets
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
os.makedirs(static_dir, exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    try:
        # Read index.html synchronously to prevent thread deadlocks under ASGI-to-WSGI wrappers on PythonAnywhere
        with open(os.path.join(static_dir, "index.html"), "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        return HTMLResponse(content=f"Error loading index.html: {str(e)}", status_code=500)

# Seeding Logic
def seed_database(db: Session):
    # Check if already seeded
    if db.query(Tenant).first():
        return
        
    print("Seeding database...")
    
    # 1. Create Tenants
    tenants = [
        Tenant(tenant_id="tenant_1", name="Acme Org", billing_plan="starter", credit_balance=45.5, api_key="apyl_acme_starter_12345", seat_count=2),
        Tenant(tenant_id="tenant_2", name="Stripe Devs", billing_plan="growth", credit_balance=320.0, api_key="apyl_stripe_growth_67890", seat_count=5),
        Tenant(tenant_id="tenant_3", name="HubSpot Partners", billing_plan="pro", credit_balance=1450.0, api_key="apyl_hubspot_pro_abcdef", seat_count=10)
    ]
    for t in tenants:
        db.add(t)
    db.commit()

    # 2. Seed CRM Sync configurations
    crm_syncs = [
        CRMSync(
            sync_id="syn_hubspot_t3",
            tenant_id="tenant_3",
            crm_type="hubspot",
            is_active=True,
            conflict_policy="preserve",
            field_mapping={
                "first_name": "firstname",
                "last_name": "lastname",
                "email": "email",
                "title": "jobtitle",
                "company_name": "company",
                "linkedin_url": "linkedin_profile_url"
            },
            last_sync_at=datetime.datetime.utcnow() - datetime.timedelta(hours=2),
            sync_logs=[
                {
                    "timestamp": (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat() + "Z",
                    "synced_leads": 12,
                    "status": "success",
                    "conflicts_resolved": 2
                }
            ]
        ),
        CRMSync(
            sync_id="syn_salesforce_t2",
            tenant_id="tenant_2",
            crm_type="salesforce",
            is_active=False,
            conflict_policy="overwrite",
            field_mapping={
                "first_name": "FirstName",
                "last_name": "LastName",
                "email": "Email",
                "title": "Title",
                "company_name": "Company"
            }
        )
    ]
    for s in crm_syncs:
        db.add(s)
    db.commit()

    # 3. Create Companies
    companies = [
        Company(
            company_id="co_101",
            legal_name="Stripe, Inc.",
            display_name="Stripe",
            domain="stripe.com",
            website_url="https://stripe.com",
            linkedin_url="https://linkedin.com/company/stripe",
            hq_country="United States",
            hq_state="California",
            hq_city="South San Francisco",
            employee_range="5001-10000",
            revenue_range="$1B+",
            industry="Financial Services",
            sub_industry="Payments",
            founded_year=2010,
            public_private="private",
            funding_stage="series_i",
            technologies=["AWS", "React", "Ruby on Rails", "PostgreSQL", "Segment", "HubSpot", "Datadog"],
            confidence_score=0.92
        ),
        Company(
            company_id="co_102",
            legal_name="HubSpot, Inc.",
            display_name="HubSpot",
            domain="hubspot.com",
            website_url="https://hubspot.com",
            linkedin_url="https://linkedin.com/company/hubspot",
            hq_country="United States",
            hq_state="Massachusetts",
            hq_city="Cambridge",
            employee_range="5001-10000",
            revenue_range="$500M-$1B",
            industry="Software",
            sub_industry="CRM & Marketing Automation",
            founded_year=2006,
            public_private="public",
            funding_stage="ipo",
            technologies=["AWS", "React", "Java", "MySQL", "Google Analytics", "Salesforce", "Amplitude"],
            confidence_score=0.95
        ),
        Company(
            company_id="co_103",
            legal_name="Acme Industries Ltd.",
            display_name="Acme Inc",
            domain="acme.com",
            website_url="https://acme.com",
            linkedin_url="https://linkedin.com/company/acme",
            hq_country="United States",
            hq_state="New York",
            hq_city="New York City",
            employee_range="201-500",
            revenue_range="$50M-$100M",
            industry="Manufacturing",
            sub_industry="Industrial Equipment",
            founded_year=1995,
            public_private="private",
            funding_stage="growth",
            technologies=["Salesforce", "WordPress", "HubSpot", "Shopify", "Google Workspace"],
            confidence_score=0.88
        ),
        Company(
            company_id="co_104",
            legal_name="Revolut Ltd",
            display_name="Revolut",
            domain="revolut.com",
            website_url="https://revolut.com",
            linkedin_url="https://linkedin.com/company/revolut",
            hq_country="United Kingdom",
            hq_state="London",
            hq_city="London",
            employee_range="5001-10000",
            revenue_range="$100M-$500M",
            industry="Financial Services",
            sub_industry="Fintech",
            founded_year=2015,
            public_private="private",
            funding_stage="series_e",
            technologies=["AWS", "React", "NodeJS", "Java", "Kubernetes", "Snowflake"],
            confidence_score=0.95
        )
    ]
    for c in companies:
        db.add(c)
    db.commit()

    # Seed Company Domain edges
    for c in companies:
        edge = DomainEdge(company_id=c.company_id, domain=c.domain, is_canonical=True)
        db.add(edge)
        
        # Seed company field level provenance
        fields = ["legal_name", "display_name", "domain", "hq_country", "employee_range", "industry"]
        for f in fields:
            meta = FieldMetadata(
                entity_type="company",
                entity_id=c.company_id,
                field_name=f,
                source="clearbit",
                confidence_score=0.88,
                last_updated_at=datetime.datetime.utcnow()
            )
            db.add(meta)
            
        # Tech edges
        for tech in c.technologies:
            tech_edge = TechEdge(
                company_id=c.company_id,
                tech_slug=tech.lower(),
                category="General Tech",
                confidence=0.80
            )
            db.add(tech_edge)
            
    db.commit()

    # 4. Create People
    people = [
        Person(
            person_id="pr_501",
            company_id="co_103",
            first_name="Jane",
            last_name="Doe",
            full_name="Jane Doe",
            title="Director of Marketing Operations",
            seniority="director",
            department="marketing",
            email="jane.doe@acme.com",
            email_status="verified",
            phone="+1-555-0199",
            phone_status="verified",
            location="New York City, NY",
            linkedin_url="https://www.linkedin.com/in/janedoe",
            confidence_score=0.92
        ),
        Person(
            person_id="pr_502",
            company_id="co_101",
            first_name="John",
            last_name="Smith",
            full_name="John Smith",
            title="VP of Engineering",
            seniority="vp",
            department="engineering",
            email="john.smith@stripe.com",
            email_status="verified",
            phone="+1-555-9080",
            phone_status="verified",
            location="San Francisco, CA",
            linkedin_url="https://www.linkedin.com/in/johnsmith",
            confidence_score=0.94
        ),
        Person(
            person_id="pr_503",
            company_id="co_102",
            first_name="Alice",
            last_name="Jones",
            full_name="Alice Jones",
            title="Sales Operations Specialist",
            seniority="individual_contributor",
            department="sales",
            email="alice.jones@hubspot.com",
            email_status="verified",
            phone="+1-555-4321",
            phone_status="likely_valid",
            location="Boston, MA",
            linkedin_url="https://www.linkedin.com/in/alicejones",
            confidence_score=0.89
        ),
        Person(
            person_id="pr_504",
            company_id="co_104",
            first_name="George",
            last_name="Higgins",
            full_name="George Higgins",
            title="UK Marketing Manager",
            seniority="manager",
            department="marketing",
            email="george.higgins@revolut.com",
            email_status="verified",
            phone="+44-20-7946-0958",
            phone_status="verified",
            location="London, United Kingdom",
            linkedin_url="https://www.linkedin.com/in/georgehiggins",
            confidence_score=0.96
        )
    ]
    for p in people:
        db.add(p)
    db.commit()

    # Seed Employment edges & field metadata
    for p in people:
        employment = EmploymentEdge(
            person_id=p.person_id,
            company_id=p.company_id,
            title=p.title,
            is_current=True
        )
        db.add(employment)
        
        # Field metadata
        fields = ["first_name", "last_name", "full_name", "title", "email", "phone", "linkedin_url"]
        for f in fields:
            meta = FieldMetadata(
                entity_type="person",
                entity_id=p.person_id,
                field_name=f,
                source="people_data_labs",
                confidence_score=0.90,
                last_updated_at=datetime.datetime.utcnow()
            )
            db.add(meta)
    
    db.commit()
    print("Database seeding completed.")

@app.on_event("startup")
def startup_event():
    # Setup folders
    os.makedirs(os.path.dirname(api.__file__), exist_ok=True)
    
    # Initialize database schemas
    init_db()
    
    # Seed data
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
