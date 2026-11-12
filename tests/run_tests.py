"""Run every check that does not need an API key.

    ./.venv/bin/python tests/run_tests.py

Covers the JSON schema, the scoring maths, the markdown renderer, and the whole
Claude API call path against a mocked HTTP transport — request payloads, SSE
parsing, pause_turn resumption, refusals, and the fallback-beta retry.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

import anthropic
from nomad_scout import client as api
from nomad_scout import criteria, prompts, report, schema, scoring

PASSED = []
FAILED = []


def check(label, fn):
    try:
        fn()
    except Exception as err:  # noqa: BLE001 - a test runner should catch everything
        FAILED.append((label, err))
        print("FAIL  {label}\n        {err}".format(label=label, err=err))
    else:
        PASSED.append(label)
        print("ok    " + label)


# --- fixtures ---------------------------------------------------------------

FINDINGS = {
    "city": "Testville",
    "country": "Testland",
    "bottom_line": "Testville works. Target Old Quarter.",
    "best_neighborhood": "Old Quarter",
    "neighborhoods": [
        {
            "name": "Old Quarter", "verdict": "sweet_spot",
            "hai_chau_comparison": "About the same | a bit more local",
            "rent_band_usd": "$400-650", "why": "Walkable and residential.",
            "downsides": "Market noise from 5am.", "best_for": "A working couple.",
            "ratings": {"internet": 9, "cafe_access": 8, "fitness_access": 9, "vibe": 9,
                        "furnished_stock": 7, "price_value": 8, "quiet": 5, "safety": 8},
        },
        {
            "name": "Beachside", "verdict": "avoid", "hai_chau_comparison": "Toward Son Tra",
            "rent_band_usd": "$700-1,100", "why": "Views.", "downsides": "Tourist pricing.",
            "best_for": "Visitors.",
            "ratings": {"internet": 6, "cafe_access": 4, "fitness_access": 2, "vibe": 2,
                        "furnished_stock": 6, "price_value": 2, "quiet": 4, "safety": 7},
        },
    ],
    "fitness": [{
        "name": "Old Quarter Park", "neighborhood": "Old Quarter", "address": "12 Test St",
        "maps_query": "Old Quarter Park, Testville", "walk_minutes": 7, "rating": 4.4,
        "hours": "24h", "fits": "Pull-up bars by the running loop.",
        "caveat": "Busy after school.", "confidence": "confirmed",
        "equipment": ["pull-up bars", "parallel bars"], "has_pullup_bars": True,
        "has_parallel_bars": True, "cost": "free",
    }, {
        "name": "Unconfirmed Gym", "neighborhood": "Old Quarter", "address": "unknown",
        "maps_query": "Unconfirmed Gym Testville", "walk_minutes": None, "rating": None,
        "hours": "unknown", "fits": "One forum post.", "caveat": "Could not confirm.",
        "confidence": "unverified", "equipment": [], "has_pullup_bars": False,
        "has_parallel_bars": False, "cost": "$3/day reported",
    }],
    "cafes": [{
        "name": "Cafe One", "neighborhood": "Old Quarter", "address": "4 Test Ln",
        "maps_query": "Cafe One Testville", "walk_minutes": 4, "rating": 4.6,
        "hours": "07:00-21:00", "fits": "Big tables, outlets.", "caveat": "Busy after 11am.",
        "confidence": "confirmed", "opens_at": "07:00", "outlets": "at_most_tables",
        "laptop_friendly": "No time limit.",
    }],
    "food": [{
        "name": "Market Alley", "neighborhood": "Old Quarter", "address": "Market Alley",
        "maps_query": "Market Alley Testville", "walk_minutes": 3, "rating": 4.5,
        "hours": "06:00-14:00", "fits": "Local breakfast.", "caveat": "Cash only.",
        "confidence": "likely", "price_range": "$0.80", "kind": "street_food",
    }],
    "housing": {
        "price_bands": "$400-650 for a furnished 1BR.",
        "where_to_look": [{"name": "Testville Expats", "kind": "facebook_group",
                           "url": "https://example.com", "notes": "Post a want ad."}],
        "lease_norms": "6 months, 1 month deposit.",
        "negotiation_notes": "15% off is normal.",
        "red_flags": ["Deposits before viewing"],
    },
    "transit": "Walkable.", "connectivity": "100/50 Mbps for $9.",
    "cost_of_living": "$1,400/mo for two.", "visa_notes": "90-day e-visa.",
    "pre_arrival_checklist": [
        {"phase": "research", "task": "Join Testville Expats", "why": "Best listings are there."},
        {"phase": "viewing", "task": "Check 5am market noise", "why": "Top local complaint."},
    ],
    "watch_outs": ["Wet season Sept-Nov."],
    "sources": ["https://example.com/guide"],
}


def _sse(text, stop_reason="end_turn", stop_details=None):
    msg = {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5",
           "content": [], "stop_reason": None, "stop_sequence": None,
           "usage": {"input_tokens": 100, "output_tokens": 0}}
    events = [
        ("message_start", {"type": "message_start", "message": msg}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": stop_reason, "stop_sequence": None,
                                     "stop_details": stop_details},
                           "usage": {"output_tokens": 50}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join("event: {n}\ndata: {d}\n\n".format(n=n, d=json.dumps(p)) for n, p in events)


def _stream_response(text, **kwargs):
    return httpx.Response(200, text=_sse(text, **kwargs), headers={"content-type": "text/event-stream"})


def _mock_client(handler):
    return anthropic.Anthropic(api_key="sk-ant-test",
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)))


# --- schema -----------------------------------------------------------------

def _walk_schema(node, path="root"):
    problems = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                problems.append(path + ": missing additionalProperties:false")
            if set(node.get("properties", {})) != set(node.get("required", [])):
                problems.append(path + ": required does not match properties")
        for banned in ("minimum", "maximum", "minLength", "maxLength", "multipleOf", "minItems"):
            if banned in node:
                problems.append("{p}: unsupported constraint '{b}'".format(p=path, b=banned))
        for key, value in node.items():
            problems += _walk_schema(value, "{p}.{k}".format(p=path, k=key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            problems += _walk_schema(value, "{p}[{i}]".format(p=path, i=i))
    return problems


def test_schema_is_api_compatible():
    problems = _walk_schema(schema.FINDINGS_SCHEMA)
    assert not problems, "; ".join(problems)


def test_schema_covers_every_rating():
    assert set(schema.RATING_KEYS) == set(scoring.RATING_TO_CRITERION)


# --- scoring ----------------------------------------------------------------

def test_weights_sum_to_100():
    assert sum(criteria.SCORECARD_WEIGHTS.values()) == 100


def test_score_bounds():
    perfect = {k: 10 for k in criteria.SCORECARD_WEIGHTS}
    assert scoring.weighted_score(perfect) == 100.0
    assert scoring.weighted_score({}) == 0.0
    assert scoring.weighted_score({k: 99 for k in criteria.SCORECARD_WEIGHTS}) == 100.0, "must clamp"
    assert scoring.weighted_score({k: -5 for k in criteria.SCORECARD_WEIGHTS}) == 0.0, "must clamp"


def test_verdict_bands():
    assert scoring.verdict(100) == "BOOK IT"
    assert scoring.verdict(80) == "BOOK IT"
    assert scoring.verdict(79.9) == "GOOD"
    assert scoring.verdict(65) == "GOOD"
    assert scoring.verdict(50) == "MAYBE"
    assert scoring.verdict(49.9) == "PASS"


def test_neighborhood_fit_ranks_correctly():
    good = scoring.neighborhood_fit(FINDINGS["neighborhoods"][0]["ratings"])
    bad = scoring.neighborhood_fit(FINDINGS["neighborhoods"][1]["ratings"])
    assert good > bad, (good, bad)
    assert 0 <= bad < good <= 100


def test_weakest_finds_the_biggest_loss():
    losses = scoring.weakest({"wifi": 10, "cafe": 10, "fitness": 0, "vibe": 10,
                              "furnished": 10, "price": 10, "quiet": 10, "safety": 10})
    assert losses[0][0] == criteria.SCORECARD_LABELS["fitness"]


# --- renderer ---------------------------------------------------------------

def test_report_renders_every_section():
    out = report.render(FINDINGS)
    for heading in ["## Bottom line", "## Neighborhoods", "## Outdoor fitness", "## Working cafes",
                    "## Food & groceries", "## Housing", "## Logistics", "## Watch-outs",
                    "## Pre-arrival checklist", "## Sources"]:
        assert heading in out, "missing " + heading
    assert "Old Quarter Park" in out and "Cafe One" in out


def test_tables_have_no_blank_rows():
    """A blank line inside a markdown table silently breaks it."""
    lines = report.render(FINDINGS).split("\n")
    for i, line in enumerate(lines[:-2]):
        if line.startswith("|") and lines[i + 1].strip() == "" and lines[i + 2].startswith("|"):
            raise AssertionError("blank line splits a table at line {i}: {l}".format(i=i, l=line))


def test_pipes_are_escaped():
    out = report.render(FINDINGS)
    assert "About the same \\| a bit more local" in out


def test_missing_fitness_is_called_out():
    stripped = dict(FINDINGS, fitness=[])
    assert "No outdoor fitness found" in report.render(stripped)


def test_report_survives_a_sparse_findings_object():
    report.render({"city": "Bare", "bottom_line": "Nothing found."})


def test_unverified_places_are_flagged():
    out = report.render(FINDINGS)
    assert "UNVERIFIED" in out


def test_scorecard_totals_match_the_breakdown():
    scores = {"wifi": 9, "cafe": 8, "fitness": 7, "vibe": 9,
              "furnished": 10, "price": 6, "quiet": 5, "safety": 8}
    card = report.render_scorecard("Unit 4B", scores)
    total = scoring.weighted_score(scores)
    assert "{t}/100".format(t=total) in card
    assert scoring.verdict(total) in card


# --- prompts ----------------------------------------------------------------

def test_system_prompt_carries_the_criteria():
    text = prompts.system_prompt()
    for needle in ["Hai Chau", "$800", "30+ Mbps", "Pull-up bars", "8-9am"]:
        assert needle in text, "system prompt is missing: " + needle


def test_research_prompt_uses_the_neighborhoods():
    text = prompts.research_prompt("Osaka", ["Nakatsu", "Nishinakajima"], budget=750)
    assert "Nakatsu" in text and "Nishinakajima" in text and "$750" in text


# --- API path (mocked transport) --------------------------------------------

def test_research_and_extract_round_trip():
    captured = []
    state = {"n": 0}

    def handler(request):
        captured.append(json.loads(request.content))
        state["n"] += 1
        if state["n"] == 1:
            return _stream_response("Old Quarter is the pick.")
        return _stream_response(json.dumps({"city": "Testville", "best_neighborhood": "Old Quarter"}))

    client = _mock_client(handler)
    text = api.research(client, prompts.system_prompt(), prompts.research_prompt("Testville"), progress=False)
    assert "Old Quarter is the pick" in text

    found = api.extract(client, "extract this", schema.FINDINGS_SCHEMA)
    assert found["best_neighborhood"] == "Old Quarter"

    research_req, extract_req = captured
    assert research_req["model"] == api.MODEL
    assert research_req["stream"] is True
    assert research_req["fallbacks"] == "default"
    assert [t["type"] for t in research_req["tools"]] == ["web_search_20260209", "web_fetch_20260209"]
    assert research_req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in research_req, "leave thinking at the Opus 5 default"
    assert "tools" not in extract_req, "the extraction pass must not carry tools"
    assert extract_req["output_config"]["format"]["type"] == "json_schema"


def test_fallback_beta_reaches_the_header():
    seen = {}

    def handler(request):
        seen["beta"] = request.headers.get("anthropic-beta")
        return _stream_response("hi")

    api.research(_mock_client(handler), "sys", "prompt", progress=False)
    assert api.FALLBACK_BETA in (seen.get("beta") or "")


def test_pause_turn_resumes():
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] == 1:
            return _stream_response("Part one. ", stop_reason="pause_turn")
        return _stream_response("Part two.")

    text = api.research(_mock_client(handler), "sys", "prompt", progress=False)
    assert "Part one." in text and "Part two." in text
    assert state["n"] == 2


def test_refusal_raises_with_the_category():
    def handler(request):
        return _stream_response("", stop_reason="refusal", stop_details={
            "type": "refusal", "category": "cyber", "explanation": "nope"})

    try:
        api.research(_mock_client(handler), "sys", "prompt", progress=False)
    except api.ScoutError as err:
        assert "declined" in str(err) and "cyber" in str(err)
    else:
        raise AssertionError("a refusal should raise ScoutError")


def test_missing_fallback_beta_retries_without_it():
    state = {"bodies": []}

    def handler(request):
        body = json.loads(request.content)
        state["bodies"].append(body)
        if "fallbacks" in body:
            return httpx.Response(400, json={"type": "error", "error": {
                "type": "invalid_request_error", "message": "fallbacks: unsupported beta"}})
        return _stream_response("Worked without fallbacks.")

    text = api.research(_mock_client(handler), "sys", "prompt", progress=False)
    assert "Worked without fallbacks" in text
    assert len(state["bodies"]) == 2 and "fallbacks" not in state["bodies"][1]


def test_other_errors_surface_plainly():
    cases = [
        (httpx.Response(400, json={"type": "error", "error": {
            "type": "invalid_request_error", "message": "max_tokens: too large"}}), "max_tokens"),
        (httpx.Response(401, json={"type": "error", "error": {
            "type": "authentication_error", "message": "bad key"}}), "ANTHROPIC_API_KEY was rejected"),
        (httpx.Response(429, json={"type": "error", "error": {
            "type": "rate_limit_error", "message": "slow down"}}), "Rate limited"),
    ]
    for response, needle in cases:
        client = _mock_client(lambda request, r=response: r)
        try:
            api.research(client, "sys", "prompt", progress=False)
        except api.ScoutError as err:
            assert needle in str(err), "expected '{n}' in: {e}".format(n=needle, e=err)
        else:
            raise AssertionError("expected ScoutError for " + needle)


def test_truncated_extraction_is_reported():
    def handler(request):
        return _stream_response('{"city": "Half', stop_reason="max_tokens")

    try:
        api.extract(_mock_client(handler), "extract", schema.FINDINGS_SCHEMA)
    except api.ScoutError as err:
        assert "cut off" in str(err)
    else:
        raise AssertionError("a truncated response should raise")


def test_missing_api_key_message():
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        api.build_client()
    except api.ScoutError as err:
        assert "ANTHROPIC_API_KEY is not set" in str(err)
    else:
        raise AssertionError("should refuse to build a client without a key")
    finally:
        if saved:
            os.environ["ANTHROPIC_API_KEY"] = saved


# --- run --------------------------------------------------------------------

if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        check(name[5:].replace("_", " "), fn)
    print("\n{p} passed, {f} failed".format(p=len(PASSED), f=len(FAILED)))
    sys.exit(1 if FAILED else 0)
