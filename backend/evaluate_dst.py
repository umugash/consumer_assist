"""Measured evaluation of single-turn slot extraction and classification.

Runs the offline rules engine and the Gemini path on the same labelled
utterances and prints per-slot accuracy, classification accuracy and macro-F1.
Usage (repo root):  python backend/evaluate_dst.py [--no-llm]
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Case
import app.services.llm_service as llm

ROOT = Path(__file__).resolve().parent.parent
SLOTS = ["platform", "issue_category", "order_id", "amount", "incident_date"]

# Hand-written challenge set (authored for this project; 'yesterday' is relative to the run date).
CHALLENGE = [
    ("I bought an Amazon Pay Gift Card on Zepto for ₹1,995, but the packaging mentions ₹2,000 and the card is invalid.",
     {"platform": "Zepto", "amount": 1995.0}),
    ("I ordered groceries worth ₹523 from Zepto (ZPT-20261107-33254) and was charged above printed MRP, product shows ₹500 as MRP",
     {"platform": "Zepto", "amount": 523.0, "order_id": "ZPT-20261107-33254", "issue_category": "Hidden Charges/Overbilling"}),
    ("flipkrt never deliverd my phone worth rs 32999 order OD1122334455",
     {"platform": "Flipkart", "amount": 32999.0, "order_id": "OD1122334455", "issue_category": "Non-Delivery"}),
    ("Samsung earbuds I got from Amazon came broken, paid 2,499 on 05/11/2026",
     {"platform": "Amazon", "amount": 2499.0, "incident_date": "2026-11-05", "issue_category": "Damaged/Defective Item"}),
    ("Blinkit sent expired milk yesterday, it cost me 68 rupees",
     {"platform": "Blinkit", "amount": 68.0, "incident_date": str(date.today() - timedelta(days=1)), "issue_category": "Expired Food/Quick-Commerce Issue"}),
    ("Myntra has not refunded ₹1,299 for the shoes I returned on 1st November",
     {"platform": "Myntra", "amount": 1299.0, "incident_date": "2026-11-01", "issue_category": "Refund Delayed/Denied"}),
    ("Swiggy Instamart delivered 1 kg sugar instead of the 5 kg atta I ordered for ₹310",
     {"platform": "Swiggy", "amount": 310.0, "issue_category": "Wrong/Missing Item"}),
    ("I paid 450 on Meesho but they added a 49 rupee handling fee that wasn't shown",
     {"platform": "Meesho", "issue_category": "Hidden Charges/Overbilling"}),
    ("Amazon cancelled my order 402-1234567-1234567 and the refund of 799 is pending for 3 weeks",
     {"platform": "Amazon", "amount": 799.0, "order_id": "402-1234567-1234567", "issue_category": "Refund Delayed/Denied"}),
    ("got a apple charger frm flipkart, its fake and doesnt work, paid ₹1,900",
     {"platform": "Flipkart", "amount": 1900.0, "issue_category": "Damaged/Defective Item"}),
]


MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


def stated(text, slot, gold):
    """Gold values only count if the utterance actually states them (no credit for guessing)."""
    if gold is None:
        return False
    t = text.lower()
    if slot == "order_id":
        return str(gold).lower() in t
    if slot == "amount":
        g = float(gold)
        return any(x in t for x in (f"{g:,.0f}", f"{g:.0f}"))
    if slot == "incident_date":
        y, m, d = str(gold).split("-")
        return MONTHS[int(m) - 1] in t and any(f"{int(d)}{suf}" in t for suf in ("st", "nd", "rd", "th", " "))
    return True  # platform and category are always inferable from the text


def norm(slot, v):
    if v is None:
        return None
    if slot == "amount":
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None
    s = str(v).strip().lower()
    if slot == "platform":
        s = s.replace(" instamart", "").replace(" india", "")
    return s


def predict(text, use_llm, db):
    case = Case(status="active", workflow_stage="1. Intake & Greeting", escalation_tier="Tier 1: Platform Escalation")
    db.add(case); db.commit()
    if not use_llm:
        llm._get_api_keys = lambda: (None, None)
    res = llm.chat_with_llm(case, text, db)
    return res.get("extracted_slots", {}), res.get("provider_used")


def macro_f1(pairs):
    labels = {g for g, _ in pairs} | {p for _, p in pairs if p}
    f1s = []
    for lab in labels:
        tp = sum(1 for g, p in pairs if g == lab and p == lab)
        fp = sum(1 for g, p in pairs if g != lab and p == lab)
        fn = sum(1 for g, p in pairs if g == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def main():
    data = json.load(open(ROOT / "data" / "synthetic_indian_complaints.json", encoding="utf-8"))["complaints"]
    items = [(c["description"], {s: c.get(s) for s in SLOTS if stated(c["description"], s, c.get(s))}) for c in data] + CHALLENGE
    modes = [False] if "--no-llm" in sys.argv else [False, True]
    orig_keys = llm._get_api_keys
    report = {}
    for use_llm in modes:
        llm._get_api_keys = orig_keys
        eng = create_engine("sqlite://"); Base.metadata.create_all(eng)
        db = sessionmaker(bind=eng)()
        hits = {s: [0, 0] for s in SLOTS}
        cls_pairs, providers, rows = [], {}, []
        for text, gold in items:
            pred, prov = predict(text, use_llm, db)
            providers[prov] = providers.get(prov, 0) + 1
            for s, g in gold.items():
                if g is None:
                    continue
                hits[s][1] += 1
                ok = norm(s, pred.get(s)) == norm(s, g)
                hits[s][0] += ok
                if not ok:
                    rows.append((text[:60], s, g, pred.get(s)))
            if gold.get("issue_category"):
                cls_pairs.append((gold["issue_category"], pred.get("issue_category")))
        name = "gemini" if use_llm else "rules"
        tot_ok = sum(h[0] for h in hits.values()); tot = sum(h[1] for h in hits.values())
        report[name] = {
            "utterances": len(items), "providers": providers,
            "slot_accuracy": {s: f"{h[0]}/{h[1]}" for s, h in hits.items()},
            "overall_slot_accuracy": round(tot_ok / tot, 3),
            "classification_accuracy": round(sum(g == p for g, p in cls_pairs) / len(cls_pairs), 3),
            "classification_macro_f1": round(macro_f1(cls_pairs), 3),
            "errors": rows,
        }
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
