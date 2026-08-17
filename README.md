# Composio 100-App Toolkit Research

This is a take-home case study for mapping whether 100 requested apps can become agent-callable Composio toolkits.

## Deliverable

- Single page case study: `site/index.html`
- Structured source data: `data/apps.tsv`
- Runnable research/report agent: `scripts/research_agent.py`
- Machine-readable run trace: `agent_trace.json`

## Run

```bash
python scripts/research_agent.py
```

The script reads the 100-app TSV, normalizes auth/access/buildability buckets, computes category-level patterns, embeds the table and statistics into `site/index.html`, and writes `agent_trace.json`.

## What The Agent Does

1. Ingests the app list and evidence URLs.
2. Normalizes auth methods into OAuth-present, key/token, Basic, no remote auth, or unclear.
3. Normalizes credential availability into self-serve, gated, paid/plan-limited, or unclear.
4. Scores each app as `Buildable`, `Partially buildable`, or `Not yet`.
5. Produces a reviewer-friendly HTML case study with filters, matrix, headline insights, workflow, and verification notes.

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
