"""
Sample email threads for testing LLM extraction.

This module contains various email scenarios to test the Gemini
extraction capabilities, including:
- Clear approvals with full details
- Ambiguous language ("LGTM", "ok")
- Rejections
- Counter-offers (modified approvals)

Run directly: python -m app.test_email_samples
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# SAMPLE EMAIL THREADS
# =============================================================================

SAMPLE_EMAILS = {
    "clear_approval": """
From: john.sales@company.com
To: jane.manager@company.com
Subject: Discount Request - MedTech Corp
Date: Jan 31, 2026 4:25 PM

Hi Jane,

MedTech Corp is requesting an 18% discount for their renewal.
They have 3 SEV-1 incidents and are threatening to churn.

Can we approve?

---
Reply from jane.manager@company.com
Date: Jan 31, 2026 4:30 PM

Approved at 15%. 18% is too high given our margin.
Similar to what we did for HealthTech last month.
""",
    
    "ambiguous_approval": """
From: mike.sales@company.com
To: bob.manager@company.com
Subject: Re: HealthTech renewal
Date: Jan 15, 2026 10:00 AM

Bob, they want 15% off. Thoughts?

---
From: bob.manager@company.com
Date: Jan 15, 2026 10:15 AM

LGTM. Go ahead.
""",
    
    "simple_ok": """
From: sarah.sales@company.com
To: tom.lead@company.com
Subject: Quick approval needed - TechStart
Date: Jan 20, 2026 3:00 PM

TechStart is asking for 10% discount on their first year.
Small deal but good potential.

---
From: tom.lead@company.com
Date: Jan 20, 2026 3:05 PM

ok
""",
    
    "rejection": """
From: sarah.sales@company.com
To: lisa.vp@company.com
Subject: BioPharm discount request
Date: Jan 20, 2026 2:00 PM

Lisa,

BioPharm is asking for 25% discount. They're a small account ($180K ARR).

---
From: lisa.vp@company.com
Date: Jan 20, 2026 2:30 PM

No, that's way too high for their size. Standard renewal only.
""",
    
    "counter_offer": """
From: john.sales@company.com
To: jane.manager@company.com
Subject: FinServe Co - urgent
Date: Feb 1, 2026 9:00 AM

FinServe wants 20% or they walk.

---
From: jane.manager@company.com
Date: Feb 1, 2026 9:15 AM

20% is not happening. Offer them 12% max.

---
From: john.sales@company.com
Date: Feb 1, 2026 9:20 AM

They accepted 12%.
""",
    
    "sounds_good": """
From: alex.sales@company.com
To: pat.manager@company.com
Subject: Renewal discount - CloudCorp
Date: Jan 25, 2026 11:00 AM

CloudCorp needs 12% for the renewal. They've been a good customer for 3 years.

---
From: pat.manager@company.com
Date: Jan 25, 2026 11:30 AM

Sounds good, approve it.
""",
    
    "fine_by_me": """
From: chris.sales@company.com
To: dana.lead@company.com
Subject: DataFlow Inc discount
Date: Jan 28, 2026 2:00 PM

DataFlow is asking for 8% off. Standard request.

---
From: dana.lead@company.com
Date: Jan 28, 2026 2:15 PM

