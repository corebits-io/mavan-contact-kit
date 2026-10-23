# CLAUDE.md — Prospect Data Kit operating instructions

You are running the data half of a lead-gen system: **list → research → enrich → qualify**. Read this fully before acting.

This kit produces a CSV. It does **not** send anything, and it does not write outreach copy. If asked to draft messages, say that is out of scope here and explain why (see rule 5).

---

## Prime directives (non-negotiable)

1. **Never invent data.** No fabricated signals, names, numbers, sources, or emails. If research found nothing real about a person, say so and fall back to an honest company-level note. Tag confidence on every row. An honest `none` beats a made-up hook — the made-up one gets caught in the reply.

2. **Two independent finders, then a verifier.** Prospeo and Better Contact are FINDERS. BounceBan is a VERIFIER and cannot find anything. Never present an unverified address as usable. `email_confidence` is the field to filter on.

3. **`risky` is not a pass.** It means a catch-all domain accepted the probe, so nothing is proven about that specific mailbox. Never upgrade a `risky` result. Email misses cluster **by company** (catch-all domains), not randomly — probe for catch-all before concluding a finder has poor coverage.

4. **Test on 5 rows before running the list.** Every enrichment row costs credits and a wrong column mapping burns all of them. `--limit 5`, read the output, then scale. Run large lists in chunks (~45 for enrich, 10 for Apify).

5. **Research is factual; messaging is not this kit's job.** Do not write hooks, openers, subject lines, or draft messages anywhere in this pipeline — not even as a suggestion in a spare column. Outreach copy is written later by the sender, in their own voice, with their own approval gate. Mixing the two produces generic templated copy, which is exactly what this system exists to avoid.

6. **Vet fit before contacting.** Every campaign gets an explicit rubric in `rubrics/`. Grade at discovery and again after enrichment — new facts change fit. Never let an ungraded list go to outreach.

7. **Nothing is silently dropped.** Grading is advisory. Report counts and reasons; let a human make the cut. If you bound coverage anywhere (top-N, sampling, skipped rows), say so explicitly — silent truncation reads as "covered everything" when it didn't.

8. **Never print an API key value.** Read keys from `.env`. Naming the key is fine; echoing it is not.

---

## The four steps

**1 — Build the list** (`build-list`, optional)
If you already have company domains and need the person, use `find-people` instead: `python3 skills/find-people/find_people.py --domain <d> --titles <set from ICP.md> --enrich 1 --fallback --out research/<d>.csv`. It finds the person, finds the email through Prospeo then Better Contact, and verifies with BounceBan in one go. One domain at a time.

**1 — Build the list** (`build-list`, optional)
Read `ICP.md`. Restate the target in one line and get a yes before spending. Clay if connected, else Apify with `maxTotalChargeUsd` set, else stop and ask for a CSV. Real LinkedIn URLs only — a guessed URL poisons every step after it.
→ `leads/<name>.csv` with `name, title, company, linkedin_url`

**2 — Research it** (`research-list`)
Free web search. Company research is reliable; person research is partial; LinkedIn profiles are usually gated to anonymous fetches, so treat any you get as a bonus. One plain line for `what_they_do`, one real recent `signal`, the actual URL in `signal_source`.
→ `research/<name>-researched.csv` adds `what_they_do, signal, signal_source, confidence`

**3 — Enrich** (`enrich-contacts`)
`enrich.py` → `repick_best_email.py` → optionally `recover_missing_emails.py` → `apify_profiles.py` → `join_apify.py` → write factual profile summaries.
Step 2 is not optional on a real campaign: `enrich.py` breaks ties toward Prospeo, which can hand you a prospect's old-employer or portfolio-company address. It verifies fine and is still the wrong inbox.
→ adds verified email, cross-checked phone, `profile_summary`

**4 — Qualify** (`qualify-leads`)
Copy `rubrics/TEMPLATE.json`, fill it in, run `--explain` to read it back before trusting it, then grade. Read every D/E row and every `employer_check` flag by hand. Record human calls in an overrides JSON, never by hand-editing the CSV.
→ adds `fit_grade, fit_reason, employer_check, status_flag, status_note`

---

## Data formats

- **Input** (`leads/*.csv`): `name, title, company, linkedin_url`. `first_name`/`last_name` also accepted.
- **Researched** adds `what_they_do, signal, signal_source, confidence`. `confidence` = `verified` (you have a source URL) / `likely` (reasonable but softer) / `none` (nothing real found — leave `signal` empty).
- **Enriched** adds the email/phone columns. `email_confidence` = `high` (both finders agree **and** deliverable) / `medium` (deliverable, one source) / `low` (catch-all) / `unusable` / `none`.
- **Graded** adds `fit_grade` (A–E), `fit_reason`, `employer_check`.
- A **row key** is the `contact_id` column if the list has one, else `row<N>` by zero-based input order. Overrides and profile joins use it.

## Credentials
All in `.env`, documented in `.env.example`. Note: the line named `BOUNCER_API_KEY` holds the **BounceBan** key. Keep a second Apify token as `APIFY_API_TOKEN_2` and select it with `APIFY_KEY=APIFY_API_TOKEN_2`.

## Known sharp edges
- **Better Contact maps by index** — it does not echo back the `linkedin_url`. If the returned row count differs from what was submitted, stop and check by hand.
- **Apify joins positionally** — the actor returns the profile's canonical vanity URL, not the URL queried. `--tag b<N>` must encode the start index.
- **Apify free plan** — 10 items/run, 20 runs/account, $5/month. Past a limit the actor *succeeds* and returns a single `{"error": ...}` item. A short batch means a limit was hit, not that the people don't exist.
- **`employer_check` is blunt** — it compares normalised company names, so it can't tell a rebrand from a departure and it trips on legitimate dual roles. It flags; it never downgrades.

## Working style
- One step at a time; verify each before moving on.
- Keep on-screen output compact: short tables and counts, not walls of reasoning.
- Ask one sharp question when genuinely blocked. Otherwise proceed.
- Stay well under 300 requests/minute.
