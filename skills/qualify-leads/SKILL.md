---
name: qualify-leads
description: Grade every lead A-E for fit with one specific campaign using a reviewable rubric file, flag employer mismatches against scraped LinkedIn profiles, and apply human overrides. Use after enrich-contacts and before any outreach.
allowed-tools: Read Write Edit Bash Glob Grep
---

# Qualify Leads

Grade each row A–E for fit with **one** campaign, so outreach only goes to people it should. Vetting fit *before* contacting is the difference between a list and a liability.

**Read:** the enriched CSV, and a rubric in `rubrics/`.
**Write:** `fit_grade`, `fit_reason`, `employer_check`, and (after overrides) `status_flag`, `status_note`.

## The rubric is the work
The grading logic lives in a JSON file, not in the script, because a fit rubric is a business judgement that changes per campaign and has to stay arguable.

- `rubrics/TEMPLATE.json` — copy this, one per campaign
- `rubrics/EXAMPLE-lmm-pe-deal-origination.json` — a real shipped rubric, read it for the level of specificity needed

Write the `campaign` line properly. Every grade is relative to it.

## Steps (full detail in playbooks/qualify-leads.md)

```bash
# 1. write the rubric, then read it back in plain English before trusting it
python3 skills/qualify-leads/grade_fit.py --rubric rubrics/my-campaign.json \
    --file research/list-enriched.csv --explain

# 2. grade. --profiles enables employer_check against the scraped LinkedIn data
python3 skills/qualify-leads/grade_fit.py --rubric rubrics/my-campaign.json \
    --file research/list-enriched.csv --profiles scratch/profiles_joined.json --sort

# 3. read every D and E row, plus every employer_check flag, by hand

# 4. record the human calls in an overrides file, then apply
python3 skills/qualify-leads/apply_overrides.py --file research/list-enriched.csv \
    --overrides rubrics/my-campaign-overrides.json --sort
```

## Grade meanings (default)
| Grade | Meaning |
|---|---|
| **A** | Owns this exact problem by job description |
| **B** | Can decide, no dedicated owner to route around them |
| **C** | Right company and function, but junior or not the entry point |
| **D** | Right company, wrong person |
| **E** | Wrong company — do not contact |

## Guardrails
- **Nothing is ever dropped.** Grading is advisory and stays reviewable. Cutting rows is a human decision made after reading them.
- **`employer_check` flags, it never downgrades.** It compares normalised company names, so it cannot tell a rebrand from a departure, and it trips on people who legitimately hold two roles. Read the flag, then decide.
- **Overrides go in the JSON file, with a reason.** Never hand-edit a grade in the CSV and never bury a judgement call in code — anyone should be able to see which grades a human changed and why.
- Grade at discovery *and* again after enrichment. New facts change fit.
- A `D`/`E` grade on a real person is a lost prospect if the rubric was blunt. Read them before you cut them.
