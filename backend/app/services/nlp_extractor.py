"""NLP Extractor — Complaint Classification & Named Entity Recognition.

Provides keyword+TF-IDF based complaint classification and regex-driven
entity extraction tailored for Indian e-commerce consumer complaints.
No GPU required; uses scikit-learn for lightweight text vectorisation.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


# ── Category definitions ──────────────────────────────────────────────────

CATEGORIES: List[str] = [
    "Non-Delivery",
    "Damaged/Defective Item",
    "Wrong/Missing Item",
    "Refund Delayed/Denied",
    "Hidden Charges/Overbilling",
    "Expired Food/Quick-Commerce Issue",
]

# Keyword seed corpus for each category — used as TF-IDF reference documents
_CATEGORY_KEYWORDS: Dict[str, str] = {
    "Non-Delivery": (
        "not delivered never received delivery failed tracking "
        "out for delivery shipment lost undelivered missing delivery "
        "package not arrived dispatch courier didn't deliver "
        "delivery date passed no delivery shows delivered but not received "
        "false delivery claim never came"
    ),
    "Damaged/Defective Item": (
        "damaged broken defective cracked scratched dent faulty "
        "not working malfunction dead on arrival DOA screen cracked "
        "manufacturing defect torn torn packaging dented crushed "
        "quality issue poor quality non-functional doesn't work "
        "broken lid broken hinge heating element doesn't work distorted sound"
    ),
    "Wrong/Missing Item": (
        "wrong item received different product sent incorrect item "
        "missing item not in package order mix up someone else order "
        "partial delivery incomplete order items missing short delivery "
        "different colour size variant wrong model wrong product"
    ),
    "Refund Delayed/Denied": (
        "refund not received refund delayed refund denied refund pending "
        "money not returned payment not refunded cancelled order refund "
        "refund rejected waiting for refund return accepted but no refund "
        "refund promised refund timeline passed bank refund"
    ),
    "Hidden Charges/Overbilling": (
        "hidden charges extra charges overcharged overbilled "
        "handling fee convenience fee undisclosed charges "
        "price higher than listed MRP violation charged more "
        "above MRP price mismatch price difference unexpected charge "
        "additional fee not shown at checkout billed extra"
    ),
    "Expired Food/Quick-Commerce Issue": (
        "expired food expiry date past expiry stale rotten moldy mold "
        "food safety FSSAI spoiled contaminated near expiry bad quality food "
        "expired milk expired paneer expired bread expired yogurt "
        "quick commerce grocery delivery food poisoning health risk "
        "use by date best before unsafe food"
    ),
}


# ── Platform / entity patterns ────────────────────────────────────────────

_PLATFORM_ALIASES: Dict[str, str] = {
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "zepto": "Zepto",
    "blinkit": "Blinkit",
    "swiggy instamart": "Swiggy Instamart",
    "swiggy": "Swiggy Instamart",
    "instamart": "Swiggy Instamart",
}

_ORDER_ID_STOPWORDS: set = {
    "placed", "order", "delivery", "details", "status", "cancel",
    "pending", "item", "items", "amount", "refund", "return", "product", "bought",
}

_ORDER_ID_PATTERNS: List[re.Pattern] = [
    # Explicit prefix patterns: "Order ID: ...", "Order #...", "Order No: ...", "Ref ID: ..."
    re.compile(r"(?:order\s*(?:id|no\.?|number|#)|ref\s*(?:id|no\.?|#)?|tracking\s*(?:id|#)?)\s*[:=\-#]?\s*([A-Za-z0-9\-_]{5,30})\b", re.IGNORECASE),
    re.compile(r"(?:order)\s*[:=\-#]\s*([A-Za-z0-9\-_]{5,30})\b", re.IGNORECASE),
    re.compile(r"\b(OD\d{10,})\b"),                     # Flipkart: OD*
    re.compile(r"\b(40[0-9]-\d{7}-\d{7})\b"),           # Amazon: 402-*-*  / 408-*-*
    re.compile(r"\b(ZPT-\d{8}-\d+)\b"),                 # Zepto
    re.compile(r"\b(BLINK-\d{10,})\b"),                  # Blinkit
    re.compile(r"\b(SWG-IM-\d{5,})\b"),                  # Swiggy Instamart
    re.compile(r"\b(SWG-\d+)\b"),                        # Swiggy generic
    # Uppercase alphanumeric tokens with at least one letter and at least one number (e.g. JHQISCUIQ59225)
    re.compile(r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*[0-9])[A-Z0-9]{8,24}\b"),
]

_AMOUNT_PATTERN = re.compile(
    r"(?:order\s*value\s*[:=\-]?\s*|price\s*[:=\-]?\s*|amount\s*[:=\-]?\s*|cost\s*[:=\-]?\s*)?₹\s*(\d[\d,]*\.?\d*)"  # e.g. Order Value: ₹1,995
    r"|(?:order\s*value\s*[:=\-]?\s*|price\s*[:=\-]?\s*|amount\s*[:=\-]?\s*|cost\s*[:=\-]?\s*)(?:₹|Rs\.?\s*|INR\s*)?(\d[\d,]*\.?\d*)" # e.g. Order Value: 1,995
    r"|(?:₹|Rs\.?\s*|INR\s*)\s*(\d[\d,]*\.?\d*)"               # currency symbol / prefix
    r"|(\d[\d,]*\.?\d*)\s*(?:rupees|rs|inr)", 
    re.IGNORECASE,
)

# Date patterns for extraction
_DATE_PATTERNS: List[re.Pattern] = [
    # "October 25th", "Nov 2nd", "November 5"
    re.compile(
        r"\b((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|"
        r"Nov|Dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?)\b",
        re.IGNORECASE,
    ),
    # "25 October 2026", "25th Oct"
    re.compile(
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|"
        r"June|July|August|September|October|November|December|Jan|Feb|Mar|"
        r"Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
        r"(?:\s+\d{4})?)\b",
        re.IGNORECASE,
    ),
    # ISO-like: 2026-10-25
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    # dd/mm/yyyy or dd-mm-yyyy
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
]

# Month lookup
_MONTH_MAP: Dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2,
    "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


# ── TF-IDF classifier (lazy-init singleton) ──────────────────────────────

class _Classifier:
    """Lazy-initialised TF-IDF classifier over category keyword corpora."""

    def __init__(self) -> None:
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._category_vectors = None
        self._labels: List[str] = []

    def _ensure_fitted(self) -> None:
        if self._vectorizer is not None:
            return
        if not _SKLEARN_AVAILABLE:
            return
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=5000,
        )
        corpus = list(_CATEGORY_KEYWORDS.values())
        self._labels = list(_CATEGORY_KEYWORDS.keys())
        self._category_vectors = self._vectorizer.fit_transform(corpus)

    def classify(self, text: str) -> Dict[str, Any]:
        """Return ``{category, confidence}`` for the given complaint text."""
        self._ensure_fitted()

        if self._vectorizer is None:
            # sklearn not available — fall back to keyword counting
            return self._keyword_fallback(text)

        text_vec = self._vectorizer.transform([text.lower()])
        similarities = cosine_similarity(text_vec, self._category_vectors)[0]
        best_idx = int(similarities.argmax())
        confidence = float(similarities[best_idx])

        if confidence < 0.02:
            return {"category": "Other", "confidence": round(confidence, 4)}

        return {
            "category": self._labels[best_idx],
            "confidence": round(confidence, 4),
        }

    # ── keyword fallback (no sklearn) ─────────────────────────────────
    @staticmethod
    def _keyword_fallback(text: str) -> Dict[str, Any]:
        text_lower = text.lower()
        best_cat = "Other"
        best_score = 0
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            words = set(keywords.split())
            score = sum(1 for w in words if w in text_lower)
            if score > best_score:
                best_score = score
                best_cat = cat
        confidence = min(best_score / 10.0, 1.0) if best_score else 0.0
        return {"category": best_cat, "confidence": round(confidence, 4)}


_classifier = _Classifier()


# ── Public API ────────────────────────────────────────────────────────────

def classify_complaint(text: str) -> Dict[str, Any]:
    """Classify a complaint into one of 6 categories + confidence.

    Returns:
        ``{"category": str, "confidence": float}``
    """
    return _classifier.classify(text)


def extract_entities(text: str) -> List[Dict[str, Any]]:
    """Extract named entities from complaint text.

    Entity types: PLATFORM, AMOUNT, ORDER_ID, DATE, PRODUCT.

    Returns:
        List of ``{"type": str, "value": str, "normalized_value": str|None}``
    """
    entities: List[Dict[str, Any]] = []

    # ── PLATFORM Contextual Disambiguation ───────────────────────────
    # Distinguish vendor/platform (e.g. Zepto) from product brand (e.g. Amazon Pay Gift Card)
    text_lower = text.lower()
    candidate_platforms: List[Dict[str, Any]] = []

    # High-confidence vendor/platform context patterns:
    # "reported this issue to Zepto", "complained to Zepto", "ordered from Zepto", "bought on Zepto"
    vendor_patterns = [
        r"(?:ordered|bought|purchased|placed\s+order\s+on|got\s+from|from|on)\s+([a-zA-Z\s]+)",
        r"(?:reported\s+(?:this\s+issue\s+)?to|contacted|complained\s+to|raised\s+(?:ticket|issue)\s+with)\s+([a-zA-Z\s]+)",
        r"(?:app\s+of|delivery\s+by|delivered\s+by)\s+([a-zA-Z\s]+)",
    ]

    vendor_hits: set = set()
    for vpat in vendor_patterns:
        for vm in re.finditer(vpat, text, re.IGNORECASE):
            subtext = vm.group(1).lower()[:30]
            for alias, canonical in _PLATFORM_ALIASES.items():
                if alias in subtext:
                    vendor_hits.add(canonical)

    # Product brand context patterns: e.g. "Amazon Pay Gift Card", "Apple iPhone", "Samsung TV"
    product_brand_hits: set = set()
    brand_patterns = [
        r"([a-zA-Z\s]+)\s+(?:pay\s+)?gift\s*card",
        r"card\s+ordered\s*[:=\-]?\s*([a-zA-Z\s]+)",
        r"(?:voucher|coupon|subscription)\s+of\s+([a-zA-Z\s]+)",
    ]
    for bpat in brand_patterns:
        for bm in re.finditer(bpat, text, re.IGNORECASE):
            subtext = bm.group(1).lower()[:30]
            for alias, canonical in _PLATFORM_ALIASES.items():
                if alias in subtext:
                    product_brand_hits.add(canonical)

    found_platforms: set = set()
    for alias, canonical in _PLATFORM_ALIASES.items():
        if alias in text_lower and canonical not in found_platforms:
            found_platforms.add(canonical)
            is_vendor = canonical in vendor_hits
            is_product_brand = canonical in product_brand_hits and canonical not in vendor_hits

            candidate_platforms.append({
                "type": "PLATFORM",
                "value": canonical,
                "normalized_value": canonical,
                "is_vendor": is_vendor,
                "is_product_brand": is_product_brand,
            })

    # Sort platforms so strong vendor hits come first, purely brand mentions come last
    candidate_platforms.sort(key=lambda p: (p.get("is_vendor", False), not p.get("is_product_brand", False)), reverse=True)
    entities.extend(candidate_platforms)

    # ── ORDER_ID ──────────────────────────────────────────────────────
    seen_order_ids: set = set()
    for pat in _ORDER_ID_PATTERNS:
        for m in pat.finditer(text):
            oid = m.group(1) if m.groups() and m.group(1) else m.group(0)
            if oid:
                oid_clean = oid.strip()
                if oid_clean.lower() in _ORDER_ID_STOPWORDS:
                    continue
                # If there are no digits and it's not a platform prefix (like OD...), skip
                if not re.search(r"\d", oid_clean) and not oid_clean.upper().startswith("OD"):
                    continue
                if oid_clean not in seen_order_ids:
                    seen_order_ids.add(oid_clean)
                    entities.append({
                        "type": "ORDER_ID",
                        "value": oid_clean,
                        "normalized_value": oid_clean,
                    })

    # ── AMOUNT Contextual Role Disambiguation ─────────────────────────
    # If text has "Order Value: 1995" or "paid 1995", prioritize that over denomination mentions
    seen_amounts: set = set()
    order_val_match = re.search(r"(?:order\s*value|paid|disputed\s*amount|total\s*amount|charged)\s*[:=\-]?\s*(?:₹|Rs\.?\s*|INR\s*)?(\d[\d,]*\.?\d*)", text, re.IGNORECASE)
    priority_order_val = None
    if order_val_match:
        try:
            priority_order_val = float(order_val_match.group(1).replace(",", ""))
            seen_amounts.add(priority_order_val)
            entities.append({
                "type": "AMOUNT",
                "value": str(priority_order_val),
                "normalized_value": f"INR {priority_order_val}",
                "is_order_value": True,
            })
        except ValueError:
            pass

    for m in _AMOUNT_PATTERN.finditer(text):
        raw = next((g for g in m.groups() if g), None)
        if raw:
            cleaned = raw.replace(",", "")
            try:
                numeric = float(cleaned)
            except ValueError:
                continue
            if numeric not in seen_amounts:
                seen_amounts.add(numeric)
                entities.append({
                    "type": "AMOUNT",
                    "value": str(numeric),
                    "normalized_value": f"INR {numeric}",
                    "is_order_value": (numeric == priority_order_val),
                })

    # ── DATE ──────────────────────────────────────────────────────────
    seen_dates: set = set()
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1).strip()
            if raw not in seen_dates:
                seen_dates.add(raw)
                normalized = normalize_date(raw)
                entities.append({
                    "type": "DATE",
                    "value": raw,
                    "normalized_value": normalized,
                })

    # ── PRODUCT ───────────────────────────────────────────────────────
    products = _extract_products(text)
    for prod in products:
        entities.append({
            "type": "PRODUCT",
            "value": prod,
            "normalized_value": prod,
        })

    return entities


def resolve_platform(text: str, candidates: Optional[List[str]] = None) -> Optional[str]:
    """Resolve the vendor/platform (e.g. Zepto) vs product brand (e.g. Amazon Pay Gift Card)."""
    if not candidates:
        entities = extract_entities(text)
        candidates = [e["value"] for e in entities if e.get("type") == "PLATFORM"]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    text_lower = text.lower()
    for cand in candidates:
        alias_matches = [k for k, v in _PLATFORM_ALIASES.items() if v == cand]
        for a in alias_matches:
            if re.search(rf"(?:reported\s+(?:this\s+issue\s+)?to|contacted|complained\s+to|ordered\s+from|bought\s+on|app\s+of)\s+{a}", text_lower):
                return cand
    return candidates[0]


def disambiguate_amount(text: str, entities: Optional[List[Dict[str, Any]]] = None) -> Optional[float]:
    """Disambiguate the disputed order value from packaging/voucher denominations."""
    ov_match = re.search(
        r"(?:order\s*value|order\s*amount|disputed\s*amount|total\s*bill|order\s+was\s+for|order\s+value\s+of\s+it\s+was|value\s*of\s*it\s*was)\s*[:=\-]?\s*(?:rs\.?|inr|₹)?\s*([0-9,]+(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE,
    )
    if ov_match:
        try:
            return float(ov_match.group(1).replace(",", ""))
        except ValueError:
            pass

    if entities:
        order_val_ents = [e for e in entities if e.get("type") == "AMOUNT" and e.get("is_order_value")]
        if order_val_ents:
            try:
                return float(order_val_ents[0]["value"])
            except ValueError:
                pass
        amt_ents = [e for e in entities if e.get("type") == "AMOUNT"]
        if amt_ents:
            try:
                return float(amt_ents[0]["value"])
            except ValueError:
                pass
    return None


def normalize_date(
    date_str: str, reference_date: Optional[datetime] = None
) -> Optional[str]:
    """Normalise a free-text date string to ISO-8601 ``YYYY-MM-DD``.

    Args:
        date_str: The raw date string (e.g. ``"05 aug 2026"``, ``"October 25th"``).
        reference_date: Used to infer the year when omitted.
            Defaults to ``datetime.utcnow()``.

    Returns:
        ISO date string or ``None`` if parsing fails.
    """
    if not date_str or not date_str.strip():
        return None

    cleaned = date_str.strip()

    # 1. ISO format: 2026-10-25 (always check standard ISO first!)
    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", cleaned)
    if iso_match:
        return cleaned

    # 2. Try python-dateutil parser with dayfirst=True and fuzzy=True
    try:
        from dateutil import parser as dt_parser
        if re.search(r"\d", cleaned) or any(m in cleaned.lower() for m in _MONTH_MAP):
            parsed = dt_parser.parse(cleaned, fuzzy=True, dayfirst=True)
            if parsed and 2000 <= parsed.year <= 2099:
                return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass

    # dd/mm/yyyy or dd-mm-yyyy
    slash_match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", cleaned)
    if slash_match:
        day, month, year = int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3))
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    # Remove ordinal suffixes
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", cleaned, flags=re.IGNORECASE)
    # Remove trailing dot from abbreviated months
    cleaned = re.sub(r"\.(\s|$)", r"\1", cleaned)

    # "Month Day [Year]" or "Day Month [Year]"
    parts = cleaned.split()
    if len(parts) >= 2:
        month_num: Optional[int] = None
        day_num: Optional[int] = None
        year_num: int = reference_date.year

        # Determine which token is the month
        if parts[0].lower().rstrip(".") in _MONTH_MAP:
            month_num = _MONTH_MAP[parts[0].lower().rstrip(".")]
            try:
                day_num = int(parts[1])
            except ValueError:
                return None
            if len(parts) >= 3:
                try:
                    year_num = int(parts[2])
                except ValueError:
                    pass
        elif len(parts) >= 2 and parts[1].lower().rstrip(".") in _MONTH_MAP:
            month_num = _MONTH_MAP[parts[1].lower().rstrip(".")]
            try:
                day_num = int(parts[0])
            except ValueError:
                return None
            if len(parts) >= 3:
                try:
                    year_num = int(parts[2])
                except ValueError:
                    pass

        if month_num and day_num:
            if year_num < 100:
                year_num += 2000
            try:
                return datetime(year_num, month_num, day_num).strftime("%Y-%m-%d")
            except ValueError:
                return None

    return None


def extract_all(text: str) -> Dict[str, Any]:
    """Run both classification and entity extraction on complaint text.

    Returns:
        ``{"intent": {"category": str, "confidence": float},
          "entities": [{"type": str, "value": str, "normalized_value": str}]}``
    """
    return {
        "intent": classify_complaint(text),
        "entities": extract_entities(text),
    }


# ── Internal helpers ──────────────────────────────────────────────────────

# Known product brands / keywords that hint at a product mention
_PRODUCT_BRANDS = [
    "Samsung", "OnePlus", "JBL", "Boat", "Prestige", "Philips", "Sony",
    "Apple", "Xiaomi", "Realme", "Nokia", "LG", "Bajaj", "Havells",
    "Amul", "Mother Dairy", "Maggi", "Parle", "Vim", "Surf", "Tide",
]

_PRODUCT_KEYWORDS = [
    "power bank", "phone", "smartphone", "laptop", "tablet", "speaker",
    "bluetooth speaker", "earbuds", "airdopes", "headphones", "earphones",
    "electric kettle", "kettle", "mixer", "grinder", "iron", "toaster",
    "paneer", "milk", "bread", "yogurt", "curd", "butter", "cheese",
    "cleaning supplies", "snacks", "diapers", "formula",
]


def _extract_products(text: str) -> List[str]:
    """Heuristic product extraction via brand + product keyword co-location."""
    products: List[str] = []
    text_lower = text.lower()

    # Check for "Brand + Product" compound mentions (e.g. "Samsung power bank")
    for brand in _PRODUCT_BRANDS:
        if brand.lower() in text_lower:
            # Try to grab the brand + following 1-4 words as a product name
            pattern = re.compile(
                rf"\b({re.escape(brand)}\s+[\w\s]{{2,40}}?)(?:\s+(?:from|on|for|worth|at|is|was|cost|ordered|received|delivered|bought)|\.|,|\s*$)",
                re.IGNORECASE,
            )
            m = pattern.search(text)
            if m:
                candidate = m.group(1).strip()
                # Trim to reasonable length
                words = candidate.split()
                if len(words) > 5:
                    candidate = " ".join(words[:5])
                if candidate not in products:
                    products.append(candidate)

    # Also match standalone product keywords
    for kw in _PRODUCT_KEYWORDS:
        if kw.lower() in text_lower and not any(kw.lower() in p.lower() for p in products):
            # Try to grab surrounding context for a richer mention
            pattern = re.compile(
                rf"\b((?:\w+\s+)?{re.escape(kw)})\b", re.IGNORECASE
            )
            m = pattern.search(text)
            if m:
                candidate = m.group(1).strip()
                if candidate not in products:
                    products.append(candidate)

    return products
