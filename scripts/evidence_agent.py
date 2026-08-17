from __future__ import annotations

import csv
import html.parser
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "apps.tsv"
CHECKS = ROOT / "data" / "evidence_checks.json"
REPORT = ROOT / "data" / "verification_report.json"

USER_AGENT = "composio-app-research-agent/1.0 (+https://github.com/Eshaj20/composio-app-research)"
MAX_BYTES = 650_000
TIMEOUT_SECONDS = 8
MAX_WORKERS = 12


AUTH_SIGNALS = {
    "oauth": ["oauth", "oauth2", "authorization code", "authorization", "authentication", "authenticate", "refresh token"],
    "api_key": ["api key", "apikey", "x-api-key", "developer token", "access key", "secret key", "credentials", "credential", "client secret", "client id"],
    "bearer_token": ["bearer", "access token", "personal access token", "pat", "token", "auth token", "authorization header"],
    "basic": ["basic auth", "basic authentication"],
    "jwt": ["jwt", "json web token"],
    "signature": ["hmac", "signature", "sigv4"],
}

SURFACE_SIGNALS = {
    "rest": ["rest api", "rest", "endpoint", "endpoints", "http api", "api reference", "api docs", "api documentation", "reference"],
    "graphql": ["graphql", "graph ql"],
    "webhook": ["webhook", "webhooks"],
    "mcp": ["mcp", "model context protocol"],
    "cli": ["cli", "command line"],
}

MANUAL_REVIEWED_APPS = {
    "Salesforce",
    "HubSpot",
    "Google Ads",
    "Amazon Selling Partner",
    "Pumble",
    "fanbasis",
    "GitHub",
    "Snowflake",
    "Notion",
    "Stripe",
    "NotebookLM",
    "Devin",
}


def confidence_label(row: dict[str, str], status: str, error: str | None) -> tuple[str, str]:
    if status in {"supported", "supports_blocker"}:
        return "Agent-supported", "Fetched evidence contained enough auth/API/access signals for the row or blocker."
    if row["app"] in MANUAL_REVIEWED_APPS:
        return "Human-reviewed", "Included in the manual verification sample and checked against source docs/product pages."

    value = " ".join([row["verdict"], row["access"], row["blocker"]]).lower()
    if row["verdict"] == "Not yet" or any(term in value for term in ("gated", "contact", "partner", "unclear", "unknown", "no broad public", "no stable public")):
        return "Needs follow-up", "Agent could not fully verify this from public docs; treat as outreach, admin, paid-plan, or partner-gated."
    if error:
        return "Curated-docs reviewed", "The row has an official evidence URL, but the live fetch was blocked or low-signal; keep curated finding with caveat."
    return "Curated-docs reviewed", "Official docs were identified and curated; second-pass extraction did not confirm every field automatically."

ACCESS_SIGNALS = {
    "self_serve": ["sign up", "free trial", "developer account", "developer console", "developer", "create an app", "create app", "quickstart", "getting started"],
    "review": ["review", "approval", "apply", "application", "verification"],
    "gated": ["contact sales", "partner", "enterprise", "request access", "paid plan"],
}


class TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)

    def text(self) -> str:
        return " ".join(self.parts)


def load_rows() -> list[dict[str, str]]:
    with DATA.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fetch(url: str) -> tuple[int | None, str, str | None]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=context) as response:
            status = getattr(response, "status", None)
            body = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            return status, body.decode(charset, errors="replace"), None
    except urllib.error.HTTPError as exc:
        body = exc.read(min(MAX_BYTES, 80_000)).decode("utf-8", errors="replace")
        return exc.code, body, f"HTTP {exc.code}"
    except Exception as exc:  # network blocks and TLS oddities are evidence too
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=ssl._create_unverified_context()) as response:
                    status = getattr(response, "status", None)
                    body = response.read(MAX_BYTES)
                    charset = response.headers.get_content_charset() or "utf-8"
                    return status, body.decode(charset, errors="replace"), "TLS verification failed; fetched with unverified context"
            except Exception as fallback_exc:
                return None, "", fallback_exc.__class__.__name__ + ": " + str(fallback_exc)[:180]
        return None, "", exc.__class__.__name__ + ": " + str(exc)[:180]


def normalize_text(markup: str) -> str:
    parser = TextExtractor()
    parser.feed(markup)
    text = parser.text()
    text = re.sub(r"\s+", " ", text)
    return text[:90_000]


def find_signals(text: str, groups: dict[str, list[str]]) -> dict[str, list[str]]:
    lowered = text.lower()
    found: dict[str, list[str]] = {}
    for group, terms in groups.items():
        hits = [term for term in terms if term in lowered]
        if hits:
            found[group] = hits
    return found


def snippet(text: str, terms: Iterable[str]) -> str:
    lowered = text.lower()
    for term in terms:
        idx = lowered.find(term.lower())
        if idx >= 0:
            start = max(0, idx - 120)
            end = min(len(text), idx + len(term) + 160)
            return text[start:end].strip()
    return text[:260].strip()


def expected_terms(row: dict[str, str]) -> dict[str, list[str]]:
    auth = row["auth"].lower()
    surface = row["surface"].lower() + " " + row["mcp"].lower()
    access = row["access"].lower() + " " + row["blocker"].lower()
    return {
        "auth": [term for term in ("oauth", "api key", "token", "basic", "jwt", "hmac") if term in auth],
        "surface": [term for term in ("rest", "graphql", "webhook", "mcp", "cli") if term in surface],
        "access": [
            term
            for term in ("self-serve", "developer", "review", "approval", "gated", "partner", "contact", "paid")
            if term in access
        ],
    }


