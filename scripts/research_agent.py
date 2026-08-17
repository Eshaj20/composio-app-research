from __future__ import annotations

import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "apps.tsv"
SITE = ROOT / "site" / "index.html"
TRACE = ROOT / "agent_trace.json"
EVIDENCE_REPORT = ROOT / "data" / "verification_report.json"
EVIDENCE_CHECKS = ROOT / "data" / "evidence_checks.json"


VERIFICATION_SAMPLE = {
    "Salesforce": {
        "result": "Pass",
        "check": "Docs expose multiple APIs and OAuth patterns; dev org path is self-serve.",
    },
    "HubSpot": {
        "result": "Pass",
        "check": "Auth docs state OAuth for public apps and private app access tokens for single-account use.",
    },
    "Google Ads": {
        "result": "Pass",
        "check": "Developer token is required; test access is self-serve while production levels are reviewed.",
    },
    "Amazon Selling Partner": {
        "result": "Pass",
        "check": "Sandbox path exists, but production public apps require developer registration, roles, and review.",
    },
    "Pumble": {
        "result": "Corrected",
        "check": "First pass treated webhooks as an API. Verification downgraded it to not-yet buildable.",
    },
    "fanbasis": {
        "result": "Pass",
        "check": "No stable public developer docs were found; kept as outreach/not-yet instead of guessing.",
    },
    "GitHub": {
        "result": "Pass",
        "check": "REST and GraphQL APIs plus GitHub App/PAT/OAuth auth are well documented.",
    },
    "Snowflake": {
        "result": "Corrected",
        "check": "Added SQL API auth nuance: key-pair JWT, OAuth, username/password, and PAT patterns.",
    },
    "Notion": {
        "result": "Pass",
        "check": "Internal tokens and OAuth are documented; page sharing remains the main agent blocker.",
    },
    "Stripe": {
        "result": "Pass",
        "check": "API keys and Connect OAuth are documented; live activation/compliance is the limiter.",
    },
    "NotebookLM": {
        "result": "Corrected",
        "check": "First pass overfit Gemini docs. Verification changed verdict to no standalone public API.",
    },
    "Devin": {
        "result": "Pass",
        "check": "Docs expose API/MCP integration path, with account/action-safety as the limiter.",
    },
}


def load_rows() -> list[dict[str, str]]:
    with DATA.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def bucket_auth(auth: str) -> str:
    value = auth.lower()
    if "oauth" in value:
        return "OAuth present"
    if "api key" in value or "token" in value or "bearer" in value:
        return "Key/token"
    if "basic" in value:
        return "Basic"
    if "no remote auth" in value or "no hosted auth" in value:
        return "No remote auth"
    return "Unclear/other"


def access_bucket(access: str) -> str:
    value = access.lower()
    if "self-serve" in value:
        return "Self-serve"
    if "gated" in value or "partner" in value or "contact" in value:
        return "Gated"
    if "paid" in value:
        return "Paid/plan-limited"
    return "Unclear"


def build_stats(rows: list[dict[str, str]]) -> dict[str, object]:
    auth = Counter(bucket_auth(r["auth"]) for r in rows)
    access = Counter(access_bucket(r["access"]) for r in rows)
    verdict = Counter(r["verdict"] for r in rows)
    category_verdicts: dict[str, Counter[str]] = defaultdict(Counter)
    category_access: dict[str, Counter[str]] = defaultdict(Counter)
    blockers = Counter(r["blocker"] for r in rows)
    for r in rows:
        category_verdicts[r["category"]][r["verdict"]] += 1
        category_access[r["category"]][access_bucket(r["access"])] += 1
    return {
        "auth": dict(auth),
        "access": dict(access),
        "verdict": dict(verdict),
        "category_verdicts": {k: dict(v) for k, v in category_verdicts.items()},
        "category_access": {k: dict(v) for k, v in category_access.items()},
        "top_blockers": blockers.most_common(12),
    }


def load_json(path: Path, fallback: object) -> object:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def pct(n: int, total: int) -> str:
    return f"{round(n * 100 / total)}%"


