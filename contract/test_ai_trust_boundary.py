"""Contract: the Orchestrator keeps its §5.6 AI trust boundary — and keeps testing it.

The single most important governance invariant is that the LLM cannot become the
system of record: no unquoted booking, no AI-set price, no AI-cleared compliance.
That rule lives in ShipSmart-Orchestrator (AiClaimGuard). This contract parses that
Java source as text (keyless, cross-repo, like the rest of sibling.py) so the rule
can't be quietly deleted or hollowed out on the Java side without a Test failure.
"""

from __future__ import annotations

from sibling import JAVA, read

GUARD = JAVA / "src/main/java/com/shipsmart/api/service/AiClaimGuard.java"
GUARD_TEST = JAVA / "src/test/java/com/shipsmart/api/service/AiClaimGuardTest.java"

# The five refusal reasons that make up the boundary (evals §5.6).
REASONS = [
    "REFUSE_NO_QUOTE",
    "REFUSE_QUOTE_EXPIRED",
    "REFUSE_UNCONFIRMED",
    "REFUSE_PRICE_UNTRUSTED",
    "REFUSE_COMPLIANCE_UNVERIFIED",
]


def test_trust_boundary_source_exists():
    assert GUARD.exists(), f"AI trust boundary missing: {GUARD}"
    assert GUARD_TEST.exists(), f"AI trust boundary test missing: {GUARD_TEST}"


def test_guard_enforces_every_refusal_reason():
    src = read(GUARD)
    missing = [r for r in REASONS if f"refuse({r})" not in src]
    assert not missing, f"AiClaimGuard declares but never enforces: {missing}"


def test_guard_reprices_from_the_stored_quote_not_the_claim():
    src = read(GUARD)
    # Java wins: the price gate re-validates the claim against the stored quote, and
    # the accepted decision carries the STORED total, never the AI-claimed one.
    assert "claimedTotal().compareTo(stored.total())" in src, "price not re-validated vs stored"
    assert "Outcome.ACCEPT, OK, stored.total()" in src, "accept path does not return stored total"


def test_guard_requires_confirmation_and_verified_compliance():
    src = read(GUARD)
    assert "claim.userConfirmed()" in src, "booking does not require explicit user confirmation"
    assert "stored.complianceVerified()" in src, "AI compliance claim not checked vs the verifier"


def test_every_invariant_has_a_junit_test():
    test_src = read(GUARD_TEST)
    untested = [r for r in REASONS if r not in test_src]
    assert not untested, f"refusal reasons with no JUnit coverage: {untested}"
