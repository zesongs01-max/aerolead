import time
import datetime
import re
from sqlalchemy.orm import Session
from app.resolution import resolve_company, resolve_person

# High fidelity mock data database for simulation
MOCK_PROVIDER_DATA = {
    "companies": {
        "stripe.com": {
            "legal_name": "Stripe, Inc.",
            "display_name": "Stripe",
            "domain": "stripe.com",
            "website_url": "https://stripe.com",
            "linkedin_url": "https://linkedin.com/company/stripe",
            "hq_country": "United States",
            "hq_state": "California",
            "hq_city": "South San Francisco",
            "employee_range": "5001-10000",
            "revenue_range": "$1B+",
            "industry": "Financial Services",
            "sub_industry": "Payments",
            "founded_year": 2010,
            "public_private": "private",
            "funding_stage": "series_i",
            "technologies": ["AWS", "React", "Ruby on Rails", "PostgreSQL", "Segment", "HubSpot", "Datadog"]
        },
        "hubspot.com": {
            "legal_name": "HubSpot, Inc.",
            "display_name": "HubSpot",
            "domain": "hubspot.com",
            "website_url": "https://hubspot.com",
            "linkedin_url": "https://linkedin.com/company/hubspot",
            "hq_country": "United States",
            "hq_state": "Massachusetts",
            "hq_city": "Cambridge",
            "employee_range": "5001-10000",
            "revenue_range": "$500M-$1B",
            "industry": "Software",
            "sub_industry": "CRM & Marketing Automation",
            "founded_year": 2006,
            "public_private": "public",
            "funding_stage": "ipo",
            "technologies": ["AWS", "React", "Java", "MySQL", "Google Analytics", "Salesforce", "Amplitude"]
        },
        "acme.com": {
            "legal_name": "Acme Industries Ltd.",
            "display_name": "Acme Inc",
            "domain": "acme.com",
            "website_url": "https://acme.com",
            "linkedin_url": "https://linkedin.com/company/acme",
            "hq_country": "United States",
            "hq_state": "New York",
            "hq_city": "New York City",
            "employee_range": "201-500",
            "revenue_range": "$50M-$100M",
            "industry": "Manufacturing",
            "sub_industry": "Industrial Equipment",
            "founded_year": 1995,
            "public_private": "private",
            "funding_stage": "growth",
            "technologies": ["Salesforce", "WordPress", "HubSpot", "Shopify", "Google Workspace"]
        }
    },
    "people": {
        "jane.doe@acme.com": {
            "first_name": "Jane",
            "last_name": "Doe",
            "full_name": "Jane Doe",
            "email": "jane.doe@acme.com",
            "title": "Director of Marketing Operations",
            "seniority": "director",
            "department": "marketing",
            "linkedin_url": "https://www.linkedin.com/in/janedoe",
            "location": "New York City, NY",
            "phone": "+1-555-0199",
            "phone_status": "verified",
            "company_domain": "acme.com",
            "company_name": "Acme Inc"
        },
        "john.smith@stripe.com": {
            "first_name": "John",
            "last_name": "Smith",
            "full_name": "John Smith",
            "email": "john.smith@stripe.com",
            "title": "VP of Engineering",
            "seniority": "vp",
            "department": "engineering",
            "linkedin_url": "https://www.linkedin.com/in/johnsmith",
            "location": "San Francisco, CA",
            "phone": "+1-555-9080",
            "phone_status": "verified",
            "company_domain": "stripe.com",
            "company_name": "Stripe"
        },
        "alice.jones@hubspot.com": {
            "first_name": "Alice",
            "last_name": "Jones",
            "full_name": "Alice Jones",
            "email": "alice.jones@hubspot.com",
            "title": "Sales Operations Specialist",
            "seniority": "individual_contributor",
            "department": "sales",
            "linkedin_url": "https://www.linkedin.com/in/alicejones",
            "location": "Boston, MA",
            "phone": "+1-555-4321",
            "phone_status": "likely_valid",
            "company_domain": "hubspot.com",
            "company_name": "HubSpot"
        }
    }
}

