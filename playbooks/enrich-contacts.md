# Playbook — Enrich contacts

**Goal:** every row gets a verified email, a cross-checked phone, and a factual LinkedIn profile summary.

**This step spends real money.** Everything below is written to stop you spending it twice.

## Before you start
- Input needs `linkedin_url`, `company`, and either `first_name`/`last_name` or `name`.
- Check `.env` has `PROSPEO_API_KEY`, `BETTERCONTACT_API_KEY`, `BOUNCER_API_KEY`, `APIFY_API_TOKEN`.
- Look at the input CSV's header row with your own eyes. A wrong column name burns credits on every row before you notice.

## Step 1 — find and verify

```bash
python3 skills/enrich-contacts/enrich.py --in leads/list.csv --out research/list-enriched.csv --limit 5
```

Read those 5 rows before going further. You are checking: did Prospeo return anything? did Better Contact return the same *number* of rows you submitted? do the emails look like they belong to these people?

Then run the list in chunks of ~45:

```bash
python3 skills/enrich-contacts/enrich.py --in leads/list.csv --out research/enriched-0.csv  --start 0  --limit 45
python3 skills/enrich-contacts/enrich.py --in leads/list.csv --out research/enriched-45.csv --start 45 --limit 45
```

What it does: submits the whole batch to Better Contact (async) up front, runs Prospeo row by row while that works, then BounceBan-verifies **every distinct address either finder returned** — not just the preferred one. Verifying only the favourite is how you throw away the address that was actually good.

**Better Contact maps by index.** It does not echo back the `linkedin_url`, so submission order is the only join key. If the script warns that the returned row count differs from what was submitted, stop and check several rows by hand before trusting that chunk.

## Step 2 — re-pick the best address (not optional)

```bash
python3 skills/enrich-contacts/repick_best_email.py --chunks 'research/enriched-*.csv' --dry-run
python3 skills/enrich-contacts/repick_best_email.py --chunks 'research/enriched-*.csv'
```

Two things: it retries BounceBan wherever the *verifier* errored (so a network blip never gets recorded as a bad address), and it re-picks `best_email` preferring the target company's own domain.

Why that matters: `enrich.py` breaks ties toward Prospeo. Once you care which inbox you land in, that's the wrong rule — a prospect's old-employer or portfolio-company address verifies perfectly and is still the wrong place to reach them for this campaign.

Needs a domain column (`firm_domain` / `company_domain` / `domain`) or `--accounts`. Without one it says so and skips the re-pick.

## Step 3 — recover the misses (optional)

```bash
python3 skills/enrich-contacts/recover_missing_emails.py --file research/enriched-0.csv --dry-run
```

Both finders report only what they've observed, so they go blank on small companies with no public email footprint. **The misses cluster by company, not randomly.** Where a colleague on the same domain did verify, that company's pattern is visible and the missing person's address can be constructed — then actually tested.

Three rules keep this honest, and they are in the script for a reason:
- only keep what BounceBan calls `deliverable`; `risky` is discarded
- catch-all is detected first with a nonsense address — if that "verifies", the whole domain is skipped and nothing is claimed for anyone there
- recovered rows are `best_email_source=pattern_inferred`, `email_confidence=medium`. **Never `high`** — nobody independently found these

## Step 4 — scrape profiles

```bash
python3 skills/enrich-contacts/apify_profiles.py --in leads/list.csv --start 0  --limit 10 --tag b0
python3 skills/enrich-contacts/apify_profiles.py --in leads/list.csv --start 10 --limit 10 --tag b10
APIFY_KEY=APIFY_API_TOKEN_2 python3 skills/enrich-contacts/apify_profiles.py --in leads/list.csv --start 20 --limit 10 --tag b20
```

**The `--tag` must be `b<start index>`.** `join_apify.py` reads that number to map results back to rows.

**Apify free plan: 10 items/run, 20 runs/account, $5/month.** A 100-row list needs 10 runs; a 270-row list needs 27, which is more than one free account allows. Keep a second token as `APIFY_API_TOKEN_2`.

Past a limit the actor **succeeds** and returns a single `{"error": ...}` item rather than failing. The script detects the all-errors case and exits 2, but a *partially* short batch also means a limit was hit — not that those people don't exist. Re-run the shortfall on another token before calling the batch complete.

## Step 5 — join

```bash
python3 skills/enrich-contacts/join_apify.py --in leads/list.csv --scratch scratch/
```

**Positional, not by URL** — the actor returns the profile's canonical vanity URL (`brian-edgerley-96895346` → `brianedgerley`), so a URL join silently loses rows. Batches go out in input order and come back in the same order.

Positional joins are dangerous unless checked, so every match is re-verified against the expected name. **Read `scratch/profiles_bad.json`.** A mismatch usually means a batch was re-run under a different `--tag`.

## Step 6 — summarize

Write a 2–4 sentence factual `profile_summary` per row: who they are, tenure, background, anything factual worth knowing. Read the About text and the per-experience descriptions.

- **Never invent.** If a scrape came back empty, write that it did. Don't reconstruct a plausible career from the job title.
- **No hooks, no openers, no message drafts.** Factual only.

## Checkpoint
Report: rows enriched, `email_confidence` breakdown, phone agreement breakdown, profiles scraped vs empty, name mismatches, and total credits burned per service. Then hand to `qualify-leads`.
