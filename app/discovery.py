"""
AeroLead Discovery Engine
=========================
Self-hosted company discovery pipeline using pure Python web scraping.
No third-party APIs required.

Pipeline:
  1. search_web()        → Query DuckDuckGo for company URLs
  2. detect_technologies() → Scan each site's HTML for tech fingerprints
  3. extract_contacts()  → Find emails, names, LinkedIn links from site HTML
  4. run_discovery_pipeline() → Full end-to-end: search → filter → save to DB
"""

import re
import time
import uuid
import datetime
import logging
from typing import Optional
from urllib.parse import urlparse, urljoin, quote_plus
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

from sqlalchemy.orm import Session
from app.database import Company, Person, TechEdge, DomainEdge, FieldMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Technology Fingerprint Signatures
# Each entry: (tech_name, category, list_of_html_patterns_to_search)
# If ANY pattern in the list is found in the page HTML, the tech is detected.
# ---------------------------------------------------------------------------
TECH_SIGNATURES = {
    "Shopify": {
        "category": "E-commerce",
        "patterns": [
            "cdn.shopify.com",
            "shopify-section",
            "Shopify.theme",
            "myshopify.com",
            "/shopify/",
            "shopifycloud.com",
        ]
    },
    "Klaviyo": {
        "category": "Email Marketing",
        "patterns": [
            "static.klaviyo.com",
            "klaviyo.com/onsite",
            "klaviyo.js",
            "_learnq",
            "KlaviyoSubscribe",
            "klaviyo_account",
        ]
    },
    "WooCommerce": {
        "category": "E-commerce",
        "patterns": [
            "woocommerce",
            "wc-ajax",
            "woocommerce-cart",
            "WooCommerce",
        ]
    },
    "WordPress": {
        "category": "CMS",
        "patterns": [
            "wp-content/",
            "wp-includes/",
            "/wp-json/",
        ]
    },
    "Mailchimp": {
        "category": "Email Marketing",
        "patterns": [
            "mailchimp.com",
            "mc.us",
            "chimpstatic.com",
            "mailchimp-embed",
        ]
    },
    "HubSpot": {
        "category": "CRM & Marketing",
        "patterns": [
            "js.hs-scripts.com",
            "hubspot.com",
            "hs-analytics",
            "hbspt",
        ]
    },
    "Stripe": {
        "category": "Payments",
        "patterns": [
            "js.stripe.com",
            "stripe.js",
        ]
    },
    "React": {
        "category": "Frontend Framework",
        "patterns": [
            "react.development.js",
            "react.production.min.js",
            "__REACT_DEVTOOLS__",
            "data-reactroot",
        ]
    },
    "Google Analytics": {
        "category": "Analytics",
        "patterns": [
            "google-analytics.com/analytics.js",
            "googletagmanager.com/gtag",
            "ga('create'",
            "gtag('config'",
        ]
    },
    "Zendesk": {
        "category": "Customer Support",
        "patterns": [
            "zopim.com",
            "zendesk.com",
            "zdassets.com",
        ]
    },
    "Magento": {
        "category": "E-commerce",
        "patterns": [
            "mage/",
            "Mage.Cookies",
            "magento",
        ]
    },
    "BigCommerce": {
        "category": "E-commerce",
        "patterns": [
            "bigcommerce.com",
            "bigcommerce",
            "cdn11.bigcommerce.com",
        ]
    },
    "Salesforce": {
        "category": "CRM",
        "patterns": [
            "salesforce.com",
            "force.com",
            "lightning.force.com",
        ]
    },
    "Cloudflare": {
        "category": "CDN & Security",
        "patterns": [
            "cloudflare.com",
            "__cf_bm",
            "cf-ray",
        ]
    },
    "Facebook Pixel": {
        "category": "Advertising",
        "patterns": [
            "connect.facebook.net/en_US/fbevents.js",
            "fbq('init'",
            "facebook-pixel",
        ]
    },
}

# ---------------------------------------------------------------------------
# HTTP Utility
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 10  # seconds


