import pytest
from email_filter import validate_email_access, is_sender_allowlisted, apply_email_filter
from intake_gates import is_internal_sender, should_block_internal_sender, pre_classify_block_reason


def test_rkarnam_ceo_exception_allowed():
    """CEO exception: rkarnam@metaforgeit.com is explicitly allowed."""
    res = validate_email_access("rkarnam@metaforgeit.com")
    assert res["decision"] == "ALLOWED"
    assert is_sender_allowlisted("rkarnam@metaforgeit.com") is True

    # Filter level check
    filt = apply_email_filter(
        from_email="rkarnam@metaforgeit.com",
        body="Positions: 2\nLocation: Bangalore\nExperience: 5+ years",
        subject="Fw: Client requirement",
    )
    assert filt.allowed is True


@pytest.mark.parametrize(
    "blocked_email",
    [
        "pavani.J@metaforgeit.com",
        "rahima.s@metaforgeit.com",
        "charlie@metaforgeit.com",
        "harini.s@metaforgeit.com",
        "recruitment.application@metaforgeit.com",
        "offshorejobs@metaforgeit.com",
        "hr@metaforgeit.com",
        "admin@sub.metaforgeit.com",
        "PAVANI.J@METAFORGEIT.COM",
        " someone@metaforgeit.com ",
    ],
)
def test_all_other_metaforge_senders_completely_blocked(blocked_email):
    """Any sender from @metaforgeit.com except rkarnam@metaforgeit.com is strictly blocked."""
    # 1. Access validation check
    res = validate_email_access(blocked_email)
    assert res["decision"] == "BLOCKED"
    assert is_sender_allowlisted(blocked_email) is False

    # 2. Intake gate checks
    assert is_internal_sender(blocked_email) is True
    # Even if they forward an email, non-CEO internal senders are blocked
    assert should_block_internal_sender(blocked_email, subject="Fw: Urgent Opening") is True
    assert should_block_internal_sender(blocked_email, subject="Re: Discussion") is True
    assert should_block_internal_sender(blocked_email, subject="Requirement") is True

    # Pre-classify block check
    block_reason = pre_classify_block_reason(
        from_email=blocked_email,
        subject="Fw: New Requirement",
        body="Experience: 5 years, Location: Bangalore",
    )
    assert block_reason in ("INTERNAL_SENDER_BLOCKED", "INTERNAL_RECRUITER_BLOCK")

    # 3. Main intake gate filter
    filt = apply_email_filter(
        from_email=blocked_email,
        body="Positions: 5\nLocation: Bangalore\nExperience: 5+ years",
        subject="Fw: New Requirement",
    )
    assert filt.allowed is False
    assert "internal domain blocked" in filt.reason.lower() or "blocked" in filt.reason.lower()
