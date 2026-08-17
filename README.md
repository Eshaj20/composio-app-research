# Composio 100-App Toolkit Research

This is a take-home case study for mapping whether 100 requested apps can become agent-callable Composio toolkits.

## Deliverable

- Single page case study: `site/index.html`
- Structured source data: `data/apps.tsv`
- Evidence-fetching research agent: `scripts/evidence_agent.py`
- Runnable report generator: `scripts/research_agent.py`
- Agent verification outputs: `data/evidence_checks.json` and `data/verification_report.json`
- Machine-readable run trace: `agent_trace.json`

## Run

```bash
python scripts/evidence_agent.py
python scripts/research_agent.py
npm run build
```

`evidence_agent.py` fetches the evidence URL for each app, extracts visible text, detects auth/API/access signals, and writes verification artifacts. `research_agent.py` reads the 100-app TSV plus those verification artifacts, computes patterns, embeds the table and statistics into `site/index.html`, and writes `agent_trace.json`.

## What The Agent Does

1. Ingests the app list and official evidence URLs.
2. Fetches each docs/product page with a deterministic batch agent.
3. Extracts visible page text and detects OAuth, API key, token, Basic auth, REST, GraphQL, webhook, MCP, review, and gated-access signals.
4. Compares extracted signals against the curated row and routes low-signal or blocked pages to human review.
5. Normalizes auth/access/buildability patterns and produces the reviewer-friendly HTML case study.

## Latest Agent Run

The latest run checked and labeled all 100 rows:

- 100 apps received a verification or triage label.
- 87 evidence URLs returned an HTTP status during the live run.
- 21 rows were strictly agent-supported by fetched page signals.
- 9 rows were primarily labeled human-reviewed; the manual sample itself covers 12 apps, including rows that were also agent-supported.
- 49 rows were curated-docs reviewed: official evidence was captured, but strict extraction did not confirm every field automatically.
- 21 rows were marked needs follow-up for gated, unclear, missing, or partner/outreach-heavy API access.

This strictness is intentional. The agent is used to accelerate collection, evidence checking, and triage across all 100 apps; it does not silently invent confidence when docs are gated, rendered client-side, or ambiguous.

## Human Verification Loop

A 12-app sample was checked manually against official docs or product developer pages:

- Salesforce
- HubSpot
- Google Ads
- Amazon Selling Partner
- Pumble
- fanbasis
- GitHub
- Snowflake
- Notion
- Stripe
- NotebookLM
- Devin

Three first-pass classifications were corrected:

- Pumble was downgraded because webhooks are not a broad public API.
- Snowflake had its auth model expanded beyond OAuth.
- NotebookLM was downgraded because there is no standalone public NotebookLM API; Gemini/Drive are adjacent alternatives, not the same product API.

## Known Limits

No paid accounts, partner accounts, or production API credentials were used. Gated products are therefore marked as partial or not-yet, which is the intended behavior for this research: the blocker itself is the finding.
