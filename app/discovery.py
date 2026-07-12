"""
AeroLead Discovery Engine
=========================
Self-hosted company discovery pipeline using pure Python web scraping.
No third-party APIs required.

Pipeline:
  1. search_web()          → Query DuckDuckGo + Bing for company URLs
  2. _scan_site_parallel() → Concurrent tech detection (ThreadPoolExecutor)
  3. extract_contacts()    → Find emails, LinkedIn links from site HTML
  4. run_discovery_pipeline() → Full pipeline, saves to DB, no strict filtering
"""

import re
import time
import uuid
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import Optional
from urllib.parse import urlparse, quote_plus, unquote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

from sqlalchemy.orm import Session
from app.database import Company, Person, TechEdge, DomainEdge, FieldMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Technology Fingerprint Signatures
# ---------------------------------------------------------------------------
TECH_SIGNATURES = {
    "Shopify": {
        "category": "E-commerce",
        "patterns": [
            "cdn.shopify.com", "shopify-section", "Shopify.theme",
            "myshopify.com", "shopifycloud.com", "shopify_features",
            "Shopify.shop", "window.Shopify",
        ]
    },
    "Klaviyo": {
        "category": "Email Marketing",
        "patterns": [
            "static.klaviyo.com", "klaviyo.com/onsite", "klaviyo.js",
            "_learnq", "KlaviyoSubscribe", "klaviyo_account",
            "a.klaviyo.com", "klaviyo-form",
        ]
    },
    "WooCommerce": {
        "category": "E-commerce",
        "patterns": [
            "woocommerce", "wc-ajax", "woocommerce-cart",
        ]
    },
    "WordPress": {
        "category": "CMS",
        "patterns": [
            "wp-content/", "wp-includes/", "/wp-json/",
        ]
    },
    "Mailchimp": {
        "category": "Email Marketing",
        "patterns": [
            "mailchimp.com", "chimpstatic.com", "mc.us",
        ]
    },
    "HubSpot": {
        "category": "CRM & Marketing",
        "patterns": [
            "js.hs-scripts.com", "hubspot.com/", "hbspt.forms",
        ]
    },
    "Stripe": {
        "category": "Payments",
        "patterns": [
            "js.stripe.com", "stripe.js",
        ]
    },
    "Google Analytics": {
        "category": "Analytics",
        "patterns": [
            "googletagmanager.com/gtag", "gtag('config'", "google-analytics.com",
        ]
    },
    "Zendesk": {
        "category": "Customer Support",
        "patterns": [
            "zopim.com", "zendesk.com/embeddable_framework", "zdassets.com",
        ]
    },
    "Magento": {
        "category": "E-commerce",
        "patterns": [
            "Mage.Cookies", "magento", "mage/cookies",
        ]
    },
    "BigCommerce": {
        "category": "E-commerce",
        "patterns": [
            "bigcommerce.com", "cdn11.bigcommerce.com",
        ]
    },
    "Facebook Pixel": {
        "category": "Advertising",
        "patterns": [
            "connect.facebook.net/en_US/fbevents.js", "fbq('init'",
        ]
    },
    "TikTok Pixel": {
        "category": "Advertising",
        "patterns": [
            "analytics.tiktok.com", "tiktok-pixel",
        ]
    },
    "Hotjar": {
        "category": "Analytics",
        "patterns": [
            "static.hotjar.com", "hotjar",
        ]
    },
    "Trustpilot": {
        "category": "Reviews",
        "patterns": [
            "trustpilot.com", "widget.trustpilot.com",
        ]
    },
    "Yotpo": {
        "category": "Reviews",
        "patterns": [
            "staticw2.yotpo.com", "yotpo.com",
        ]
    },
}

# ---------------------------------------------------------------------------
# Domains to always skip
# ---------------------------------------------------------------------------
SKIP_DOMAINS = {
    "google.com", "google.co.uk", "google.com.au",
    "bing.com", "yahoo.com", "duckduckgo.com",
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
    "amazon.com", "amazon.co.uk", "ebay.com", "ebay.co.uk",
    "wikipedia.org", "reddit.com", "quora.com",
    "indeed.com", "glassdoor.com", "trustpilot.com",
    "yell.com", "checkatrade.com", "yelp.com",
    "companies.house.gov.uk", "gov.uk", "hmrc.gov.uk",
    "bbc.co.uk", "theguardian.com", "dailymail.co.uk",
}