class BaseProviderAdapter:
    def __init__(self, provider_name: str, has_key: bool = False):
        self.provider_name = provider_name
        self.has_key = has_key

    def get_provider_tag(self) -> str:
        return self.provider_name

class OpenCorporatesAdapter(BaseProviderAdapter):
    def __init__(self):
        super().__init__("open_corporates")

    def fetch_company_legal_data(self, domain: str) -> dict:
        """Simulates querying OpenCorporates for canonical legal registration."""
        # Find matches based on domain matching mock db
        company_data = MOCK_PROVIDER_DATA["companies"].get(domain, {})
        if not company_data:
            return {}
        
        return {
            "legal_name": company_data.get("legal_name"),
            "founded_year": company_data.get("founded_year"),
            "public_private": company_data.get("public_private"),
            "hq_country": company_data.get("hq_country")
        }

class BuiltWithAdapter(BaseProviderAdapter):
    def __init__(self):
        super().__init__("builtwith")

    def fetch_technographics(self, domain: str) -> dict:
        """Simulates BuiltWith technographics lookup."""
        company_data = MOCK_PROVIDER_DATA["companies"].get(domain, {})
        if not company_data:
            return {"technologies": ["Google Workspace", "Cloudflare"]}
        
        return {
            "technologies": company_data.get("technologies", [])
        }

class ClearbitAdapter(BaseProviderAdapter):
    def __init__(self):
        super().__init__("clearbit")

    def fetch_firmographics(self, domain: str) -> dict:
        """Simulates Clearbit firmographic enrichment lookup."""
        company_data = MOCK_PROVIDER_DATA["companies"].get(domain, {})
        if not company_data:
            return {}
        
        return {
            "display_name": company_data.get("display_name"),
            "website_url": company_data.get("website_url"),
            "linkedin_url": company_data.get("linkedin_url"),
            "employee_range": company_data.get("employee_range"),
            "revenue_range": company_data.get("revenue_range"),
            "industry": company_data.get("industry"),
            "sub_industry": company_data.get("sub_industry"),
            "hq_state": company_data.get("hq_state"),
            "hq_city": company_data.get("hq_city"),
            "funding_stage": company_data.get("funding_stage")
        }

class HunterAdapter(BaseProviderAdapter):
    def __init__(self):
        super().__init__("hunter")

    def verify_email(self, email: str) -> dict:
        """Simulates Hunter.io email verification."""
        person_data = MOCK_PROVIDER_DATA["people"].get(email.lower())
        if person_data:
            return {
                "email": email,
                "email_status": "verified"
            }
        
        # Simple heuristic for mock
        if "@" in email:
            domain = email.split("@")[1]
            if domain in ["gmail.com", "yahoo.com"]:
                return {"email": email, "email_status": "likely_valid"}
            else:
                return {"email": email, "email_status": "verified"}
        return {"email": email, "email_status": "unknown"}

    def discover_email(self, first_name: str, last_name: str, domain: str) -> str:
        """Simulates Hunter.io Email Finder."""
        # Check mock database
        for email, p in MOCK_PROVIDER_DATA["people"].items():
            if (p["first_name"].lower() == first_name.lower() and 
                p["last_name"].lower() == last_name.lower() and 
                p["company_domain"].lower() == domain.lower()):
                return email
                
        # Generate default email pattern: first.last@domain
        clean_first = re.sub(r'[^a-zA-Z0-9]', '', first_name.lower())
        clean_last = re.sub(r'[^a-zA-Z0-9]', '', last_name.lower())
        return f"{clean_first}.{clean_last}@{domain.lower()}"

