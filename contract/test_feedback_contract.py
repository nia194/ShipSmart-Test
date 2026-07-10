"""Contract: the feedback loop is wired end-to-end — Web → API → AIEvent → promotion.

The Layer-6 online loop only works if all three seams hold: the Web client posts
to the endpoint the API actually serves, with the same rating vocabulary; the API
stores the comment REDACTED on the AIEvent; and the promotion pipeline consumes
that shape. Parsed as text, keyless, like every sibling contract.
"""

from __future__ import annotations

import re

from sibling import API, WEB, read

API_ROUTE = API / "app" / "api" / "routes" / "feedback.py"
API_EVENTS = API / "app" / "core" / "ai_events.py"
API_SCHEMA = API / "app" / "schemas" / "ai_event.py"
WEB_CLIENT = WEB / "src" / "lib" / "feedback-api.ts"
WEB_CONFIG = WEB / "src" / "config" / "api.ts"


def test_api_serves_the_feedback_endpoint():
    src = read(API_ROUTE)
    assert 'prefix="/feedback"' in src, "feedback router prefix changed"
    assert "feedback_enabled" in src, "feedback endpoint is no longer flag-gated"
    main = read(API / "app" / "main.py")
    assert "feedback.router" in main, "feedback router is not mounted"


def test_web_posts_to_the_same_endpoint():
    assert WEB_CLIENT.exists(), "Web feedback client missing"
    cfg = read(WEB_CONFIG)
    assert "/api/v1/feedback" in cfg, "pythonApi.feedback() no longer targets /api/v1/feedback"
    client = read(WEB_CLIENT)
    assert "pythonApi.feedback()" in client, "Web client bypasses the shared path helper"


def test_rating_vocabulary_matches_across_web_and_api():
    api_lit = re.search(r'rating:\s*Literal\[(.*?)\]', read(API_ROUTE))
    assert api_lit, "API rating Literal not found"
    api_ratings = set(re.findall(r'"([a-z]+)"', api_lit.group(1)))

    web_type = re.search(r'type FeedbackRating\s*=\s*([^;]+);', read(WEB_CLIENT))
    assert web_type, "Web FeedbackRating type not found"
    web_ratings = set(re.findall(r'"([a-z]+)"', web_type.group(1)))

    assert api_ratings == web_ratings == {"up", "down"}


def test_comment_is_redacted_onto_the_ai_event():
    assert "feedback_comment" in read(API_SCHEMA), "AIEvent lost the feedback_comment field"
    assert "feedback_comment=redact(feedback_comment)" in read(API_EVENTS), (
        "the feedback comment is no longer PII-redacted at build time"
    )


def test_comment_caps_match_across_web_and_api():
    api_cap = re.search(
        r'comment:\s*str\s*=\s*Field\(default="",\s*max_length=(\d+)\)', read(API_ROUTE)
    )
    web_cap = re.search(r"FEEDBACK_MAX_COMMENT_LENGTH\s*=\s*(\d+)", read(WEB_CLIENT))
    assert api_cap and web_cap, "comment caps not found"
    assert api_cap.group(1) == web_cap.group(1) == "2000"
