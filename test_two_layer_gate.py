import pytest
from email_filter import is_sender_allowlisted, has_requirement_structure, apply_email_filter


def test_is_sender_allowlisted():
    # Allowed domains & subdomains
    assert is_sender_allowlisted("user@ltts.com") is True
    assert is_sender_allowlisted("sub.user@kpmg.com") is True
    assert is_sender_allowlisted("recruiter@itcinfotech.com") is True
    assert is_sender_allowlisted("anusha.k@iexcel.co.in") is True
    assert is_sender_allowlisted("vaishnavi.g@idexcel.com") is True
    assert is_sender_allowlisted("test@deloitte.com") is False
    assert is_sender_allowlisted("contact@iexcel.com") is False

    # Allowed CEO email
    assert is_sender_allowlisted("rkarnam@metaforgeit.com") is True

    # Blocked senders (internal staff except CEO, external non-client senders)
    assert is_sender_allowlisted("rahima.s@metaforgeit.com") is False
    assert is_sender_allowlisted("harini.s@metaforgeit.com") is False
    assert is_sender_allowlisted("charlie@metaforgeit.com") is False
    assert is_sender_allowlisted("spam@otherdomain.com") is False


def test_has_requirement_structure():
    # Position count
    assert has_requirement_structure("We have 3 positions open in Bangalore.") is True
    assert has_requirement_structure("Urgent: 2 openings for React Developer") is True

    # Experience / skills
    assert has_requirement_structure("Mandatory skills: Python, Django") is True
    assert has_requirement_structure("Required skills: Java, AWS") is True
    assert has_requirement_structure("Candidate must have 5+ yrs experience") is True
    assert has_requirement_structure("Experience: 8-10 years") is True

    # Structured JD headers
    assert has_requirement_structure("Role Title: Senior Java Developer\nLocation: Hybrid") is True
    assert has_requirement_structure("Job Description:\nWe are hiring for a Data Scientist.") is True

    # Plain reply without requirement structure
    assert has_requirement_structure("Please find attached resume for review.") is False
    assert has_requirement_structure("Thanks, I sent 3 profiles to the client today.") is False
