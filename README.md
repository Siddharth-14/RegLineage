# RegLineage

A small, self-contained **data lineage and quality scorecard** for
regulatory-reporting pipelines.

> **Synthetic data only. No connection to any real institution.**
> Every table, name, and figure this app shows is randomly generated with a
> fixed seed (`42`). Nothing here is derived from, modeled on, or connected
> to any real bank's systems, data, or reporting. This is a portfolio demo
> illustrating the *kind* of lineage and quality evidence a data governance
> team might produce for numbers that land in a regulatory report -- it is
> not, and does not claim to be, a real audit of anything.

## What this demonstrates

Regulators increasingly expect banks to be able to trace a number in a
regulatory report all the way back to its source systems, and to show
evidence that the data along that path is complete, fresh, correctly
linked, and accurate. RegLineage is a toy version of the kind of tool that
helps a data governance team produce that evidence:

1. **Declare lineage** from source fields, through transforms, to a report
   field (`lineage/manifest.yaml`).
2. **Score data quality** at each source/report node against real,
   generated data: completeness, freshness, referential consistency, and
   accuracy (`lineage/scoring.py`).
3. **Visualize the lineage graph**, color-coded by the worst score along
   each path, so a reviewer can see at a glance where a report field's
   evidentiary chain breaks down.
4. **Explain each flagged field in plain English**, either from a
   deterministic template (always available, free) or, optionally, a live
   call to Claude for a more natural remediation-memo narrative.

## How lineage is declared here (and what's out of scope)

Lineage in this demo is **hand-declared** in `lineage/manifest.yaml`: a
human data owner lists each source field, each transform, each report
field, and the edges between them. `lineage/graph.py` just parses that file
into a `networkx` DiGraph -- there's no SQL parsing, no ETL-log scraping, no
automatic column-level lineage discovery.

**Auto-discovering lineage from pipeline code (SQL, dbt, Spark jobs, etc.)
is explicitly out of scope for this demo.** That's a much larger, genuinely
hard engineering problem on its own, and solving it well is exactly the
kind of thing a real implementation would need to tackle next. This demo
focuses on what you can do *once* lineage is declared: scoring it and
explaining it.

## Repo layout

```
reglineage/
  data/
    generate_synthetic_data.py   # builds seeded synthetic tables to data/*.csv
  lineage/
    manifest.yaml                # source table -> transform -> report field
    graph.py                     # builds a networkx DiGraph from manifest.yaml
    scoring.py                   # per-node quality metrics + pass/fail flags
  narrative/
    templates.py                 # deterministic narrative generator (default, free)
    llm_narrative.py             # optional Anthropic API call; falls back silently
  app.py                         # Streamlit UI
  seed_and_run.sh                # generates data + launches app in one command
  requirements.txt
```

## Running it locally

```bash
git clone <this-repo>
cd reglineage
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./seed_and_run.sh
```

That's it -- no manual data setup, no API key required. If `data/*.csv`
don't exist yet, `app.py` generates them automatically on first load, so a
fresh clone (or a fresh Streamlit Cloud deploy) needs zero manual steps.

The synthetic data generator seeds a handful of realistic defects on
purpose, so the scorecard always has something to flag on a fresh run:

- ~12% of `accounts.csv` rows with a null `customer_id` (an orphaned
  foreign key back to `customers.csv`)
- ~12% of `transactions.csv` rows backdated well past their account's
  normal activity window (a staleness defect)
- ~12% of `reg_report_extract.csv` rows where `reported_value` is pushed
  outside tolerance of the actual transaction rollup (an accuracy defect)
- ~12% of `customers.csv` rows with a missing `kyc_status` (a completeness
  defect)

These rates are set a bit higher than a real institution's error rates
would typically be, specifically so the demo reliably clears the 90%
flagging threshold on every run rather than depending on random luck. The
90% thresholds themselves (and the 30-day staleness window, and the
accuracy tolerance) live in a small config dict at the top of
`lineage/scoring.py` -- change them there if you want to see the scorecard
react differently.

## Enabling the optional live-LLM narrative

By default, every flagged field gets a plain-English narrative from
`narrative/templates.py` -- a deterministic, free, no-network-call
explanation of what failed and why it matters for the lineage trace.

If you set the `ANTHROPIC_API_KEY` environment variable, `app.py` instead
asks Claude to write that narrative, with a strict system prompt that:

- states explicitly that the data is synthetic with no connection to any
  real institution,
- forbids inventing any fact or number beyond the metrics actually
  computed,
- asks for a short (2-3 sentence), factual, non-alarmist remediation-memo
  style note.

If the key isn't set, the `anthropic` package can't be imported, or the API
call fails for any reason, RegLineage silently falls back to the template
narrative -- the app never breaks over this optional path, and the UI
labels which narrative source actually ran.

To try it locally:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./seed_and_run.sh
```

## Deploying for free (Streamlit Community Cloud)

1. Push this repo to a public GitHub repository.
2. Go to [Streamlit Community Cloud](https://streamlit.io/cloud), connect
   your GitHub account, and deploy `app.py` from that repo.
3. That's the whole default deploy -- no secrets, no paid dependencies, no
   infrastructure to manage. The optional LLM path stays off unless you add
   a key.
4. If you want the live-LLM narrative demoed for a specific session (e.g.
   an interview), add `ANTHROPIC_API_KEY` in that app's **Settings ->
   Secrets** in Streamlit Cloud. **Never commit an API key to the repo.**

## Stack

Python 3.11, pandas, numpy, Faker, networkx, pyvis (rendered inside
Streamlit via `streamlit.components.v1.html`), streamlit, pyyaml. The
`anthropic` SDK is an optional dependency, imported lazily and only used
when `ANTHROPIC_API_KEY` is set -- its absence never breaks the app.
