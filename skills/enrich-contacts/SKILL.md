---
name: enrich-contacts
description: Find and verify email + phone for a leads CSV using two independent finders (Prospeo + Better Contact), cross-check them, verify the email with BounceBan, and pull full LinkedIn profiles via Apify for summarizing. Use after a researched list exists and before writing outreach.
allowed-tools: Read Write Edit Bash Glob Grep
---

# Enrich Contacts

Turns a leads CSV into a list with a **verified** email, a cross-checked phone, and a factual LinkedIn profile summary per row.

**Costs real money per row.** Always do a `--limit 5` run first and read the output before running the full list.

## Tool roles — do not confuse these
| Tool | Role | Notes |
|---|---|---|
| **Prospeo** | FINDER | email + mobile from a LinkedIn URL. Mobile reveal ~10 credits |
| **Better Contact** | FINDER | independent waterfall, async batch. ~7 credits/row |
| **BounceBan** | VERIFIER ONLY | judges an address; **cannot find one**. 1 credit/email |
| **Apify** | profile scrape | About text + per-experience descriptions |

The two-finder cross-check is the entire point. One finder gives you an address with no way to judge it; two finders plus a verifier give you something you can actually send to.

`.env` note: the key line is named `BOUNCER_API_KEY` but holds the **BounceBan** key.

## Steps (full detail in playbooks/enrich-contacts.md)

```bash
# 1. find + verify. Test on 5 first. Run big lists in chunks of ~45.
python3 skills/enrich-contacts/enrich.py --in leads/list.csv \
    --out research/list-enriched.csv --limit 5

# 2. retry verifier errors, and re-pick best_email preferring the company's OWN domain
python3 skills/enrich-contacts/repick_best_email.py --chunks 'research/list-enriched*.csv'

# 3. (optional) recover finder misses by inferring the company's address pattern
python3 skills/enrich-contacts/recover_missing_emails.py --file research/list-enriched.csv --dry-run

# 4. scrape profiles, 10 at a time, tagged by start index
python3 skills/enrich-contacts/apify_profiles.py --in leads/list.csv --start 0 --limit 10 --tag b0

# 5. join profiles back onto the rows, then READ profiles_bad.json
python3 skills/enrich-contacts/join_apify.py --in leads/list.csv --scratch scratch/
```

6. Summarize each profile into a short factual `profile_summary` (2–4 sentences: who they are, tenure, background, anything factual worth knowing). If a scrape failed, say so in the summary rather than guessing.

## Things that will bite you
- **Step 2 is not optional on a real campaign.** `enrich.py` breaks ties toward Prospeo; that can hand you a prospect's old-employer or portfolio-company address. It verifies fine and is still the wrong inbox.
- **`risky` ≠ good.** It means a catch-all domain accepted the probe. It proves nothing about that specific mailbox. Email misses cluster **by company** (catch-all domains), not randomly — so probe for catch-all before blaming coverage.
- **Better Contact maps by index.** It does not echo back the `linkedin_url`. If the returned row count differs from what you submitted, the script warns — stop and check by hand.
- **Apify joins positionally**, because the actor returns the profile's canonical vanity URL, not the URL you queried. The `--tag b<N>` must encode the start index or the join silently misaligns.
- **Apify free plan: 10 items/run, 20 runs/account, $5/month.** Past a limit the actor *succeeds* and returns a single `{"error": ...}` item. A short batch means a limit was hit, not that those people don't exist. Keep a second token as `APIFY_API_TOKEN_2` and switch with `APIFY_KEY=APIFY_API_TOKEN_2`.

## Columns added
`prospeo_email, prospeo_bb_result, bettercontact_email, bettercontact_bb_result, email_agreement, best_email, best_email_source, bounceban_result, bounceban_score, email_confidence, best_mobile, phone_agreement, phone_confidence, profile_summary`

`email_confidence`: `high` = both finders agree **and** it verifies deliverable · `medium` = verifies, one source only · `low` = catch-all, unprovable · `unusable` = undeliverable or verifier error · `none` = nothing found.

## Guardrails
- **Never print an API key value.** Read them from `.env`.
- Trust `bounceban_result` for send-safety, always.
- **No message-writing here.** Summaries are factual. Outreach copy happens later, in the sender's own voice.
- Never mark a `pattern_inferred` email as `high` confidence — nobody independently found it.
