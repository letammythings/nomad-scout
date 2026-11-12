"""Thin wrapper over the Claude API for the two calls this tool makes."""

import json
import os
import sys
from typing import Any, Dict, List, Optional

import anthropic

MODEL = "claude-opus-5"

# Opus 5 safety classifiers can decline a request; server-side fallbacks re-serve
# it on Opus 4.8 inside the same call. Dropped automatically if the account does
# not have the beta.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 18}
WEB_FETCH_TOOL = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 12}

MAX_PAUSE_RESUMES = 6


class ScoutError(RuntimeError):
    """Anything that should stop the run with a message the user can act on."""


def build_client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ScoutError(
            "ANTHROPIC_API_KEY is not set.\n"
            "  Get a key at https://console.anthropic.com/settings/keys, then:\n"
            "    export ANTHROPIC_API_KEY='sk-ant-...'\n"
            "  Or put it in a .env file next to this project (see .env.example)."
        )
    # 20 minutes: a deep research pass with many searches is a long single request.
    return anthropic.Anthropic(timeout=1200.0)


def _is_fallback_beta_error(err: Exception) -> bool:
    """A 400 that mentions fallbacks means this account cannot use the beta.

    The request is identical without it, so retrying is always safe — the only
    thing lost is automatic re-serving of a declined request on Opus 4.8.
    """
    return "fallback" in str(err).lower()


def _text_of(message: Any) -> str:
    return "\n".join(b.text for b in message.content if getattr(b, "type", None) == "text").strip()


def _describe_refusal(message: Any) -> str:
    details = getattr(message, "stop_details", None)
    category = getattr(details, "category", None) if details else None
    explanation = getattr(details, "explanation", None) if details else None
    parts = ["The model declined this request."]
    if category:
        parts.append("Category: {c}.".format(c=category))
    if explanation:
        parts.append(explanation)
    parts.append("Try rephrasing the city or neighborhood, or narrowing the request.")
    return " ".join(parts)


def research(
    client: anthropic.Anthropic,
    system: str,
    prompt: str,
    effort: str = "high",
    max_tokens: int = 32000,
    progress: bool = True,
) -> str:
    """Run the web-search research pass and return the report text.

    Streams so a multi-minute request cannot hit an HTTP timeout, and resumes
    automatically when the server-side search loop reports `pause_turn`.
    """
    messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
    use_fallbacks = True
    collected: List[str] = []

    for attempt in range(MAX_PAUSE_RESUMES + 1):
        kwargs: Dict[str, Any] = dict(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL],
            output_config={"effort": effort},
            betas=[],
        )
        if use_fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        try:
            with client.beta.messages.stream(**kwargs) as stream:
                for event in stream:
                    if not progress:
                        continue
                    if event.type == "content_block_start" and event.content_block.type == "server_tool_use":
                        sys.stderr.write(".")
                        sys.stderr.flush()
                message = stream.get_final_message()
        except anthropic.BadRequestError as err:
            if use_fallbacks and _is_fallback_beta_error(err):
                # Account lacks the fallback beta — retry without it.
                use_fallbacks = False
                continue
            raise ScoutError("The API rejected the request: {err}".format(err=err))
        except anthropic.AuthenticationError:
            raise ScoutError("ANTHROPIC_API_KEY was rejected. Check the key is current and has credit.")
        except anthropic.RateLimitError:
            raise ScoutError("Rate limited by the API. Wait a minute and run it again.")
        except anthropic.APIConnectionError as err:
            raise ScoutError("Could not reach the API: {err}".format(err=err))

        if message.stop_reason == "refusal":
            raise ScoutError(_describe_refusal(message))

        text = _text_of(message)
        if text:
            collected.append(text)

        if message.stop_reason != "pause_turn":
            if progress:
                sys.stderr.write("\n")
            break

        # The server-side search loop hit its iteration cap. Echo the turn back
        # verbatim and it resumes where it stopped.
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": message.content},
        ]
    else:
        if progress:
            sys.stderr.write("\n")

    report = "\n\n".join(collected).strip()
    if not report:
        raise ScoutError("The research pass returned no text. Try again, or lower --effort.")
    return report


def extract(
    client: anthropic.Anthropic,
    prompt: str,
    schema: Dict[str, Any],
    max_tokens: int = 16000,
) -> Dict[str, Any]:
    """Second pass: turn the report prose into the structured findings object.

    Runs without tools on a fresh message list so no web-search citation blocks
    reach a request that uses `output_config.format`.
    """
    use_fallbacks = True
    while True:
        kwargs: Dict[str, Any] = dict(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            betas=[],
        )
        if use_fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        try:
            with client.beta.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
        except anthropic.BadRequestError as err:
            if use_fallbacks and _is_fallback_beta_error(err):
                use_fallbacks = False
                continue
            raise ScoutError("The API rejected the extraction request: {err}".format(err=err))

        if message.stop_reason == "refusal":
            raise ScoutError(_describe_refusal(message))
        if message.stop_reason == "max_tokens":
            raise ScoutError(
                "The structured output was cut off. Re-run with a narrower scope "
                "(fewer neighborhoods) or raise --max-tokens."
            )

        text = _text_of(message)
        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            raise ScoutError("Could not parse the structured output as JSON: {err}".format(err=err))


def load_dotenv(path: str) -> None:
    """Minimal .env loader so the tool works without extra dependencies."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
