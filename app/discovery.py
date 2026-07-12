"""
AeroLead Discovery Engine v3
=============================
Self-hosted company discovery pipeline using pure Python web scraping.
Uses 5 search engines concurrently to avoid rate-limiting by any single source.
No third-party APIs required.
"""

import re
import time
import uuid
import datetime
import logging
import random
import html as html_module
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            "myshopify.com", "shopifycloud.com", "window.Shopify",
            "shopify_features", "Shopify.shop",
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
        "patterns": ["woocommerce", "wc-ajax", "woocommerce-cart"]
    },
    "WordPress": {
        "category": "CMS",
        "patterns": ["wp-content/", "wp-includes/", "/wp-json/"]
    },
    "Mailchimp": {
        "category": "Email Marketing",
        "patterns": ["mailchimp.com", "chimpstatic.com", "mc.us"]
    },
    "HubSpot": {
        "category": "CRM & Marketing",
        "patterns": ["js.hs-scripts.com", "hubspot.com/", "hbspt.forms"]
    },
    "Stripe": {
        "category": "Payments",
        "patterns": ["js.stripe.com", "stripe.js"]
    },
    "Google Analytics": {
        "category": "Analytics",
        "patterns": ["googletagmanager.com/gtag", "gtag('config'", "google-analytics.com"]
    },
    "Zendesk": {
        "category": "Customer Support",
        "patterns": ["zopim.com", "zendesk.com/embeddable_framework", "zdassets.com"]
    },
    "Magento": {
        "category": "E-commerce",
        "patterns": ["Mage.Cookies", "magento", "mage/cookies"]
    },
    "BigCommerce": {
        "category": "E-commerce",
        "patterns": ["bigcommerce.com", "cdn11.bigcommerce.com"]
    },
    "Facebook Pixel": {
        "category": "Advertising",
        "patterns": ["connect.facebook.net/en_US/fbevents.js", "fbq('init'"]
    },
    "TikTok Pixel": {
        "category": "Advertising",
        "patterns": ["analytics.tiktok.com", "tiktok-pixel"]
    },
    "Hotjar": {
        "category": "Analytics",
        "patterns": ["static.hotjar.com", "hotjar"]
    },
    "Trustpilot": {
        "category": "Reviews",
        "patterns": ["widget.trustpilot.com", "trustpilot.com/review"]
    },
    "Yotpo": {
        "category": "Reviews",
        "patterns": ["staticw2.yotpo.com", "yotpo.com"]
    },
    "Attentive": {
        "category": "SMS Marketing",
        "patterns": ["attn.tv", "attentivemobile.com"]
    },
    "Omnisend": {
        "category": "Email Marketing",
        "patterns": ["omnisrc.com", "omnisend.com"]
    },
}

# ---------------------------------------------------------------------------
# Domains to always skip
# ---------------------------------------------------------------------------
SKIP_DOMAINS = {
    "google.com", "google.co.uk", "google.com.au", "google.de",
    "bing.com", "yahoo.com", "finance.yahoo.com", "news.yahoo.com", "duckduckgo.com", "mojeek.com",
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
    "amazon.com", "amazon.co.uk", "ebay.com", "ebay.co.uk",
    "wikipedia.org", "reddit.com", "quora.com", "medium.com",
    "indeed.com", "glassdoor.com", "trustpilot.com", "yelp.com",
    "yell.com", "checkatrade.com", "companies.house.gov.uk",
    "gov.uk", "hmrc.gov.uk", "bbc.co.uk", "theguardian.com",
    "dailymail.co.uk", "shopify.com", "wix.com", "squarespace.com",
    "etsy.com", "asos.com", "nike.com", "adidas.com",
    "temu.com", "shein.com", "zara.com", "hm.com", "primark.com",
    "next.co.uk", "marksandspencer.com", "debenhams.com",
    "search.yahoo.com", "uk.yahoo.com",
}

# ---------------------------------------------------------------------------
# HTTP — Rotating User-Agents
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

REQUEST_TIMEOUT = 6