# ---------------------------------------------------------------------------
# HTTP Utility — 5 second timeout, proper headers
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 6  # seconds — fast fail, don't block the pool


def _fetch_html(url: str, timeout: int = REQUEST_TIMEOUT, max_bytes: int = 300_000) -> Optional[str]:
    """
    Fetches the raw HTML of a URL using urllib.
    Returns None on any error. Reads max_bytes to stay fast.
    """
    try:
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept-Encoding": "identity",  # no compression, simpler parsing
                "Connection": "close",
            }
        )
        with urlopen(req, timeout=timeout) as response:
            charset = "utf-8"
            ct = response.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].strip().split(";")[0]
            raw_bytes = response.read(max_bytes)
            return raw_bytes.decode(charset, errors="replace")
    except Exception as e:
        logger.debug(f"Fetch failed {url}: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 1: Multi-source Web Search
# ---------------------------------------------------------------------------
def _parse_duckduckgo(html: str) -> list:
    """Extract unique base URLs from DuckDuckGo HTML result page."""
    urls = []
    seen = set()

    # Primary: uddg= redirect links (most reliable)
    for raw in re.findall(r'uddg=(https?[^&"\']+)', html):
        url = unquote(raw)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
            domain = parsed.netloc.replace("www.", "")
            if domain not in SKIP_DOMAINS and base not in seen:
                seen.add(base)
                urls.append(base)

    # Secondary: href links from result anchors
    for href in re.findall(r'href="(https?://[^"]+)"', html):
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
            domain = parsed.netloc.replace("www.", "")
            if domain not in SKIP_DOMAINS and base not in seen:
                seen.add(base)
                urls.append(base)

    return urls


def _parse_bing(html: str) -> list:
    """Extract unique base URLs from Bing HTML result page."""
    urls = []
    seen = set()
    for href in re.findall(r'<a[^>]+href="(https?://(?!www\.bing)[^"]+)"', html):
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
            domain = parsed.netloc.replace("www.", "")
            if domain not in SKIP_DOMAINS and base not in seen:
                seen.add(base)
                urls.append(base)
    return urls


def search_web(query: str, location: str = "", max_results: int = 20) -> list:
    """
    Searches DuckDuckGo (+ Bing as fallback) for company websites.
    Returns a deduplicated list of base URLs.
    """
    all_urls = []
    seen = set()

    # Build search strings
    q_parts = [query]
    if location:
        q_parts.append(location)
    base_q = " ".join(q_parts)

    # Exclusion suffix to remove noise sites
    exclude = " -site:linkedin.com -site:facebook.com -site:amazon.com -site:ebay.com -site:wikipedia.org -site:reddit.com"

    # Search 1: DuckDuckGo — general query (business/shop focused)
    ddg_q1 = base_q + " shop OR store OR buy" + exclude
    html1 = _fetch_html(f"https://html.duckduckgo.com/html/?q={quote_plus(ddg_q1)}", timeout=12, max_bytes=500_000)
    if html1:
        for u in _parse_duckduckgo(html1):
            if u not in seen:
                seen.add(u)
                all_urls.append(u)

    # Search 2: DuckDuckGo — .co.uk focus for UK searches
    if location and ("uk" in location.lower() or "united kingdom" in location.lower()):
        ddg_q2 = f"{query} site:.co.uk" + exclude
    else:
        ddg_q2 = base_q + " company website" + exclude
    html2 = _fetch_html(f"https://html.duckduckgo.com/html/?q={quote_plus(ddg_q2)}", timeout=10, max_bytes=500_000)
    if html2:
        for u in _parse_duckduckgo(html2):
            if u not in seen:
                seen.add(u)
                all_urls.append(u)

    # Search 3: Bing (always try — gives different results)
    bing_q = base_q + " online store"
    html3 = _fetch_html(f"https://www.bing.com/search?q={quote_plus(bing_q)}&count=20", timeout=10, max_bytes=500_000)
    if html3:
        for u in _parse_bing(html3):
            if u not in seen:
                seen.add(u)
                all_urls.append(u)

    return all_urls[:max_results]


# ---------------------------------------------------------------------------
# Step 2: Concurrent Tech Stack Scanner
# ---------------------------------------------------------------------------
def detect_technologies(url: str) -> dict:
    """
    Downloads the homepage HTML of a URL and scans for tech fingerprints.
    Returns a dict: { tech_name: category } for each detected technology.
    """
    html = _fetch_html(url, timeout=REQUEST_TIMEOUT)
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


def _scan_single_site(url: str) -> dict:
    """Scans one URL: fetches HTML, detects tech, extracts basic contact info."""
    html = _fetch_html(url, timeout=REQUEST_TIMEOUT)
    if not html:
        return {"url": url, "ok": False, "techs": {}, "contact_info": None}

    html_lower = html.lower()

    # Detect technologies
    techs = {}
    for tech_name, info in TECH_SIGNATURES.items():
        for pattern in info["patterns"]:
            if pattern.lower() in html_lower:
                techs[tech_name] = info["category"]
                break

    # Extract basic info inline (no extra page fetches for speed)
    parsed = urlparse(url)
    domain = parsed.netloc.lstrip("www.")
    company_name = _extract_company_name_from_html(html, domain)
    country = _extract_country(html)
    emails = _extract_emails(html, domain)
    linkedin_company = _extract_linkedin_company(html)

    return {
        "url": url,
        "ok": True,
        "techs": techs,
        "contact_info": {
            "company_name": company_name,
            "domain": domain,
            "website_url": url,
            "emails": emails,
            "country": country,
            "linkedin_company": linkedin_company,
            "linkedin_people": [],
        }
    }


def scan_sites_concurrent(urls: list, max_workers: int = 8, emit=None) -> list:
    """
    Scans all URLs concurrently using a thread pool.
    Returns list of scan result dicts.
    """
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_scan_single_site, url): url for url in urls}
        completed = 0
        for future in as_completed(future_map, timeout=120):
            url = future_map[future]
            completed += 1
            try:
                result = future.result(timeout=REQUEST_TIMEOUT + 2)
                results.append(result)
                if emit:
                    if result["ok"]:
                        tech_names = list(result["techs"].keys())
                        tech_str = ", ".join(tech_names[:4]) if tech_names else "no tech detected"
                        emit(f"[{completed}/{len(urls)}] ✅ {url} → {tech_str}")
                    else:
                        emit(f"[{completed}/{len(urls)}] ⚠️  {url} → unreachable, skipped")
            except Exception as e:
                results.append({"url": url, "ok": False, "techs": {}, "contact_info": None})
                if emit:
                    emit(f"[{completed}/{len(urls)}] ❌ {url} → error: {type(e).__name__}")
    return results


