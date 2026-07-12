import os

# Database configurations
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key-for-jwt-and-cookies-12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

# Data Provider Quality Weightings (used in confidence score calculation)
PROVIDER_QUALITY = {
    "manual_verification": 1.00,
    "open_corporates": 0.95,
    "sec_edgar": 0.95,
    "people_data_labs": 0.90,
    "clearbit": 0.88,
    "hunter": 0.85,
    "wappalyzer": 0.80,
    "builtwith": 0.80,
    "scraping_fallback": 0.30
}

# Billing Tier Packaging
BILLING_PLANS = {
    "starter": {
        "name": "Starter",
        "price_per_seat": 39,
        "monthly_credits": 100,
        "api_limit_per_month": 500,
        "allowed_features": ["basic_search", "crm_sync"]
    },
    "growth": {
        "name": "Growth",
        "price_per_seat": 79,
        "monthly_credits": 500,
        "api_limit_per_month": 5000,
        "allowed_features": ["basic_search", "crm_sync", "technographics", "saved_audiences"]
    },
    "pro": {
        "name": "Pro",
        "price_per_seat": 119,
        "monthly_credits": 2000,
        "api_limit_per_month": 25000,
        "allowed_features": ["basic_search", "crm_sync", "technographics", "saved_audiences", "advanced_scoring", "public_api"]
    }
}

# Credit Costs for Usage Billing
CREDIT_COSTS = {
    "enrich_person": 1,      # 1 credit per enriched person
    "enrich_company": 1,     # 1 credit per enriched company
    "api_search_hit": 0.1    # 0.1 credit per API search result
}

# Default CRM Mapping Templates
DEFAULT_CRM_MAPPINGS = {
    "salesforce": {
        "lead": {
            "first_name": "FirstName",
            "last_name": "LastName",
            "email": "Email",
            "title": "Title",
            "company_name": "Company",
            "phone": "Phone",
            "hq_country": "Country",
            "linkedin_url": "LinkedIn_Profile_URL__c",
            "confidence_score": "Confidence_Score__c"
        }
    },
    "hubspot": {
        "contact": {
            "first_name": "firstname",
            "last_name": "lastname",
            "email": "email",
            "title": "jobtitle",
            "company_name": "company",
            "phone": "phone",
            "hq_country": "country",
            "linkedin_url": "linkedin_profile_url",
            "confidence_score": "confidence_score"
        }
    }
}
