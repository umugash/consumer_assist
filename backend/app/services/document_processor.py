"""Document Processor — OCR & structured field extraction for evidence documents.

Supports PDF (via ``pdfplumber``) and image (via ``pytesseract``) inputs.
When those optional libraries are not installed, the module gracefully
falls back to sample/mock data so the rest of the pipeline keeps running.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


# ── Optional dependency probing ───────────────────────────────────────────

try:
    import pdfplumber  # type: ignore
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False

try:
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False


# ── Fallback sample data ─────────────────────────────────────────────────

SAMPLE_RECEIPT_DATA: Dict[str, Any] = {
    "vendor": "Amazon Seller Services Pvt. Ltd.",
    "invoice_date": "2026-10-25",
    "items": [
        {
            "name": "Samsung 10000mAh Power Bank",
            "quantity": 1,
            "unit_price": 2499.0,
            "total": 2499.0,
        }
    ],
    "tax": {
        "cgst": 224.91,
        "sgst": 224.91,
        "total_tax": 449.82,
    },
    "total_amount": 2499.0,
    "order_id": "402-8834521-7789234",
    "payment_method": "UPI",
    "note": (
        "This is sample/fallback data returned because the OCR libraries "
        "(pdfplumber / pytesseract) are not installed."
    ),
}


# ── Public API ────────────────────────────────────────────────────────────

def process_document(
    file_path: str,
    file_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a document (PDF or image) and return extracted text & fields.

    Args:
        file_path: Absolute or relative path to the file.
        file_type: One of ``"pdf"``, ``"image"`` / ``"png"`` / ``"jpg"`` /
            ``"jpeg"``.  When *None* the type is inferred from the extension.

    Returns:
        ``{"ocr_text": str, "extracted_fields": dict, "status": str}``
    """
    if file_type is None:
        file_type = _infer_file_type(file_path)

    # ── PDF path ──────────────────────────────────────────────────────
    if file_type == "pdf":
        return _process_pdf(file_path)

    # ── Image path ────────────────────────────────────────────────────
    if file_type in ("image", "png", "jpg", "jpeg", "tiff", "bmp"):
        return _process_image(file_path)

    # ── Unknown type ──────────────────────────────────────────────────
    return {
        "ocr_text": None,
        "extracted_fields": SAMPLE_RECEIPT_DATA,
        "status": "fallback",
        "message": f"Unsupported file type '{file_type}'. Returning sample data.",
    }


def categorize_document(text: str, filename: str, file_type: str = "") -> str:
    """Categorize document into statutory checklist categories based on OCR text and filename."""
    combined = f"{filename} {text}".lower()

    # 1. Order confirmation / invoice
    if any(k in combined for k in ["invoice", "tax invoice", "bill", "receipt", "order summary", "gstin", "billed to", "subtotal", "order confirmation"]):
        return "Order confirmation / invoice"

    # 2. Chat with customer support
    if any(k in combined for k in ["customer support", "support chat", "chat with support", "agent", "executive", "chat history", "conversation", "live chat", "ticket", "help centre"]):
        return "Chat with customer support"

    # 3. Refund request / status screenshot
    if any(k in combined for k in ["refund status", "refund requested", "refund rejected", "refund denied", "refund initiated", "refund failed", "return status", "cancellation status"]):
        return "Refund request/status screenshot"

    # 4. Payment proof (bank/UPI statement)
    if any(k in combined for k in ["utr", "upi", "debited", "credited", "payment successful", "bank statement", "transaction id", "payment proof", "gpay", "phonepe", "paytm", "netbanking", "imps", "neft"]):
        return "Payment proof (bank/UPI statement)"

    # 5. Product photo / received vs ordered
    if any(k in combined for k in ["damaged", "defective", "broken", "leak", "expired", "mrp", "batch"]):
        return "Photo of damaged/defective product"
    if file_type.lower() in ("jpg", "jpeg", "png", "webp", "image") and len(text.strip()) < 80:
        return "Photo of received item vs ordered item"

    # 6. Delivery status screenshot
    if any(k in combined for k in ["delivered", "out for delivery", "tracking", "shipment status", "courier", "awb"]):
        return "Delivery status screenshot"

    # Fallback
    return "Order confirmation / invoice" if "order" in combined else "Relevant evidentiary document"