# ---------------------------------------------------------------------------
# Helper Extractors
# ---------------------------------------------------------------------------
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
CONTACT_PREFIXES = ["info", "hello", "contact", "sales", "team", "support", "enquiries", "enquiry"]
EMAIL_BLACKLIST_DOMAINS = {
    "example.com", "test.com", "sentry.io", "wixpress.com",
    "shopify.com", "klaviyo.com", "cloudflare.com",
    "w3.org", "schema.org", "google.com", "jquery.com",
    "facebook.com", "twitter.com", "instagram.com",
}


def _extract_emails(html: str, site_domain: str) -> list:
    raw_emails = EMAIL_PATTERN.findall(html)
    emails = []
    seen = set()
    for email in raw_emails:
        el = email.lower()
        ed = el.split("@")[-1]
        if ed in EMAIL_BLACKLIST_DOMAINS:
            continue
        if ed.endswith((".js", ".css", ".png", ".jpg", ".gif", ".svg", ".woff")):
            continue
        if el in seen:
            continue
        seen.add(el)
        emails.append(email)
    # Prefer on-domain emails first, then role-based
    def sort_key(e):
        el = e.lower()
        ed = el.split("@")[-1]
        on_domain = 0 if site_domain in ed else 1
        role_based = 0 if any(el.startswith(p + "@") or el.startswith(p + ".") for p in CONTACT_PREFIXES) else 1
        return (on_domain, role_based, e)
    emails.sort(key=sort_key)
    return emails[:8]