class PeopleDataLabsAdapter(BaseProviderAdapter):
    def __init__(self):
        super().__init__("people_data_labs")

    def enrich_person(self, name: str = None, domain: str = None, linkedin_url: str = None, email: str = None) -> dict:
        """Simulates PDL Person Enrichment lookup."""
        # Match keys
        match = None
        if email:
            match = MOCK_PROVIDER_DATA["people"].get(email.lower())
        
        if not match and linkedin_url:
            for p in MOCK_PROVIDER_DATA["people"].values():
                if p["linkedin_url"] == linkedin_url:
                    match = p
                    break
                    
        if not match and name and domain:
            for p in MOCK_PROVIDER_DATA["people"].values():
                if (p["full_name"].lower() == name.lower() or 
                    (p["first_name"] + " " + p["last_name"]).lower() == name.lower()) and p["company_domain"] == domain:
                    match = p
                    break
                    
        if not match:
            # Generate dummy record to ensure it returns something useful
            first = "Enriched"
            last = "Contact"
            if name:
                parts = name.strip().split()
                if len(parts) > 1:
                    first = parts[0]
                    last = " ".join(parts[1:])
                else:
                    first = name
            
            return {
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}",
                "title": "Strategy Operations Manager",
                "seniority": "manager",
                "department": "operations",
                "linkedin_url": linkedin_url or f"https://www.linkedin.com/in/{first.lower()}{last.lower()}",
                "location": "United States",
                "company_domain": domain or "unknown.com",
                "company_name": domain.split('.')[0].capitalize() if domain else "Unknown Corp"
            }

        return match

# Enrichment Waterfall Manager Orchestrator
class EnrichmentWaterfallManager:
    def __init__(self):
        self.open_corp = OpenCorporatesAdapter()
        self.builtwith = BuiltWithAdapter()
        self.clearbit = ClearbitAdapter()
        self.hunter = HunterAdapter()
        self.pdl = PeopleDataLabsAdapter()

    def enrich_company_waterfall(self, db: Session, domain: str) -> dict:
        """
        Company Enrichment Waterfall:
        1. OpenCorporates/SEC -> Canonical legal name, founded year
        2. BuiltWith/Wappalyzer -> Technographics
        3. Clearbit/PDL -> Firmographics
        """
        # Run adapters in sequence
        # Step 1: Legal
        legal_payload = self.open_corp.fetch_company_legal_data(domain)
        # Step 2: Tech
        tech_payload = self.builtwith.fetch_technographics(domain)
        # Step 3: Firmographics
        firm_payload = self.clearbit.fetch_firmographics(domain)

        # Merge payloads into one consolidated schema
        company_payload = {
            "domain": domain
        }
        
        # Merge legal
        if legal_payload:
            company_payload.update(legal_payload)
            resolve_company(db, company_payload, self.open_corp.get_provider_tag())

        # Merge firmographic
        if firm_payload:
            company_payload.update(firm_payload)
            resolve_company(db, company_payload, self.clearbit.get_provider_tag())

        # Merge tech
        if tech_payload:
            company_payload["technologies"] = tech_payload.get("technologies", [])
            resolve_company(db, company_payload, self.builtwith.get_provider_tag())

        # Pull final record from DB
        from app.database import Company
        final_company = db.query(Company).filter(Company.domain == domain).first()
        return final_company

    def enrich_person_waterfall(self, db: Session, name: str = None, domain: str = None, linkedin_url: str = None, email: str = None) -> dict:
        """
        Person Enrichment Waterfall:
        1. PDL -> Person attributes & company linkage
        2. Hunter -> Verify/Find Email contact details
        3. Company Waterfall -> Enrich company details for context
        """
        # Step 1: Ingest Person attributes from PDL
        pdl_payload = self.pdl.enrich_person(name=name, domain=domain, linkedin_url=linkedin_url, email=email)
        
        # Enforce email discovery if email key is missing and we have names + domain
        final_email = email or pdl_payload.get("email")
        if not final_email and pdl_payload.get("first_name") and pdl_payload.get("company_domain"):
            final_email = self.hunter.discover_email(
                pdl_payload["first_name"],
                pdl_payload["last_name"],
                pdl_payload["company_domain"]
            )
            pdl_payload["email"] = final_email

        # Step 2: Verify email using Hunter
        if final_email:
            verification = self.hunter.verify_email(final_email)
            pdl_payload["email_status"] = verification.get("email_status", "unknown")

        # Step 3: Enrich Company context first so person resolution links to rich company
        p_company = None
        c_domain = domain or pdl_payload.get("company_domain")
        if c_domain:
            self.enrich_company_waterfall(db, c_domain)

        # Resolve Person
        resolved_person = resolve_person(db, pdl_payload, self.pdl.get_provider_tag())
        return resolved_person