def _fetch_html(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    """
    Fetches the raw HTML of a URL using urllib (no external libraries).
    Returns None on any error.
    """
    try:
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
                "Connection": "keep-alive",
            }
        )
        with urlopen(req, timeout=timeout) as response:
            charset = "utf-8"
            content_type = response.headers.get("Content-Type", "")
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].strip()
            raw_bytes = response.read(500_000)  # max 500KB
            return raw_bytes.decode(charset, errors="replace")
    except (URLError, HTTPError, Exception) as e:
        logger.debug(f"Fetch failed for {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 1: Web Search (DuckDuckGo HTML scraping)
# ---------------------------------------------------------------------------
class _LinkParser(HTMLParser):
    """Minimal HTML parser that extracts <a href> values."""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href:
                self.links.append(href)


def search_web(query: str, location: str = "", max_results: int = 20) -> list:
    """
    Searches DuckDuckGo for company websites matching the query.
    Returns a list of URLs (strings).
    """
    # Build search query
    full_query = query
    if location:
        full_query += f" {location}"
    full_query += " site:.co.uk OR site:.com -site:linkedin.com -site:facebook.com -site:twitter.com -site:youtube.com -site:amazon.com -site:ebay.com"

    encoded = quote_plus(full_query)
    ddg_url = f"https://html.duckduckgo.com/html/?q={encoded}"

    html = _fetch_html(ddg_url, timeout=15)
    if not html:
        logger.warning("DuckDuckGo search failed.")
        return []

    # DuckDuckGo result links are in <a class="result__url"> or redirect links
    # Extract redirect URLs: //duckduckgo.com/l/?uddg=<encoded_url>
    urls = []
    # Pattern 1: uddg= redirect links
    uddg_matches = re.findall(r'uddg=(https?[^&"\']+)', html)
    for raw in uddg_matches:
        from urllib.parse import unquote
        url = unquote(raw)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            # Skip ad/tracker domains
            skip_domains = ["duckduckgo.com", "google.com", "bing.com", "linkedin.com",
                           "facebook.com", "twitter.com", "youtube.com", "amazon.com",
                           "ebay.com", "wikipedia.org", "reddit.com"]
            if not any(skip in parsed.netloc for skip in skip_domains):
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                if base_url not in urls:
                    urls.append(base_url)

    # Pattern 2: result__url class links
    parser = _LinkParser()
    parser.feed(html)
    for link in parser.links:
        if link.startswith("http") and "duckduckgo.com" not in link:
            parsed = urlparse(link)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            if base_url not in urls:
                skip_domains = ["linkedin.com", "facebook.com", "twitter.com",
                               "youtube.com", "amazon.com", "ebay.com", "wikipedia.org",
                               "reddit.com", "instagram.com"]
                if not any(skip in parsed.netloc for skip in skip_domains):
                    urls.append(base_url)

    return urls[:max_results]


# ---------------------------------------------------------------------------
# Step 2: Tech Stack Detector
# ---------------------------------------------------------------------------
def detect_technologies(url: str) -> dict:
    """
    Downloads the homepage HTML of a URL and scans for tech fingerprints.
    Returns a dict: { tech_name: category } for each detected technology.
    """
    html = _fetch_html(url)
    if not html:
        return {}

    html_lower = html.lower()
    detected = {}
    for tech_name, info in TECH_SIGNATURES.items():
        for pattern in info["patterns"]:
            if pattern.lower() in html_lower:
                detected[tech_name] = info["category"]
                break

    return detected


# ---------------------------------------------------------------------------
# Step 3: Contact & Company Info Extractor
# ---------------------------------------------------------------------------
EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'
)
LINKEDIN_PERSON_PATTERN = re.compile(
    r'linkedin\.com/in/([A-Za-z0-9\-_%]+)'
)
LINKEDIN_COMPANY_PATTERN = re.compile(
    r'linkedin\.com/company/([A-Za-z0-9\-_%]+)'
)

# Common junk emails to filter out
EMAIL_BLACKLIST = {
    "example.com", "test.com", "sentry.io", "wixpress.com",
    "shopify.com", "klaviyo.com", "cloudflare.com",
    "w3.org", "schema.org", "google.com", "jquery.com",
}

# Common role-based email prefixes to prefer as contacts
CONTACT_PREFIXES = ["info", "hello", "contact", "sales", "team",
                    "support", "enquiries", "enquiry"]