def _extract_company_name_from_html(html: str, domain: str) -> str:
    og = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if og:
        return og.group(1).strip()
    og2 = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']', html, re.IGNORECASE)
    if og2:
        return og2.group(1).strip()
    title = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if title:
        t = title.group(1).strip()
        for sep in [" | ", " - ", " – ", " · ", " :: "]:
            if sep in t:
                t = t.split(sep)[0].strip()
        if t:
            return t
    return domain.replace("www.", "").split(".")[0].replace("-", " ").title()


def _extract_country(html: str) -> str:
    patterns = [
        r'"addressCountry"\s*:\s*"([^"]{2,30})"',
        r'addressCountry["\s:]+([A-Z]{2})',
        r'<meta[^>]+name=["\']geo\.country["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            country_map = {
                "GB": "United Kingdom", "UK": "United Kingdom",
                "US": "United States", "CA": "Canada",
                "AU": "Australia", "DE": "Germany",
                "FR": "France", "NL": "Netherlands", "IE": "Ireland",
            }
            return country_map.get(val.upper(), val)
    return ""


def _extract_linkedin_company(html: str) -> str:
    m = re.search(r'linkedin\.com/company/([A-Za-z0-9\-_%]+)', html)
    if m:
        return f"https://www.linkedin.com/company/{m.group(1)}"
    return ""


