from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROWS_PATH = ROOT / "data" / "apps.tsv"
CHECKS_PATH = ROOT / "data" / "evidence_checks.json"
REPORT_PATH = ROOT / "data" / "clean_table_audit.json"


def load_rows() -> list[dict[str, str]]:
    with ROWS_PATH.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def has_any(value: str, terms: tuple[str, ...]) -> bool:
    lower = value.lower()
    return any(term in lower for term in terms)


def signal_keys(check: dict[str, object], key: str) -> set[str]:
    value = check.get(key, {})
    if not isinstance(value, dict):
        return set()
    return {str(k) for k, hits in value.items() if hits}


def audit_row(row: dict[str, str], check: dict[str, object]) -> list[str]:
    issues: list[str] = []
    auth = row["auth"].lower()
    access = row["access"].lower()
    surface = row["surface"].lower()
    verdict = row["verdict"]
    blocker = row["blocker"].lower()

    auth_signals = signal_keys(check, "auth_signals")
    surface_signals = signal_keys(check, "surface_signals")
    access_signals = signal_keys(check, "access_signals")
    confidence = str(check.get("confidence", ""))

    if "oauth" in auth and "oauth" not in auth_signals and confidence == "Agent-supported":
        issues.append("auth_mentions_oauth_but_evidence_lacks_oauth_signal")
    if has_any(auth, ("api key", "token", "bearer", "basic", "jwt", "hmac")) and not auth_signals:
        issues.append("auth_expected_but_no_auth_signal")
    if has_any(surface, ("rest", "graphql", "api", "webhook", "cli")) and not surface_signals:
        issues.append("surface_expected_but_no_surface_signal")
    if verdict == "Buildable" and has_any(access + " " + blocker, ("gated", "partner", "contact sales", "unclear", "unknown", "no broad public")):
        issues.append("buildable_verdict_has_gated_or_unclear_access")
    if verdict == "Not yet" and confidence == "Agent-supported" and surface_signals and check.get("status") != "supports_blocker":
        issues.append("not_yet_row_has_agent_api_surface_signal")
    if has_any(access + " " + blocker, ("gated", "partner", "contact", "review", "approval", "paid")) and not access_signals:
        issues.append("gated_or_review_claim_lacks_access_signal")

    return issues


def main() -> None:
    rows = load_rows()
    checks = {str(c["app"]): c for c in json.loads(CHECKS_PATH.read_text(encoding="utf-8"))}
    findings = []
    for row in rows:
        check = checks.get(row["app"], {})
        issues = audit_row(row, check)
        if issues:
            findings.append(
                {
                    "id": row["id"],
                    "app": row["app"],
                    "verdict": row["verdict"],
                    "auth": row["auth"],
                    "access": row["access"],
                    "surface": row["surface"],
                    "confidence": check.get("confidence"),
                    "status": check.get("status"),
                    "issues": issues,
                    "evidence_url": row["evidence"],
                    "snippet": str(check.get("snippet", ""))[:320],
                }
            )
    REPORT_PATH.write_text(json.dumps({"findings": findings, "count": len(findings)}, indent=2), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Findings: {len(findings)}")
    for item in findings[:40]:
        print(item["id"], item["app"], "; ".join(item["issues"]))


if __name__ == "__main__":
    main()