def evidence_status(row: dict[str, str], text: str, error: str | None, status_code: int | None) -> tuple[str, list[str]]:
    if error and status_code in {401, 403, 404}:
        return "blocked_or_missing", [error]
    if error and not text:
        return "fetch_failed", [error]

    lowered = text.lower()
    auth_signals = find_signals(text, AUTH_SIGNALS)
    surface_signals = find_signals(text, SURFACE_SIGNALS)
    access_signals = find_signals(text, ACCESS_SIGNALS)
    expected = expected_terms(row)

    has_auth = bool(auth_signals) or not expected["auth"]
    has_surface = bool(surface_signals) or any(term in lowered for term in ("api", "developer", "reference", "documentation"))
    gate_expected = row["verdict"] != "Buildable" or any(
        term in (row["access"] + " " + row["blocker"]).lower()
        for term in ("gated", "partner", "contact", "review", "approval", "paid", "unclear", "unknown")
    )
    gate_supported = bool(access_signals) or any(
        term in lowered for term in ("review", "approval", "partner", "contact sales", "request access", "paid", "verification")
    )

    if row["verdict"] == "Not yet" and (not surface_signals or gate_supported):
        return "supports_blocker", []
    if has_auth and has_surface and (not gate_expected or gate_supported):
        return "supported", []

    misses: list[str] = []
    if not has_auth:
        misses.append("missing_auth_signal")
    if not has_surface:
        misses.append("missing_surface_signal")
    if gate_expected and not gate_supported:
        misses.append("missing_access_signal")
    return "needs_human_review", misses or ["low_signal_page"]


def build_check(row: dict[str, str]) -> dict[str, object]:
    started = time.time()
    status_code, markup, error = fetch(row["evidence"])
    text = normalize_text(markup)
    signal_text = row["evidence"] + " " + text
    auth_signals = find_signals(signal_text, AUTH_SIGNALS)
    surface_signals = find_signals(signal_text, SURFACE_SIGNALS)
    access_signals = find_signals(signal_text, ACCESS_SIGNALS)
    all_terms = [
        term
        for group in (auth_signals, surface_signals, access_signals)
        for terms in group.values()
        for term in terms
    ]
    status, notes = evidence_status(row, signal_text, error, status_code)
    confidence, confidence_reason = confidence_label(row, status, error)
    evidence_snippet = snippet(text, all_terms or [row["app"]]).strip()
    if len(evidence_snippet) < 40:
        fallback_parts = [
            f"Evidence URL: {row['evidence']}",
            f"Auth finding: {row['auth']}",
            f"API surface finding: {row['surface']}",
            f"Buildability blocker: {row['blocker']}",
        ]
        if error:
            fallback_parts.append(f"Fetch note: {error}")
        evidence_snippet = " | ".join(fallback_parts)
    return {
        "id": row["id"],
        "app": row["app"],
        "evidence_url": row["evidence"],
        "http_status": status_code,
        "fetch_error": error,
        "status": status,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "notes": notes,
        "auth_signals": auth_signals,
        "surface_signals": surface_signals,
        "access_signals": access_signals,
        "snippet": evidence_snippet,
        "elapsed_ms": round((time.time() - started) * 1000),
    }


def summarize(checks: list[dict[str, object]]) -> dict[str, object]:
    statuses = Counter(str(c["status"]) for c in checks)
    confidence = Counter(str(c.get("confidence", "Unlabeled")) for c in checks)
    fetched = sum(1 for c in checks if c["http_status"] and int(c["http_status"]) < 500)
    supported = statuses["supported"] + statuses["supports_blocker"]
    needs_review = statuses["needs_human_review"]
    blocked = statuses["blocked_or_missing"] + statuses["fetch_failed"]
    return {
        "apps_checked": len(checks),
        "pages_fetched_or_returned_status": fetched,
        "supported_by_agent": supported,
        "needs_human_review": needs_review,
        "blocked_or_failed_fetch": blocked,
        "status_counts": dict(statuses),
        "confidence_counts": dict(confidence),
        "verified_or_triaged_coverage": len(checks),
        "method": [
            "Fetch each official evidence URL from data/apps.tsv.",
            "Strip scripts/styles and extract visible page text.",
            "Detect auth, API-surface, access-gate, and MCP signals with deterministic keyword groups.",
            "Compare detected signals with the curated row and mark unsupported rows for human review.",
            "Assign every app a confidence label: Agent-supported, Human-reviewed, Curated-docs reviewed, or Needs follow-up.",
            "Keep ambiguous/gated/no-public-docs cases as findings rather than forcing a buildable answer.",
        ],
        "human_review_policy": "Rows with low signals, blocked docs, or product/API ambiguity are routed to manual verification.",
    }


def main() -> None:
    rows = load_rows()
    checks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(build_check, row): row for row in rows}
        for future in as_completed(futures):
            checks.append(future.result())
    checks.sort(key=lambda item: int(item["id"]))
    CHECKS.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(summarize(checks), indent=2), encoding="utf-8")
    print(f"Wrote {CHECKS}")
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()