# ---------------------------------------------------------------------------
# Step 3: Contact Extractor (for matched companies — visits /contact too)
# ---------------------------------------------------------------------------
def extract_contacts_deep(url: str) -> dict:
    """
    Crawls homepage + /contact page to gather more contact info.
    Used only for companies that matched the tech filter.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lstrip("www.")
    all_html = ""

    home_html = _fetch_html(url, timeout=REQUEST_TIMEOUT) or ""
    all_html += home_html

    # Try /contact page
    contact_url = f"{parsed.scheme}://{parsed.netloc}/contact"
    c_html = _fetch_html(contact_url, timeout=5) or ""
    all_html += c_html

    emails = _extract_emails(all_html, domain)
    linkedin_company = _extract_linkedin_company(all_html)

    people_handles = list(set(re.findall(r'linkedin\.com/in/([A-Za-z0-9\-_%]+)', all_html)))

    return {
        "company_name": _extract_company_name_from_html(home_html, domain),
        "domain": domain,
        "website_url": url,
        "emails": emails,
        "country": _extract_country(all_html),
        "linkedin_company": linkedin_company,
        "linkedin_people": [f"https://www.linkedin.com/in/{h}" for h in people_handles[:5]],
    }


# ---------------------------------------------------------------------------
# Step 4: Full Discovery Pipeline
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
    Full end-to-end discovery pipeline.

    KEY CHANGE from v1: We NO LONGER filter out companies that don't have
    required_techs. Instead we SHOW ALL companies and just label their actual
    detected techs. This avoids zero results when sites load Klaviyo via JS.

    required_techs is used to SORT results (matching sites appear first).
    """

    def _emit(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    # Step 1: Search
    _emit(f"🔍 Searching web for: '{query}' in '{location or 'anywhere'}'...")
    urls = search_web(query, location, max_results=max_results)

    if not urls:
        _emit("⚠️  No URLs returned from search. Try a broader query.")
        return {"status": "complete", "companies_found": 0, "contacts_found": 0, "companies": []}

    _emit(f"📋 Found {len(urls)} candidate websites. Scanning all concurrently (this is fast)...")

    # Step 2: Scan all sites concurrently
    scan_results = scan_sites_concurrent(urls, max_workers=8, emit=_emit)

    # Step 3: Score and sort — matching techs first
    required_lower = {t.lower() for t in required_techs}

    def _score(r):
        if not r["ok"] or not r["contact_info"]:
            return -1
        detected_lower = {k.lower() for k in r["techs"].keys()}
        matches = len(required_lower & detected_lower)
        return matches

    scan_results.sort(key=_score, reverse=True)

    # Filter out unreachable sites
    reachable = [r for r in scan_results if r["ok"] and r["contact_info"]]

    if not reachable:
        _emit("⚠️  All sites were unreachable or blocked. Try a different search query.")
        return {"status": "complete", "companies_found": 0, "contacts_found": 0, "companies": []}

    _emit(f"\n💾 Saving {len(reachable)} companies to database...")

    # Step 4: Save to database
    saved_companies = []
    saved_contacts = []

    for item in reachable:
        info = item["contact_info"]
        techs = item["techs"]
        domain = info["domain"]

        if not domain:
            continue

        # Skip if already exists
        existing = db.query(Company).filter(Company.domain == domain).first()
        if existing:
            _emit(f"  ⏭ {domain} already in database")
            matched = {k for k in techs.keys() if k.lower() in required_lower}
            saved_companies.append({
                "company_id": existing.company_id,
                "domain": domain,
                "legal_name": existing.legal_name,
                "hq_country": existing.hq_country,
                "technologies": list(techs.keys()),
                "website_url": info["website_url"],
                "linkedin_url": info.get("linkedin_company", ""),
                "confidence_score": existing.confidence_score,
                "tech_matches": list(matched),
                "contacts": [],
                "already_existed": True,
            })
            continue

        company_id = f"co_disc_{uuid.uuid4().hex[:8]}"
        tech_match_count = len({k.lower() for k in techs.keys()} & required_lower)
        confidence = min(0.55 + 0.15 * tech_match_count, 0.95)

        company = Company(
            company_id=company_id,
            legal_name=info["company_name"],
            display_name=info["company_name"],
            domain=domain,
            website_url=info["website_url"],
            linkedin_url=info.get("linkedin_company") or None,
            hq_country=info.get("country") or (location if location else None),
            technologies=list(techs.keys()),
            confidence_score=confidence,
        )
        db.add(company)
        db.add(DomainEdge(company_id=company_id, domain=domain, is_canonical=True))
        for tech_name, category in techs.items():
            db.add(TechEdge(company_id=company_id, tech_slug=tech_name.lower(), category=category, confidence=0.85))
        db.add(FieldMetadata(
            entity_type="company", entity_id=company_id, field_name="domain",
            source="web_discovery", confidence_score=confidence,
            last_updated_at=datetime.datetime.utcnow()
        ))
        db.flush()

        # Save contacts (on-domain emails only)
        persons_saved = []
        for idx, email in enumerate(info["emails"][:5]):
            email_domain = email.split("@")[-1].lower()
            if not (domain in email_domain or email_domain in domain):
                continue
            person_id = f"pr_disc_{uuid.uuid4().hex[:8]}"
            prefix = email.split("@")[0]
            name_parts = re.split(r"[._\-]", prefix)
            first = name_parts[0].title() if name_parts else "Contact"
            last = name_parts[1].title() if len(name_parts) > 1 else ""
            full_name = f"{first} {last}".strip()
            linkedin = info["linkedin_people"][idx] if idx < len(info.get("linkedin_people", [])) else None
            person = Person(
                person_id=person_id, company_id=company_id,
                first_name=first, last_name=last, full_name=full_name,
                title="Contact", seniority="unknown", department="unknown",
                email=email, email_status="likely_valid",
                location=info.get("country") or location or None,
                linkedin_url=linkedin, confidence_score=0.60,
            )
            db.add(person)
            persons_saved.append({"full_name": full_name, "email": email, "linkedin_url": linkedin})

        db.commit()

        matched_techs = [k for k in techs.keys() if k.lower() in required_lower]
        _emit(f"  💾 Saved: {info['company_name']} ({domain}) | techs: {', '.join(list(techs.keys())[:3]) or 'none'} | {len(persons_saved)} contacts")

        saved_companies.append({
            "company_id": company_id,
            "domain": domain,
            "legal_name": info["company_name"],
            "hq_country": info.get("country"),
            "technologies": list(techs.keys()),
            "website_url": info["website_url"],
            "linkedin_url": info.get("linkedin_company", ""),
            "confidence_score": confidence,
            "tech_matches": matched_techs,
            "contacts": persons_saved,
        })
        saved_contacts.extend(persons_saved)

    matching = [c for c in saved_companies if c.get("tech_matches")]
    _emit(f"\n🎉 Done! Saved {len(saved_companies)} companies ({len(matching)} match your tech filters), {len(saved_contacts)} contacts.")

    return {
        "status": "complete",
        "companies_found": len(saved_companies),
        "contacts_found": len(saved_contacts),
        "companies": saved_companies,
        "tech_matching": len(matching),
    }
