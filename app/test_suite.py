import unittest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, Tenant, Company, Person, DomainEdge, EmploymentEdge, FieldMetadata
from app.resolution import normalize_domain, calculate_string_similarity, resolve_company, resolve_person, calculate_record_confidence
from app.adapters import EnrichmentWaterfallManager
from app.search import search_people_engine, search_companies_engine
from app.main import app

class TestAeroLeadCore(unittest.TestCase):
    def setUp(self):
        # Create an in-memory database for testing
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()
        
        # Seed test tenant
        self.tenant = Tenant(
            tenant_id="test_tenant",
            name="Test Org",
            billing_plan="pro",
            credit_balance=100.0,
            api_key="test_api_key_123"
        )
        self.db.add(self.tenant)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_normalization(self):
        self.assertEqual(normalize_domain("HTTPS://WWW.STRIPE.COM/PAYMENTS"), "stripe.com")
        self.assertEqual(normalize_domain("http://hubspot.com/"), "hubspot.com")
        self.assertEqual(normalize_domain("  acme.com  "), "acme.com")

    def test_string_similarity(self):
        self.assertEqual(calculate_string_similarity("Stripe", "Stripe"), 1.0)
        self.assertGreater(calculate_string_similarity("Acme Inc", "Acme Industries"), 0.3)
        self.assertEqual(calculate_string_similarity("Stripe", "Google"), 0.0)

    def test_entity_resolution_company(self):
        # Resolve company first time (creation)
        payload = {
            "domain": "stripe.com",
            "legal_name": "Stripe, Inc.",
            "industry": "Fintech"
        }
        co1 = resolve_company(self.db, payload, "clearbit")
        self.assertEqual(co1.legal_name, "Stripe, Inc.")
        
        # Resolve company second time with duplicate domain but different name (should merge)
        payload2 = {
            "domain": "stripe.com",
            "legal_name": "Stripe Payments",
            "employee_range": "1000+"
        }
        co2 = resolve_company(self.db, payload2, "pdl")
        self.assertEqual(co1.company_id, co2.company_id)
        self.assertEqual(co2.employee_range, "1000+")
        
        # Verify domain edge was written
        edge = self.db.query(DomainEdge).filter(DomainEdge.company_id == co1.company_id).first()
        self.assertIsNotNone(edge)
        self.assertEqual(edge.domain, "stripe.com")

    def test_field_level_survivorship(self):
        # Resolve company with a manual edit
        payload = {
            "domain": "stripe.com",
            "legal_name": "Stripe, Inc.",
            "industry": "Fintech"
        }
        co = resolve_company(self.db, payload, "manual_verification")
        self.assertEqual(co.industry, "Fintech")
        
        # Try to overwrite with lower confidence source (clearbit)
        payload2 = {
            "domain": "stripe.com",
            "industry": "Payments Software"
        }
        co2 = resolve_company(self.db, payload2, "clearbit")
        # Should NOT overwrite Fintech because existing field source was manual_verification
        self.assertEqual(co2.industry, "Fintech")

    def test_entity_resolution_person(self):
        # Seed company
        resolve_company(self.db, {"domain": "stripe.com", "legal_name": "Stripe Inc"}, "clearbit")
        
        # Resolve person
        payload = {
            "first_name": "John",
            "last_name": "Smith",
            "email": "john.smith@stripe.com",
            "title": "VP of Engineering",
            "company_domain": "stripe.com"
        }
        p1 = resolve_person(self.db, payload, "people_data_labs")
        self.assertEqual(p1.full_name, "John Smith")
        self.assertIsNotNone(p1.company_id)
        
        # Resolve again using name + domain (should match existing)
        payload2 = {
            "first_name": "John",
            "last_name": "Smith",
            "company_domain": "stripe.com",
            "title": "VP of Eng"
        }
        p2 = resolve_person(self.db, payload2, "clearbit")
        self.assertEqual(p1.person_id, p2.person_id)

    def test_confidence_scorecard(self):
        resolve_company(self.db, {"domain": "stripe.com", "legal_name": "Stripe Inc"}, "clearbit")
        p = resolve_person(self.db, {
            "first_name": "John",
            "last_name": "Smith",
            "email": "john.smith@stripe.com",
            "company_domain": "stripe.com",
            "title": "Engineer"
        }, "people_data_labs")
        
        # Calculate confidence
        score = calculate_record_confidence(self.db, "person", p.person_id, key_match_strength=1.0)
        self.assertGreaterEqual(score, 0.5)
        self.assertLessEqual(score, 1.0)

    def test_faceted_search(self):
        # Seed data
        co = resolve_company(self.db, {
            "domain": "acme.com", 
            "legal_name": "Acme Inc",
            "hq_country": "United States",
            "employee_range": "201-500",
            "industry": "Software"
        }, "clearbit")
        resolve_person(self.db, {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@acme.com",
            "title": "Director of Marketing Operations",
            "seniority": "director",
            "company_domain": "acme.com"
        }, "people_data_labs")
        
        # Search Query
        search_payload = {
            "query": "director",
            "filters": {
                "company_locations": ["United States"],
                "seniorities": ["director"]
            }
        }
        results = search_people_engine(self.db, search_payload)
        
        self.assertEqual(len(results["data"]), 1)
        self.assertEqual(results["data"][0]["person"]["full_name"], "Jane Doe")
        self.assertIn("United States", results["facets"]["company_locations"])
        self.assertIn("director", results["facets"]["seniorities"])

    def test_company_search(self):
        # Seed company
        resolve_company(self.db, {
            "domain": "stripe.com",
            "legal_name": "Stripe Inc",
            "hq_country": "United States",
            "employee_range": "1000+",
            "revenue_range": "$1B+",
            "industry": "Fintech",
            "technologies": ["AWS", "React"]
        }, "clearbit")
        
        # Query company search
        search_payload = {
            "query": "Stripe",
            "filters": {
                "company_locations": ["United States"],
                "employee_ranges": ["1000+"],
                "technologies_any": ["React"]
            }
        }
        results = search_companies_engine(self.db, search_payload)
        self.assertEqual(len(results["data"]), 1)
        self.assertEqual(results["data"][0]["legal_name"], "Stripe Inc")
        self.assertIn("Fintech", results["facets"]["industries"])
        self.assertIn("United States", results["facets"]["company_locations"])