def _fetch_html(url: str, timeout: int = REQUEST_TIMEOUT, max_bytes: int = 300_000) -> Optional[str]:
    """Fetches HTML using urllib with a rotated user-agent. Returns None on error."""
    try:
        req = Request(
            url,
            headers={
                "User-Agent": random.choice(_USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        with urlopen(req, timeout=timeout) as resp:
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].strip().split(";")[0]
            return resp.read(max_bytes).decode(charset, errors="replace")
    except Exception as e:
        logger.debug(f"Fetch failed {url}: {type(e).__name__}")
        return None


def _is_blocked(html: Optional[str]) -> bool:
    """Returns True if page looks like a CAPTCHA or block page."""
    if not html or len(html) < 400:
        return True
    signals = [
        "unusual traffic", "captcha", "are you a human",
        "access denied", "too many requests", "automated queries",
        "verify you are human", "bot detection",
    ]
    hl = html.lower()
    return any(s in hl for s in signals)


def _extract_urls_from_html(html: str, skip_containing: str = "") -> list:
    """Generic URL extractor from any search result HTML.
    Decodes HTML entities first to avoid truncation at &#NNN; sequences.
    """
    # Decode HTML entities so &#46; -> . before URL parsing
    try:
        html = html_module.unescape(html)
    except Exception:
        pass
    seen = set()
    result = []
    for href in re.findall(r'href=["\']?(https?://[^\s"\'<>]{10,})', html):
        if skip_containing and skip_containing in href:
            continue
        try:
            href = unquote(href)
        except Exception:
            pass
        # Strip trailing junk chars
        href = href.rstrip("\"'><).,;")
        parsed = urlparse(href)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        netloc = parsed.netloc
        # Must have a dot and valid TLD
        if "." not in netloc or len(netloc) < 5:
            continue
        tld = netloc.rsplit(".", 1)[-1].lower()
        if len(tld) < 2 or not tld.isalpha():
            continue
        base = f"{parsed.scheme}://{netloc}"
        domain = netloc.replace("www.", "").replace("www2.", "")
        if domain in SKIP_DOMAINS or base in seen:
            continue
        if any(x in parsed.path.lower() for x in ["/search", "/wiki/", ".js", ".css", ".png", ".jpg"]):
            continue
        seen.add(base)
        result.append(base)
    return result


def _extract_ddg_urls(html: str) -> list:
    """Extracts URLs from DuckDuckGo results (uddg= encoded links)."""
    seen = set()
    result = []
    # Primary: uddg= parameters
    for raw in re.findall(r'uddg=(https?[^&"\'\\s]+)', html):
        try:
            url = unquote(raw)
        except Exception:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        base = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc.replace("www.", "")
        if domain not in SKIP_DOMAINS and base not in seen:
            seen.add(base)
            result.append(base)
    # Fallback: generic hrefs
    for u in _extract_urls_from_html(html, skip_containing="duckduckgo.com"):
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


# ---------------------------------------------------------------------------
# Individual Search Engine Functions
# ---------------------------------------------------------------------------
def _search_ddg_lite(query: str) -> list:
    """DuckDuckGo Lite — minimal HTML, most scraper-friendly DDG endpoint."""
    url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}&kl=uk-en"
    html = _fetch_html(url, timeout=12, max_bytes=400_000)
    if _is_blocked(html):
        logger.debug("DDG Lite blocked")
        return []
    return _extract_ddg_urls(html)


def _search_ddg_html(query: str) -> list:
    """DuckDuckGo HTML — heavier but more results."""
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl=uk-en"
    html = _fetch_html(url, timeout=12, max_bytes=500_000)
    if _is_blocked(html):
        logger.debug("DDG HTML blocked")
        return []
    return _extract_ddg_urls(html)


def _search_bing(query: str) -> list:
    """Bing search."""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count=20&mkt=en-GB"
    html = _fetch_html(url, timeout=10, max_bytes=500_000)
    if _is_blocked(html):
        logger.debug("Bing blocked")
        return []
    return _extract_urls_from_html(html, skip_containing="bing.com")


def _search_mojeek(query: str) -> list:
    """Mojeek — independent UK search engine, scraper-friendly."""
    url = f"https://www.mojeek.com/search?q={quote_plus(query)}&fmt=1"
    html = _fetch_html(url, timeout=10, max_bytes=400_000)
    if _is_blocked(html):
        logger.debug("Mojeek blocked")
        return []
    return _extract_urls_from_html(html, skip_containing="mojeek.com")


def _search_yahoo(query: str) -> list:
    """Yahoo search — useful when DDG rate-limits."""
    url = f"https://search.yahoo.com/search?p={quote_plus(query)}&n=20"
    html = _fetch_html(url, timeout=10, max_bytes=500_000)
    if _is_blocked(html):
        logger.debug("Yahoo blocked")
        return []
    raw = []
    # Yahoo uses /r/?RU= redirect links
    for encoded in re.findall(r'RU=(https?[^&"\'\\s]+)', html):
        try:
            raw.append(unquote(encoded))
        except Exception:
            pass
    seen = set()
    result = []
    for href in raw:
        parsed = urlparse(href)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        base = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc.replace("www.", "")
        if domain not in SKIP_DOMAINS and base not in seen:
            seen.add(base)
            result.append(base)
    # Also try generic hrefs
    for u in _extract_urls_from_html(html, skip_containing="yahoo.com"):
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


# ---------------------------------------------------------------------------
# Master Search — runs all engines concurrently
# ---------------------------------------------------------------------------
def search_web(query: str, location: str = "", max_results: int = 20) -> list:
    """
    Queries 5 search engines concurrently with varied search terms.
    Gracefully degrades if any engine blocks or fails.
    Returns up to max_results deduplicated base URLs.
    """
    base_q = f"{query} {location}".strip() if location else query
    is_uk = location and ("uk" in location.lower() or "united kingdom" in location.lower())

    # Multiple query variations spread across engines
    tasks = [
        ("ddg_lite", _search_ddg_lite, base_q + " online shop"),
        ("ddg_lite2", _search_ddg_lite, (f"{query} site:.co.uk" if is_uk else base_q + " company")),
        ("ddg_html",  _search_ddg_html, base_q + " buy store"),
        ("bing",      _search_bing,     base_q + " shop"),
        ("mojeek",    _search_mojeek,   base_q + " ecommerce website"),
        ("yahoo",     _search_yahoo,    base_q + " online store"),
    ]

    all_urls = []
    seen = set()

    def _run(engine_name, fn, q):
        try:
            return fn(q)
        except Exception as e:
            logger.debug(f"{engine_name} error: {e}")
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_run, name, fn, q): name for name, fn, q in tasks}
        for future in as_completed(futures, timeout=25):
            name = futures[future]
            try:
                urls = future.result(timeout=15) or []
                added = 0
                for u in urls:
                    if u not in seen:
                        seen.add(u)
                        all_urls.append(u)
                        added += 1
                logger.info(f"[{name}] returned {len(urls)} URLs, {added} new")
            except Exception as e:
                logger.debug(f"Future {name} error: {e}")

    logger.info(f"search_web total: {len(all_urls)} unique URLs for '{base_q}'")
    return all_urls[:max_results]


