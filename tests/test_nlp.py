"""Unit and regression tests for NLP Extractor, Entity Recognition, and Normalization."""

import pytest
from app.services.nlp_extractor import (
    classify_complaint,
    extract_entities,
    normalize_date,
    extract_all,
)


def test_classify_complaint_categories():
    """Verify classification across major Indian e-commerce complaints."""
    test_cases = [
        ("I ordered on Amazon and it was never delivered", "Non-Delivery"),
        ("The speaker has a cracked body and distorted sound", "Damaged/Defective Item"),
        ("Received someone else's order containing diapers instead of groceries", "Wrong/Missing Item"),
        ("Zepto delivered expired milk and paneer", "Expired Food/Quick-Commerce Issue"),
        ("Cancelled order 3 weeks ago but refund delayed and no response", "Refund Delayed/Denied"),
        ("Amazon added an extra 700 handling fee not shown at checkout", "Hidden Charges/Overbilling"),
    ]

    for text, expected in test_cases:
        res = classify_complaint(text)
        assert res["category"] == expected, f"Failed for '{text}': got {res['category']}, expected {expected}"
        assert res["confidence"] > 0.0


def test_entity_extraction_platforms():
    """Test extraction of Indian e-commerce & quick commerce platform names."""
    samples = [
        ("Placed an order on Amazon India yesterday", "Amazon"),
        ("Flipkart delivery is delayed", "Flipkart"),
        ("Zepto delivered rotten vegetables", "Zepto"),
        ("Blinkit sent wrong items", "Blinkit"),
        ("Swiggy Instamart cancelled without refund", "Swiggy Instamart"),
    ]
    for text, expected_plat in samples:
        entities = extract_entities(text)
        plat_entities = [e["value"] for e in entities if e["type"] == "PLATFORM"]
        assert expected_plat in plat_entities, f"Expected {expected_plat} in {plat_entities}"


def test_entity_extraction_amounts():
    """Test extraction of monetary amounts in INR / ₹."""
    samples = [
        ("I was charged ₹2,499.00 for the order", 2499.0),
        ("Paid Rs. 15999 for this item", 15999.0),
        ("Total amount was 346 rupees", 346.0),
    ]
    for text, expected_val in samples:
        entities = extract_entities(text)
        amt_entities = [e.get("normalized") or e.get("normalized_value") for e in entities if e["type"] == "AMOUNT"]
        # Can match either 'INR 2499.0' or '2499.0'
        assert any(str(expected_val) in str(val) for val in amt_entities), f"Expected {expected_val} in {amt_entities}"


def test_entity_extraction_order_ids():
    """Test platform-specific Order ID extraction patterns."""
    samples = [
        ("Order 402-8834521-7789234 was not received", "402-8834521-7789234"),
        ("My Flipkart tracking OD432876512349876", "OD432876512349876"),
        ("Zepto order id ZPT-20261108-44821", "ZPT-20261108-44821"),
        ("Blinkit ref BLINK-2026110522187", "BLINK-2026110522187"),
    ]
    for text, expected_oid in samples:
        entities = extract_entities(text)
        oids = [e["value"] for e in entities if e["type"] == "ORDER_ID"]
        assert expected_oid in oids, f"Expected {expected_oid} in {oids}"


def test_date_normalization():
    """Verify normalization of various Indian and natural date strings to ISO YYYY-MM-DD."""
    assert normalize_date("October 25th 2026") == "2026-10-25"
    assert normalize_date("Nov 2 2026") == "2026-11-02"
    assert normalize_date("2026-11-08") == "2026-11-08"
    assert normalize_date("05 aug 2026") == "2026-08-05"
    assert normalize_date("order placed at 05 aug 2026") == "2026-08-05"
    assert normalize_date("August 5th") is not None
    assert normalize_date("5/8/2026") == "2026-08-05"