def _extract_company_name(html: str, domain: str) -> str:
    """Try to extract company name from page title or og:site_name meta tag."""
    og_match = re.search(
        r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if og_match:
        return og_match.group(1).strip()

    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
        # Clean up common suffixes like "| Shop" or "- Official Store"
        for sep in [" | ", " - ", " – ", " · "]:
            if sep in title:
                title = title.split(sep)[0].strip()
        return title

    # Fallback: derive from domain
    return domain.replace("www.", "").split(".")[0].title()


def _extract_country(html: str) -> str:
    """Try to detect country from HTML meta or address tags."""
    patterns = [
        r'"addressCountry"\s*:\s*"([^"]+)"',
        r'addressCountry["\s:]+([A-Z]{2})',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            country_map = {
                "GB": "United Kingdom", "UK": "United Kingdom",
                "US": "United States", "CA": "Canada",
                "AU": "Australia", "DE": "Germany",
                "FR": "France", "NL": "Netherlands",
            }
            return country_map.get(val.upper(), val)
    return ""


def extract_contacts(url: str, extra_pages: bool = True) -> dict:
    """
    Crawls homepage (and optionally /contact, /about pages) of a URL.
    Returns a dict with:
      - company_name: str
      - domain: str
      - emails: list[str]
      - linkedin_people: list[str]
      - linkedin_company: str
      - country: str
      - raw_html_snippet: str (for debugging)
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lstrip("www.")

    all_html = ""

    # Fetch homepage
    home_html = _fetch_html(url) or ""
    all_html += home_html

    if extra_pages:
        # Also check /contact and /about pages
        for suffix in ["/contact", "/contact-us", "/about", "/about-us"]:
            sub_url = f"{parsed.scheme}://{parsed.netloc}{suffix}"
            sub_html = _fetch_html(sub_url, timeout=8) or ""
            all_html += sub_html
            time.sleep(0.3)  # polite delay

    # Extract emails
    raw_emails = EMAIL_PATTERN.findall(all_html)
    emails = []
    seen = set()
    for email in raw_emails:
        email_lower = email.lower()
        email_domain = email_lower.split("@")[-1]
        if email_domain in EMAIL_BLACKLIST:
            continue
        if email_domain.endswith((".js", ".css", ".png", ".jpg", ".gif", ".svg")):
            continue
        if email_lower in seen:
            continue
        seen.add(email_lower)
        emails.append(email)

    # Sort: prefer role-based addresses first
    emails.sort(key=lambda e: (
        0 if any(e.lower().startswith(p) for p in CONTACT_PREFIXES) else 1,
        e
    ))

    # Extract LinkedIn handles
    people_handles = list(set(LINKEDIN_PERSON_PATTERN.findall(all_html)))
    company_matches = LINKEDIN_COMPANY_PATTERN.findall(all_html)
    company_handle = company_matches[0] if company_matches else ""

    return {
        "company_name": _extract_company_name(home_html, domain),
        "domain": domain,
        "emails": emails[:10],   # limit to 10
        "linkedin_people": [f"https://www.linkedin.com/in/{h}" for h in people_handles[:5]],
        "linkedin_company": f"https://www.linkedin.com/company/{company_handle}" if company_handle else "",
        "country": _extract_country(all_html),
        "website_url": url,
    }


# ---------------------------------------------------------------------------
# Step 4: Full Discovery Pipeline — saves results directly to DB
# ---------------------------------------------------------------------------
def run_discovery_pipeline(
    db: Session,
    query: str,
    location: str,
    required_techs: list,
    max_results: int = 20,
    progress_callback=None,
) -> dict:
    """
    Full end-to-end discovery pipeline:
      1. Search DuckDuckGo for companies
      2. Detect tech stack on each site
      3. Filter to only sites matching required_techs
      4. Extract contacts from matching sites
      5. Save new Company + Person records to DB

    Returns a summary dict with discovered companies + contacts.
    """

    def _emit(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    _emit(f"🔍 Searching for: '{query}' in '{location}'...")
    urls = search_web(query, location, max_results=max_results)
    _emit(f"Found {len(urls)} candidate URLs. Scanning tech stacks...")

    discovered = []
    required_lower = [t.lower() for t in required_techs]

    for i, url in enumerate(urls):
        _emit(f"[{i+1}/{len(urls)}] Scanning {url}...")
        time.sleep(0.5)  # polite crawl delay

        techs = detect_technologies(url)
        techs_lower = {k.lower(): v for k, v in techs.items()}

        # Filter: must match ALL required technologies
        if required_lower and not all(t in techs_lower for t in required_lower):
            continue

        _emit(f"  ✅ Tech match! Extracting contacts from {url}...")
        contact_info = extract_contacts(url)

        discovered.append({
            "url": url,
            "technologies": techs,
            "contact_info": contact_info,
        })

    _emit(f"✅ Found {len(discovered)} matching companies. Saving to database...")

    saved_companies = []
    saved_contacts = []

    for item in discovered:
        info = item["contact_info"]
        techs = item["technologies"]
        domain = info["domain"]

        # Skip if company with same domain already exists
        existing = db.query(Company).filter(Company.domain == domain).first()
        if existing:
            _emit(f"  ⏭ Skipping {domain} (already in database)")
            saved_companies.append({"company_id": existing.company_id, "domain": domain,
                                    "legal_name": existing.legal_name, "already_existed": True})
            continue

        # Create new Company record
        company_id = f"co_disc_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            legal_name=info["company_name"],
            display_name=info["company_name"],
            domain=domain,
            website_url=info["website_url"],
            linkedin_url=info["linkedin_company"] or None,
            hq_country=info["country"] or (location if location else None),
            technologies=list(techs.keys()),
            confidence_score=0.75,
        )
        db.add(company)

        # Domain edge
        db.add(DomainEdge(company_id=company_id, domain=domain, is_canonical=True))

        # Tech edges
        for tech_name, category in techs.items():
            db.add(TechEdge(
                company_id=company_id,
                tech_slug=tech_name.lower(),
                category=category,
                confidence=0.85,
            ))

        # Field metadata
        db.add(FieldMetadata(
            entity_type="company",
            entity_id=company_id,
            field_name="domain",
            source="web_discovery",
            confidence_score=0.75,
            last_updated_at=datetime.datetime.utcnow()
        ))

        db.flush()

        # Create Person records for discovered emails
        persons_saved = []
        for idx, email in enumerate(info["emails"][:5]):
            email_domain = email.split("@")[-1]
            if email_domain != domain:
                continue  # only save on-domain emails

            person_id = f"pr_disc_{uuid.uuid4().hex[:8]}"
            prefix = email.split("@")[0]
            # Try to derive a name from email prefix
            name_parts = re.split(r'[._\-]', prefix)
            first = name_parts[0].title() if name_parts else "Contact"
            last = name_parts[1].title() if len(name_parts) > 1 else ""
            full_name = f"{first} {last}".strip()

            # Try to match linkedin profile if available
            linkedin = info["linkedin_people"][idx] if idx < len(info["linkedin_people"]) else None

            person = Person(
                person_id=person_id,
                company_id=company_id,
                first_name=first,
                last_name=last,
                full_name=full_name,
                title="Contact",
                seniority="unknown",
                department="unknown",
                email=email,
                email_status="likely_valid",
                location=info["country"] or location or None,
                linkedin_url=linkedin,
                confidence_score=0.65,
            )
            db.add(person)
            persons_saved.append({
                "full_name": full_name,
                "email": email,
                "linkedin_url": linkedin,
            })

        db.commit()
        _emit(f"  💾 Saved: {info['company_name']} ({domain}) with {len(persons_saved)} contacts")

        saved_companies.append({
            "company_id": company_id,
            "domain": domain,
            "legal_name": info["company_name"],
            "hq_country": info["country"],
            "technologies": list(techs.keys()),
            "website_url": info["website_url"],
            "linkedin_url": info["linkedin_company"],
            "confidence_score": 0.75,
            "contacts": persons_saved,
        })
        saved_contacts.extend(persons_saved)

    _emit(f"🎉 Discovery complete! {len(saved_companies)} companies, {len(saved_contacts)} contacts saved.")

    return {
        "status": "complete",
        "companies_found": len(saved_companies),
        "contacts_found": len(saved_contacts),
        "companies": saved_companies,
    }
