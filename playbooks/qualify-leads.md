# Playbook — Qualify leads

**Goal:** every row carries an A–E fit grade and a readable reason, so outreach only goes to people it should.

Costs nothing. Skipping it costs you the list's credibility.

## Why a rubric file and not code
A fit rubric is a business judgement. It changes per campaign, it gets argued about, and someone who wasn't there when it was built has to be able to read it and disagree. So it lives in `rubrics/*.json`, not inside `grade_fit.py`.

Start from `rubrics/TEMPLATE.json`. Read `rubrics/EXAMPLE-lmm-pe-deal-origination.json` first — it's a real shipped rubric and shows the level of specificity that actually works. Note how its disqualifier reasons explain the *business logic* ("secondaries buyers buy LP interests, not companies") rather than just saying "not a fit". That's what makes a graded list reviewable later.

## Step 1 — write the rubric

```bash
cp rubrics/TEMPLATE.json rubrics/my-campaign.json
```

Fill in, in this order:

1. **`campaign`** — one line: what you're selling, to whom. Every grade is relative to this. Write it properly.
2. **`columns`** — map the logical fields to your actual CSV column names. Get this right or nothing matches.
3. **`account_disqualifiers`** — substrings of the company description that mean *wrong company*. Checked first, because wrong company beats everything else.
4. **`owner_titles`** (→ A) — who owns this exact problem by job description.
5. **`decision_titles`** (→ B) — who can decide when there's no dedicated owner.
6. **`wrong_person_titles`** (→ D) — right company, wrong function.
7. **`junior_titles`** (→ C) — right function, not the entry point.

Titles are matched as lowercase **substrings**, so `partner` also matches `Managing Partner`. That's why `decision_title_exclusions` contains `vice president` — otherwise it matches the `president` substring. Keep that.

## Step 2 — read the rubric back before trusting it

```bash
python3 skills/qualify-leads/grade_fit.py --rubric rubrics/my-campaign.json \
    --file research/enriched.csv --explain
```

Prints the rubric in plain English and exits. If the printout doesn't match what you meant, fix the JSON now — before it grades 300 people.

## Step 3 — grade

```bash
python3 skills/qualify-leads/grade_fit.py --rubric rubrics/my-campaign.json \
    --file research/enriched.csv --profiles scratch/profiles_joined.json --sort
```

First rule that matches wins, deliberately in this order:

| # | Check | Grade |
|---|---|---|
| 1 | `account_disqualifiers` | E — wrong company, nothing else matters |
| 2 | `role_type_rules` | D — structurally wrong person |
| 3 | `wrong_person_titles` | D — wrong function |
| 4 | `owner_titles` | A |
| 5 | `decision_titles` | B |
| 6 | `junior_titles` | C |
| 7 | `default` | C |

`--profiles` enables `employer_check`: does the scraped LinkedIn profile agree about where this person currently works? **It flags, it never downgrades** — it compares normalised company names, so it cannot tell a rebrand from a departure, and it trips on people who legitimately hold two roles.

**Nothing is ever dropped.** Grading is advisory.

## Step 4 — read the rows by hand

This is the part that can't be automated:
- every **D** and **E** row — the rubric is blunt, and a wrong grade is a lost prospect
- every **`employer_check`** flag
- a sample of **A** rows — if an A looks wrong, the rubric is wrong

## Step 5 — record the human calls

Put them in an overrides file, never by hand-editing the CSV, so anyone can see which grades a human changed and why:

```json
{
  "ok_rebrand": {
    "note": "company renamed; the row is correct",
    "clears_employer_check": true,
    "contacts": {"row12": "Calvert Street rebranded to Parkway Capital in 2024"}
  },
  "left_company": {
    "grade": "E",
    "note": "no longer at the company we filed them under",
    "contacts": {"row40": "profile shows they moved to an operating role elsewhere"}
  }
}
```

```bash
python3 skills/qualify-leads/apply_overrides.py --file research/enriched.csv \
    --overrides rubrics/my-campaign-overrides.json --sort
```

Keys are row keys: the `contact_id` column if your list has one, else `row<N>` by zero-based input order. The script warns about override keys that matched no row — that means a stale key or the wrong file.

## Checkpoint
Report: the A–E mix, how many rows are A/B **and** have a verified email (that's your actual reachable list), employer mismatches outstanding, and which grades a human overrode. Grade again if the list is later re-enriched — new facts change fit.