# ---------------------------------------------------------------------------
# Tech Stack Detection
# ---------------------------------------------------------------------------
def detect_technologies(url: str) -> dict:
    """Scans a URL's homepage HTML for technology fingerprints."""
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
    """Fetches one site and returns tech stack + basic company info."""
    html = _fetch_html(url, timeout=REQUEST_TIMEOUT)
    if not html:
        return {"url": url, "ok": False, "techs": {}, "contact_info": None}

    html_lower = html.lower()
    techs = {}
    for tech_name, info in TECH_SIGNATURES.items():
        for pattern in info["patterns"]:
            if pattern.lower() in html_lower:
                techs[tech_name] = info["category"]
                break

    parsed = urlparse(url)
    domain = parsed.netloc.lstrip("www.").lstrip("www2.")
    company_name = _extract_company_name(html, domain)
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
    """Scans all URLs concurrently using a thread pool."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_scan_single_site, url): url for url in urls}
        completed = 0
        for future in as_completed(future_map, timeout=90):
            url = future_map[future]
            completed += 1
            try:
                result = future.result(timeout=REQUEST_TIMEOUT + 3)
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
                    emit(f"[{completed}/{len(urls)}] ❌ {url} → timeout/error")
    return results


# ---------------------------------------------------------------------------
# Helper Extractors
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
_CONTACT_PREFIXES = ["info", "hello", "contact", "sales", "team", "support", "enquiries", "enquiry"]
_EMAIL_BLACKLIST = {
    "example.com", "test.com", "sentry.io", "wixpress.com",
    "shopify.com", "klaviyo.com", "cloudflare.com",
    "w3.org", "schema.org", "google.com", "jquery.com",
    "facebook.com", "twitter.com", "instagram.com", "apple.com",
}


def _extract_emails(html: str, site_domain: str) -> list:
    raw = _EMAIL_RE.findall(html)
    seen = set()
    emails = []
    for email in raw:
        el = email.lower()
        ed = el.split("@")[-1]
        if ed in _EMAIL_BLACKLIST:
            continue
        if ed.endswith((".js", ".css", ".png", ".jpg", ".gif", ".svg", ".woff")):
            continue
        if el in seen:
            continue
        seen.add(el)
        emails.append(email)

    def sort_key(e):
        el = e.lower()
        ed = el.split("@")[-1]
        on_domain = 0 if site_domain in ed else 1
        role = 0 if any(el.startswith(p) for p in _CONTACT_PREFIXES) else 1
        return (on_domain, role, e)

    emails.sort(key=sort_key)
    return emails[:8]


def _extract_company_name(html: str, domain: str) -> str:
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
        if t and len(t) < 80:
            return t
    return domain.replace("www.", "").split(".")[0].replace("-", " ").title()


def _extract_country(html: str) -> str:
    patterns = [
        r'"addressCountry"\s*:\s*"([^"]{2,30})"',
        r'addressCountry["\s:]+([A-Z]{2})',
        r'<meta[^>]+name=["\']geo\.country["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    country_map = {
        "GB": "United Kingdom", "UK": "United Kingdom",
        "US": "United States", "CA": "Canada",
        "AU": "Australia", "DE": "Germany",
        "FR": "France", "NL": "Netherlands", "IE": "Ireland",
    }
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            return country_map.get(val.upper(), val)
    return ""


def _extract_linkedin_company(html: str) -> str:
    m = re.search(r'linkedin\.com/company/([A-Za-z0-9\-_%]+)', html)
    return f"https://www.linkedin.com/company/{m.group(1)}" if m else ""


# ---------------------------------------------------------------------------
# Full Discovery Pipeline
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
    Full pipeline: search → concurrent scan → save to DB.
    Shows ALL found companies (sorted by tech match count).
    """

    def _emit(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    # Step 1: Search
    _emit(f"🔍 Searching 5 engines for: '{query}' in '{location or 'anywhere'}'...")
    urls = search_web(query, location, max_results=max_results)

    if not urls:
        _emit("⚠️  No URLs returned from any search engine. Try a simpler query (e.g. 'clothing' not 'clothing stores UK').")
        return {"status": "complete", "companies_found": 0, "contacts_found": 0, "companies": []}

    _emit(f"📋 Found {len(urls)} candidate websites. Scanning concurrently...")

    # Step 2: Scan all concurrently
    scan_results = scan_sites_concurrent(urls, max_workers=8, emit=_emit)

    # Step 3: Sort — sites matching required techs first
    required_lower = {t.lower() for t in required_techs}

    def _score(r):
        if not r["ok"] or not r["contact_info"]:
            return -1
        return len(required_lower & {k.lower() for k in r["techs"].keys()})

    scan_results.sort(key=_score, reverse=True)
    reachable = [r for r in scan_results if r["ok"] and r["contact_info"]]

    if not reachable:
        _emit("⚠️  All discovered sites were unreachable. Try a different search query.")
        return {"status": "complete", "companies_found": 0, "contacts_found": 0, "companies": []}

    _emit(f"\n💾 Saving {len(reachable)} companies to database...")

    saved_companies = []
    saved_contacts = []

    for item in reachable:
        info = item["contact_info"]
        techs = item["techs"]
        domain = info.get("domain", "")
        if not domain or len(domain) < 3:
            continue

        existing = db.query(Company).filter(Company.domain == domain).first()
        if existing:
            _emit(f"  ⏭  {domain} already in database")
            matched = [k for k in techs.keys() if k.lower() in required_lower]
            saved_companies.append({
                "company_id": existing.company_id,
                "domain": domain,
                "legal_name": existing.legal_name,
                "hq_country": existing.hq_country,
                "technologies": list(techs.keys()),
                "website_url": info["website_url"],
                "linkedin_url": info.get("linkedin_company", ""),
                "confidence_score": existing.confidence_score,
                "tech_matches": matched,
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
            db.add(TechEdge(
                company_id=company_id, tech_slug=tech_name.lower(),
                category=category, confidence=0.85
            ))
        db.add(FieldMetadata(
            entity_type="company", entity_id=company_id, field_name="domain",
            source="web_discovery", confidence_score=confidence,
            last_updated_at=datetime.datetime.utcnow()
        ))
        db.flush()

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
        tech_str = ", ".join(list(techs.keys())[:3]) or "none detected"
        _emit(f"  💾 Saved: {info['company_name']} ({domain}) | {tech_str} | {len(persons_saved)} contacts")

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