def pill(text: str) -> str:
    cls = text.lower().replace(" ", "-").replace("/", "-")
    return f'<span class="pill {html.escape(cls)}">{html.escape(text)}</span>'


def render(rows: list[dict[str, str]], stats: dict[str, object]) -> str:
    total = len(rows)
    buildable = sum(1 for r in rows if r["verdict"] == "Buildable")
    partial = sum(1 for r in rows if r["verdict"] == "Partially buildable")
    not_yet = sum(1 for r in rows if r["verdict"] == "Not yet")
    oauth = sum(1 for r in rows if bucket_auth(r["auth"]) == "OAuth present")
    selfserve = sum(1 for r in rows if access_bucket(r["access"]) == "Self-serve")
    evidence_report = load_json(EVIDENCE_REPORT, {})
    evidence_checks = load_json(EVIDENCE_CHECKS, [])
    supported_by_agent = int(evidence_report.get("supported_by_agent", 0)) if isinstance(evidence_report, dict) else 0
    needs_human_review = int(evidence_report.get("needs_human_review", 0)) if isinstance(evidence_report, dict) else 0
    blocked_or_failed = int(evidence_report.get("blocked_or_failed_fetch", 0)) if isinstance(evidence_report, dict) else 0
    fetched_statuses = int(evidence_report.get("pages_fetched_or_returned_status", 0)) if isinstance(evidence_report, dict) else 0

    category_cards = []
    for category, counts in stats["category_verdicts"].items():
        b = counts.get("Buildable", 0)
        p = counts.get("Partially buildable", 0)
        n = counts.get("Not yet", 0)
        category_cards.append(
            f"""
            <article class="category-card">
              <h3>{html.escape(category)}</h3>
              <div class="bar" aria-label="{html.escape(category)} verdict split">
                <span style="width:{b * 10}%" class="ok"></span>
                <span style="width:{p * 10}%" class="mid"></span>
                <span style="width:{n * 10}%" class="bad"></span>
              </div>
              <p>{b}/10 buildable, {p}/10 partial, {n}/10 not yet</p>
            </article>
            """
        )

    table_rows = []
    for r in rows:
        table_rows.append(
            f"""
            <tr data-category="{html.escape(r['category'])}" data-verdict="{html.escape(r['verdict'])}">
              <td>{r['id']}</td>
              <td><strong>{html.escape(r['app'])}</strong><span>{html.escape(r['category'])}</span></td>
              <td>{html.escape(r['one_line'])}</td>
              <td>{html.escape(r['auth'])}</td>
              <td>{html.escape(r['access'])}</td>
              <td>{html.escape(r['surface'])}<span>{html.escape(r['mcp'])}</span></td>
              <td>{pill(r['verdict'])}<span>{html.escape(r['blocker'])}</span></td>
              <td><a href="{html.escape(r['evidence'])}" target="_blank" rel="noreferrer">Evidence</a></td>
            </tr>
            """
        )

    verification_cards = []
    for app, item in VERIFICATION_SAMPLE.items():
        cls = item["result"].lower()
        verification_cards.append(
            f"""
            <article class="verify {cls}">
              <h3>{html.escape(app)}</h3>
              {pill(item['result'])}
              <p>{html.escape(item['check'])}</p>
            </article>
            """
        )

    agent_review_rows = []
    if isinstance(evidence_checks, list):
        review_items = [
            c
            for c in evidence_checks
            if c.get("status") in {"needs_human_review", "blocked_or_missing", "fetch_failed"}
        ][:12]
        for item in review_items:
            notes = ", ".join(str(n) for n in item.get("notes", [])) or str(item.get("fetch_error") or "Needs review")
            agent_review_rows.append(
                f"""
                <tr>
                  <td><strong>{html.escape(str(item.get('app', '')))}</strong></td>
                  <td>{pill(str(item.get('status', 'review')))}</td>
                  <td>{html.escape(notes)}</td>
                  <td>{html.escape(str(item.get('snippet', ''))[:240])}</td>
                </tr>
                """
            )

    rows_json = json.dumps(rows, indent=2)
    stats_json = json.dumps(stats, indent=2)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Composio Toolkit Research: 100 App Buildability Map</title>
  <style>
    :root {{
      --ink:#171717; --muted:#5f6368; --line:#d9dee7; --panel:#f8fafc; --paper:#fffdf8;
      --ok:#217a4b; --mid:#b66a00; --bad:#a43a3a; --accent:#285f8f; --teal:#14756f;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; color:var(--ink); background:var(--paper); }}
    header {{ padding:42px 5vw 28px; border-bottom:1px solid var(--line); background:#f4f7fb; }}
    h1 {{ margin:0; max-width:980px; font-size:clamp(2rem, 4vw, 4.3rem); line-height:1; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:1.4rem; }}
    h3 {{ margin:0 0 8px; font-size:1rem; }}
    p {{ color:var(--muted); line-height:1.45; }}
    a {{ color:var(--accent); }}
    main {{ padding:28px 5vw 64px; }}
    section {{ margin:0 auto 34px; max-width:1320px; }}
    .lede {{ max-width:900px; font-size:1.12rem; }}
    .grid {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; }}
    .grid.five {{ grid-template-columns:repeat(5, minmax(0, 1fr)); }}
    .metric, .category-card, .verify, .workflow-step {{ background:white; border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .metric strong {{ display:block; font-size:2rem; }}
    .metric span {{ color:var(--muted); }}
    .insights {{ display:grid; grid-template-columns:1.15fr .85fr; gap:18px; }}
    .insights ul {{ margin:0; padding-left:20px; line-height:1.5; }}
    .matrix {{ display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; }}
    .bar {{ display:flex; height:10px; overflow:hidden; border-radius:999px; background:#edf1f5; margin:10px 0; }}
    .bar span.ok {{ background:var(--ok); }}
    .bar span.mid {{ background:var(--mid); }}
    .bar span.bad {{ background:var(--bad); }}
    .workflow {{ display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; }}
    .workflow-step b {{ display:inline-grid; place-items:center; width:26px; height:26px; border-radius:999px; background:#dff0eb; color:#07594e; margin-bottom:8px; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:12px 0; }}
    input, select {{ border:1px solid var(--line); border-radius:6px; padding:9px 10px; background:white; min-height:40px; }}
    input {{ min-width:260px; flex:1; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:8px; background:white; }}
    table {{ width:100%; border-collapse:collapse; min-width:1180px; }}
    th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:.9rem; }}
    th {{ position:sticky; top:0; background:#eef3f7; z-index:1; }}
    td span {{ display:block; color:var(--muted); margin-top:4px; font-size:.82rem; }}
    .pill {{ display:inline-block; padding:4px 8px; border-radius:999px; font-size:.78rem; font-weight:700; background:#eef1f5; color:#31363c; }}
    .pill.buildable, .pill.pass, .pill.supported, .pill.supports_blocker {{ background:#dff2e7; color:var(--ok); }}
    .pill.partially-buildable, .pill.corrected, .pill.needs_human_review {{ background:#fff0d8; color:var(--mid); }}
    .pill.not-yet, .pill.blocked_or_missing, .pill.fetch_failed {{ background:#fde5e5; color:var(--bad); }}
    .verify-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:10px; }}
    .data-note {{ font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:.8rem; background:#111827; color:#e5e7eb; padding:14px; border-radius:8px; overflow:auto; max-height:240px; }}
    footer {{ max-width:1320px; margin:0 auto; padding:0 5vw 48px; color:var(--muted); }}
    @media (max-width: 960px) {{
      .grid, .insights, .matrix, .workflow, .verify-grid {{ grid-template-columns:1fr 1fr; }}
    }}
    @media (max-width: 640px) {{
      header, main {{ padding-left:18px; padding-right:18px; }}
      .grid, .insights, .matrix, .workflow, .verify-grid {{ grid-template-columns:1fr; }}
      input {{ min-width:100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>100 app toolkit research map for Composio</h1>
    <p class="lede">An agent-assisted pass across requested apps to find auth patterns, API access gates, MCP/toolkit readiness, blockers, and the best near-term build queue.</p>
  </header>
  <main>
    <section class="grid five" aria-label="headline metrics">
      <div class="metric"><strong>{buildable}</strong><span>apps buildable today ({pct(buildable, total)})</span></div>
      <div class="metric"><strong>{partial}</strong><span>partial or gated ({pct(partial, total)})</span></div>
      <div class="metric"><strong>{not_yet}</strong><span>not yet buildable ({pct(not_yet, total)})</span></div>
      <div class="metric"><strong>{oauth}</strong><span>have OAuth somewhere in the auth model</span></div>
      <div class="metric"><strong>{supported_by_agent}</strong><span>rows supported by live evidence-agent signals</span></div>
    </section>

    <section class="insights">
      <div>
        <h2>What matters</h2>
        <ul>
          <li><strong>OAuth dominates distribution, but tokens dominate first-party use.</strong> CRM, support, productivity, ads, and commerce often need OAuth for multi-tenant installs; infra, data, email, and scraping tools commonly start with API keys.</li>
          <li><strong>The easiest wins are already agent-shaped.</strong> Developer platforms, productivity tools, support desks, and ecommerce platforms have broad public APIs, clear docs, and existing MCP/community precedent.</li>
          <li><strong>The hardest blockers are not technical endpoints.</strong> Ads, fintech, Amazon SP-API, and enterprise commerce are mostly blocked by review, compliance, tenant admin approval, or paid data licenses.</li>
          <li><strong>Not-yet apps are mostly missing a public developer surface.</strong> Pumble, fanbasis, Paygent Connect, NotebookLM, and Consensus should go to outreach or partner-discovery before engineering starts.</li>
        </ul>
      </div>
      <div class="metric">
        <strong>{selfserve}</strong>
        <span>apps had a practical self-serve or trial path for a developer to start research without a partnership.</span>
        <p>Self-serve did not always mean production-ready. Google Ads, Plaid, Amazon SP-API, Meta/LinkedIn Ads, and finance platforms still need review before broad customer use.</p>
      </div>
    </section>

    <section>
      <h2>Category buildability matrix</h2>
      <div class="matrix">{''.join(category_cards)}</div>
    </section>

    <section>
      <h2>Agent workflow</h2>
      <div class="workflow">
        <article class="workflow-step"><b>1</b><h3>Seed</h3><p>Started from the 100-app list, official domains, and developer-doc hints.</p></article>
        <article class="workflow-step"><b>2</b><h3>Fetch</h3><p><code>evidence_agent.py</code> visits every evidence URL, strips page chrome, and extracts text from official docs pages.</p></article>
        <article class="workflow-step"><b>3</b><h3>Extract</h3><p>Deterministic rules detect OAuth, API keys, tokens, Basic auth, REST, GraphQL, webhooks, MCP, review, and gated-access signals.</p></article>
        <article class="workflow-step"><b>4</b><h3>Verify</h3><p>The agent compares extracted signals with the TSV, routes low-signal rows to human review, and a 12-app sample is checked manually.</p></article>
        <article class="workflow-step"><b>5</b><h3>Package</h3><p><code>research_agent.py</code> emits this HTML, <code>agent_trace.json</code>, and the verification report for reruns.</p></article>
      </div>
    </section>

    <section class="grid" aria-label="agent verification metrics">
      <div class="metric"><strong>{supported_by_agent}</strong><span>supported or blocker-supported by fetched evidence</span></div>
      <div class="metric"><strong>{needs_human_review}</strong><span>routed to human review by the evidence agent</span></div>
      <div class="metric"><strong>{blocked_or_failed}</strong><span>blocked, missing, or failed fetches</span></div>
      <div class="metric"><strong>{fetched_statuses}</strong><span>URLs returned an HTTP status during the live run</span></div>
    </section>

    <section>
      <h2>Agent-routed review queue</h2>
      <p>These are examples the evidence agent refused to fully trust. They are the right places for manual checking, outreach, or paid-account validation.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>App</th><th>Agent status</th><th>Reason</th><th>Evidence snippet</th></tr></thead>
          <tbody>{''.join(agent_review_rows) or '<tr><td colspan="4">Run <code>python scripts/evidence_agent.py</code> to generate the review queue.</td></tr>'}</tbody>
        </table>
      </div>
    </section>

    <section>
      <h2>Verification sample</h2>
      <p>Initial pass accuracy on this sample was 9/12. After verification corrections for Pumble, Snowflake, and NotebookLM, the reported sample is 12/12 against the checked evidence. This is the key human loop: ambiguous APIs are downgraded, not guessed.</p>
      <div class="verify-grid">{''.join(verification_cards)}</div>
    </section>

    <section>
      <h2>Clean table</h2>
      <div class="toolbar">
        <input id="q" placeholder="Search app, auth, blocker, or category" aria-label="Search table">
        <select id="verdict" aria-label="Filter verdict">
          <option value="">All verdicts</option>
          <option>Buildable</option>
          <option>Partially buildable</option>
          <option>Not yet</option>
        </select>
        <select id="category" aria-label="Filter category">
          <option value="">All categories</option>
          {''.join(f'<option>{html.escape(c)}</option>' for c in sorted(set(r['category'] for r in rows)))}
        </select>
      </div>
      <div class="table-wrap">
        <table id="apps">
          <thead>
            <tr><th>#</th><th>App</th><th>What it does</th><th>Auth</th><th>Access</th><th>API surface / MCP</th><th>Verdict / blocker</th><th>Proof</th></tr>
          </thead>
          <tbody>{''.join(table_rows)}</tbody>
        </table>
      </div>
    </section>

    <section>
      <h2>Machine-readable output</h2>
      <p>Generated from <code>data/apps.tsv</code> by <code>python scripts/evidence_agent.py</code> and <code>python scripts/research_agent.py</code>. The runs write <code>data/evidence_checks.json</code>, <code>data/verification_report.json</code>, and <code>agent_trace.json</code>.</p>
      <pre class="data-note">{html.escape(stats_json)}</pre>
    </section>
  </main>
  <footer>
    Source and runnable trigger: <code>python scripts/evidence_agent.py</code> then <code>python scripts/research_agent.py</code>. Evidence links are intentionally official docs or product developer pages wherever available; unclear apps are marked as gated/unknown rather than inferred.
  </footer>
  <script>
    const rows = Array.from(document.querySelectorAll("#apps tbody tr"));
    const q = document.querySelector("#q");
    const verdict = document.querySelector("#verdict");
    const category = document.querySelector("#category");
    function applyFilters() {{
      const term = q.value.trim().toLowerCase();
      for (const row of rows) {{
        const text = row.innerText.toLowerCase();
        const okTerm = !term || text.includes(term);
        const okVerdict = !verdict.value || row.dataset.verdict === verdict.value;
        const okCategory = !category.value || row.dataset.category === category.value;
        row.style.display = okTerm && okVerdict && okCategory ? "" : "none";
      }}
    }}
    q.addEventListener("input", applyFilters);
    verdict.addEventListener("change", applyFilters);
    category.addEventListener("change", applyFilters);
    window.__researchRows = {rows_json};
  </script>
</body>
</html>
"""


def main() -> None:
    rows = load_rows()
    stats = build_stats(rows)
    SITE.write_text(render(rows, stats), encoding="utf-8")
    TRACE.write_text(
        json.dumps(
            {
                "source": str(DATA.relative_to(ROOT)),
                "output": str(SITE.relative_to(ROOT)),
                "rows": len(rows),
                "stats": stats,
                "evidence_report": load_json(EVIDENCE_REPORT, {}),
                "verification_sample": VERIFICATION_SAMPLE,
                "known_limits": [
                    "No paid credentials were used.",
                    "Official docs were preferred; gated products are marked as partial or not-yet.",
                    "MCP presence is a discovery signal, not a guarantee of production readiness.",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {SITE}")
    print(f"Wrote {TRACE}")


if __name__ == "__main__":
    main()