class TestAeroLeadAPIRoutes(unittest.TestCase):
    def setUp(self):
        self.client_ctx = TestClient(app)
        self.client = self.client_ctx.__enter__()
        
    def tearDown(self):
        self.client_ctx.__exit__(None, None, None)
        
    def test_api_unauthorized(self):
        # Missing header
        res = self.client.post("/v1/search/people", json={})
        self.assertEqual(res.status_code, 401)
        
        # Invalid key
        res = self.client.post("/v1/search/people", headers={"X-API-Key": "invalid_key"}, json={})
        self.assertEqual(res.status_code, 401)

    def test_api_search_and_enrich(self):
        # Use seeded pro key from main.py startup ('apyl_hubspot_pro_abcdef')
        headers = {"X-API-Key": "apyl_hubspot_pro_abcdef"}
        
        # Search Call
        res = self.client.post("/v1/search/people", headers=headers, json={"query": "Jane"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("data", data)
        self.assertIn("facets", data)
        
        # Enrich Call
        enrich_res = self.client.post("/v1/enrich/person", headers=headers, json={
            "input": {
                "full_name": "John Smith",
                "company_domain": "stripe.com"
            }
        })
        self.assertEqual(enrich_res.status_code, 200)
        enrich_data = enrich_res.json()
        self.assertTrue(enrich_data["match"]["matched"])
        self.assertEqual(enrich_data["person"]["full_name"], "John Smith")
        
        # Fetch lead profile Call
        lead_id = enrich_data["person"]["person_id"].replace("pr_", "ld_")
        lead_res = self.client.get(f"/v1/leads/{lead_id}", headers=headers)
        self.assertEqual(lead_res.status_code, 200)
        lead_data = lead_res.json()
        self.assertEqual(lead_data["lead_id"], lead_id)
        self.assertIn("crm_links", lead_data)
        self.assertIn("signals", lead_data)

if __name__ == "__main__":
    unittest.main()