Fine by me. Process it.
"""
}


# =============================================================================
# TEST RUNNER
# =============================================================================

async def test_extraction(email_name: str, email_text: str):
    """Test extraction on a single email."""
    from .gemini_service import gemini_service
    
    print(f"\n{'='*60}")
    print(f"Test: {email_name}")
    print(f"{'='*60}")
    
    try:
        extracted = await gemini_service.extract_decision_from_email(
            email_text,
            "Test Customer"
        )
        
        print("\n✅ Extraction successful:")
        print(f"  Requested: {extracted.get('requested_discount')}")
        print(f"  Final: {extracted.get('final_discount')}")
        print(f"  Outcome: {extracted.get('outcome')}")
        print(f"  Requestor: {extracted.get('requestor_email')}")
        print(f"  Decision Maker: {extracted.get('decision_maker_email')}")
        print(f"  Reason: {extracted.get('reason')}")
        print(f"  Reasoning: {extracted.get('reasoning')}")
        
        if 'confidence' in extracted:
            avg_conf = sum(extracted['confidence'].values()) / len(extracted['confidence'])
            print(f"  Avg Confidence: {avg_conf:.2f}")
            print(f"  Confidence breakdown:")
            for field, score in extracted['confidence'].items():
                print(f"    - {field}: {score}")
        
        return True, extracted
        
    except Exception as e:
        print(f"\n❌ Extraction failed: {e}")
        return False, None


async def test_all_samples():
    """Test extraction on all sample emails."""
    from .gemini_service import gemini_service
    
    print("\n" + "="*70)
    print("🧪 Testing LLM Extraction on Sample Emails")
    print("="*70)
    
    # Check if Gemini is available
    status = gemini_service.check_status()
    print(f"\nGemini Status: {status}")
    
    if not status.get("available"):
        print("\n⚠️  Gemini not available. Please set GEMINI_API_KEY.")
        return
    
    results = {}
    
    for name, email in SAMPLE_EMAILS.items():
        success, extracted = await test_extraction(name, email)
        results[name] = {"success": success, "extracted": extracted}
    
    # Print summary
    print("\n" + "="*70)
    print("📊 Summary")
    print("="*70)
    
    successful = sum(1 for r in results.values() if r["success"])
    total = len(results)
    print(f"\n✅ Successful: {successful}/{total}")
    
    if successful < total:
        print("\n❌ Failed tests:")
        for name, result in results.items():
            if not result["success"]:
                print(f"  - {name}")
    
    # Validate specific scenarios
    print("\n" + "="*70)
    print("🔍 Validation Checks")
    print("="*70)
    
    # Check ambiguous approval handling
    if results.get("ambiguous_approval", {}).get("success"):
        outcome = results["ambiguous_approval"]["extracted"].get("outcome")
        if outcome == "approved":
            print("✅ LGTM correctly interpreted as approved")
        else:
            print(f"⚠️  LGTM interpreted as '{outcome}' (expected: approved)")
    
    # Check simple ok handling
    if results.get("simple_ok", {}).get("success"):
        outcome = results["simple_ok"]["extracted"].get("outcome")
        if outcome == "approved":
            print("✅ 'ok' correctly interpreted as approved")
        else:
            print(f"⚠️  'ok' interpreted as '{outcome}' (expected: approved)")
    
    # Check rejection handling
    if results.get("rejection", {}).get("success"):
        outcome = results["rejection"]["extracted"].get("outcome")
        if outcome == "rejected":
            print("✅ Rejection correctly identified")
        else:
            print(f"⚠️  Rejection interpreted as '{outcome}' (expected: rejected)")
    
    # Check counter-offer handling
    if results.get("counter_offer", {}).get("success"):
        extracted = results["counter_offer"]["extracted"]
        requested = extracted.get("requested_discount")
        final = extracted.get("final_discount")
        outcome = extracted.get("outcome")
        if outcome in ["modified", "approved"] and "12" in str(final):
            print(f"✅ Counter-offer handled: {requested} -> {final} as '{outcome}'")
        else:
            print(f"⚠️  Counter-offer: {requested} -> {final} as '{outcome}' (expected modified/approved at 12%)")


async def test_single(email_name: str):
    """Test a single sample by name."""
    if email_name not in SAMPLE_EMAILS:
        print(f"Unknown sample: {email_name}")
        print(f"Available: {list(SAMPLE_EMAILS.keys())}")
        return
    
    await test_extraction(email_name, SAMPLE_EMAILS[email_name])


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Run specific test
        asyncio.run(test_single(sys.argv[1]))
    else:
        # Run all tests
        asyncio.run(test_all_samples())