def extract_invoice_fields(text: str) -> Dict[str, Any]:
    """Extract structured invoice/receipt fields from raw text.

    Fields returned:
        vendor, invoice_date, items, tax, total_amount, order_id

    Uses regex heuristics — no ML model required.
    """
    fields: Dict[str, Any] = {
        "vendor": _extract_vendor(text),
        "invoice_date": _extract_invoice_date(text),
        "items": _extract_line_items(text),
        "tax": _extract_tax(text),
        "total_amount": _extract_total_amount(text),
        "order_id": _extract_order_id(text),
    }
    return fields


# ── Internal: PDF processing ─────────────────────────────────────────────

def _process_pdf(file_path: str) -> Dict[str, Any]:
    if not _PDFPLUMBER_AVAILABLE:
        return {
            "ocr_text": None,
            "extracted_fields": SAMPLE_RECEIPT_DATA,
            "status": "fallback",
            "message": "pdfplumber is not installed. Returning sample data.",
        }

    if not os.path.isfile(file_path):
        return {
            "ocr_text": None,
            "extracted_fields": SAMPLE_RECEIPT_DATA,
            "status": "error",
            "message": f"File not found: {file_path}",
        }

    try:
        full_text_parts: List[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text_parts.append(page_text)

        full_text = "\n".join(full_text_parts)
        if not full_text.strip():
            return {
                "ocr_text": "",
                "extracted_fields": SAMPLE_RECEIPT_DATA,
                "status": "empty",
                "message": "PDF contained no extractable text. Returning sample data.",
            }

        extracted = extract_invoice_fields(full_text)
        return {
            "ocr_text": full_text,
            "extracted_fields": extracted,
            "status": "success",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ocr_text": None,
            "extracted_fields": SAMPLE_RECEIPT_DATA,
            "status": "error",
            "message": f"PDF processing error: {exc}",
        }


# ── Internal: Image processing ───────────────────────────────────────────

def _process_image(file_path: str) -> Dict[str, Any]:
    if not os.path.isfile(file_path):
        return {
            "ocr_text": None,
            "extracted_fields": SAMPLE_RECEIPT_DATA,
            "status": "error",
            "message": f"File not found: {file_path}",
        }

    # 1. Attempt LLM Multimodal Vision Analysis first if API key is configured
    try:
        from app.services.llm_service import analyze_document_with_vision
        vision_data = analyze_document_with_vision(file_path)
        if vision_data:
            return {
                "ocr_text": vision_data.get("ocr_text", ""),
                "extracted_fields": vision_data,
                "status": "success",
            }
    except Exception as exc:  # noqa: BLE001
        pass

    # 2. Local OCR via Tesseract if available
    if _TESSERACT_AVAILABLE:
        try:
            img = Image.open(file_path)
            full_text: str = pytesseract.image_to_string(img)
            if full_text.strip():
                extracted = extract_invoice_fields(full_text)
                return {
                    "ocr_text": full_text,
                    "extracted_fields": extracted,
                    "status": "success",
                }
        except Exception:
            pass

    # 3. Dynamic Context-Aware Fallback (extracts clues from filename)
    filename = os.path.basename(file_path)
    cat = categorize_document("", filename, _infer_file_type(file_path))

    dynamic_data: Dict[str, Any] = {
        "vendor": "E-Commerce Merchant",
        "document_type": cat,
        "filename": filename,
        "total_amount": None,
        "order_id": None,
        "status": "processed",
    }
    # Look for order ID or amounts in filename
    oid_match = re.search(r"([A-Z0-9]{8,25})", filename)
    if oid_match:
        dynamic_data["order_id"] = oid_match.group(1)

    return {
        "ocr_text": f"Uploaded document: {filename} (Processed as {cat})",
        "extracted_fields": dynamic_data,
        "status": "fallback",
    }



# ── Internal: field extraction helpers ────────────────────────────────────

def _infer_file_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    if ext == "pdf":
        return "pdf"
    if ext in ("png", "jpg", "jpeg", "tiff", "bmp", "webp"):
        return "image"
    return ext or "unknown"


def _extract_vendor(text: str) -> Optional[str]:
    """Try to pull a vendor / seller name from invoice text."""
    # Common patterns: "Sold By: <name>", "Seller: <name>", company name lines
    patterns = [
        re.compile(r"(?:Sold\s*By|Seller|Vendor|Sold\s*by)[:\s]+(.+)", re.IGNORECASE),
        re.compile(r"(?:Billed?\s*(?:By|From))[:\s]+(.+)", re.IGNORECASE),
        re.compile(r"(?:Invoice\s*From)[:\s]+(.+)", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip().split("\n")[0].strip()

    # Known platform names as fallback
    known = ["Amazon", "Flipkart", "Zepto", "Blinkit", "Swiggy"]
    text_lower = text.lower()
    for name in known:
        if name.lower() in text_lower:
            return name
    return None


def _extract_invoice_date(text: str) -> Optional[str]:
    """Extract date from invoice text."""
    patterns = [
        re.compile(
            r"(?:Invoice\s*Date|Date\s*of\s*Issue|Order\s*Date|Date)[:\s]+"
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:Invoice\s*Date|Date\s*of\s*Issue|Order\s*Date|Date)[:\s]+"
            r"(\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:Invoice\s*Date|Date\s*of\s*Issue|Order\s*Date|Date)[:\s]+"
            r"(\d{1,2}\s+\w+\s+\d{4})",
            re.IGNORECASE,
        ),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def _extract_line_items(text: str) -> List[Dict[str, Any]]:
    """Best-effort line-item extraction from invoice text."""
    items: List[Dict[str, Any]] = []
    # Pattern: quantity × description   price
    line_pat = re.compile(
        r"(\d+)\s*[x×]\s+(.+?)\s+"
        r"(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)",
        re.IGNORECASE,
    )
    for m in line_pat.finditer(text):
        qty = int(m.group(1))
        name = m.group(2).strip()
        total = float(m.group(3).replace(",", ""))
        items.append({
            "name": name,
            "quantity": qty,
            "unit_price": round(total / qty, 2) if qty else total,
            "total": total,
        })

    # Simpler fallback: "Item  ₹amount"
    if not items:
        simple_pat = re.compile(
            r"^(.{3,60}?)\s+(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in simple_pat.finditer(text):
            name = m.group(1).strip()
            # Skip header-like lines
            if any(h in name.lower() for h in ("total", "tax", "subtotal", "discount", "grand")):
                continue
            total = float(m.group(2).replace(",", ""))
            items.append({
                "name": name,
                "quantity": 1,
                "unit_price": total,
                "total": total,
            })

    return items


def _extract_tax(text: str) -> Dict[str, Any]:
    """Extract tax details from invoice text."""
    tax: Dict[str, Any] = {}
    patterns = {
        "cgst": re.compile(r"CGST[:\s@%\d.]*\s*(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)", re.IGNORECASE),
        "sgst": re.compile(r"SGST[:\s@%\d.]*\s*(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)", re.IGNORECASE),
        "igst": re.compile(r"IGST[:\s@%\d.]*\s*(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)", re.IGNORECASE),
        "gst": re.compile(r"(?<!C|S|I)GST[:\s@%\d.]*\s*(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)", re.IGNORECASE),
    }
    for key, pat in patterns.items():
        m = pat.search(text)
        if m:
            tax[key] = float(m.group(1).replace(",", ""))

    total_tax_pat = re.compile(
        r"(?:Total\s*Tax|Tax\s*Total)[:\s]*(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)",
        re.IGNORECASE,
    )
    m = total_tax_pat.search(text)
    if m:
        tax["total_tax"] = float(m.group(1).replace(",", ""))
    elif tax:
        tax["total_tax"] = sum(v for v in tax.values() if isinstance(v, (int, float)))

    return tax


def _extract_total_amount(text: str) -> Optional[float]:
    """Extract grand total / total amount from invoice text."""
    patterns = [
        re.compile(
            r"(?:Grand\s*Total|Total\s*Amount|Amount\s*Payable|Net\s*Amount|"
            r"Total\s*Due|Invoice\s*Total|Order\s*Total)[:\s]*"
            r"(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:Total)[:\s]*(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*\.?\d*)",
            re.IGNORECASE,
        ),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def _extract_order_id(text: str) -> Optional[str]:
    """Extract order ID from invoice text."""
    # Reuse the patterns from nlp_extractor
    order_patterns = [
        re.compile(r"\b(OD\d{10,})\b"),
        re.compile(r"\b(40[0-9]-\d{7}-\d{7})\b"),
        re.compile(r"\b(ZPT-\d{8}-\d+)\b"),
        re.compile(r"\b(BLINK-\d{10,})\b"),
        re.compile(r"\b(SWG-IM-\d{5,})\b"),
        re.compile(r"\b(SWG-\d+)\b"),
    ]
    for pat in order_patterns:
        m = pat.search(text)
        if m:
            return m.group(1)

    # Generic "Order ID: <value>" pattern
    generic = re.compile(
        r"(?:Order\s*(?:ID|No|Number|#))[:\s]*([A-Za-z0-9\-]+)",
        re.IGNORECASE,
    )
    m = generic.search(text)
    if m:
        return m.group(1).strip()
    return None
