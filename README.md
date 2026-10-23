# Mavan contact kit

Four Claude Code skills that take you from an ICP to a graded, contactable prospect list:

```
build-list  →  research-list  →  enrich-contacts  →  qualify-leads
   (who)         (facts)          (email/phone)        (fit A to E)
```

**This kit does not send anything.** No LinkedIn account, no email account, no outreach copy. Its only output is a CSV. That is deliberate. You can run all of it without any risk of a message going out in someone's name.

---

## Setup (5 minutes)

```bash
git clone https://github.com/corebits-io/mavan-contact-kit.git
cd mavan-contact-kit
cp .env.example .env        # then fill in your own API keys
python3 --version           # 3.8+; no pip installs needed
```

Then open the folder in Claude Code. The skills register on restart.

### Two ways to use it

**A. Work inside this repo** (simplest). Put lists in `leads/`, get output in `research/`.

**B. Install as a plugin** and work in your own project:
```
/plugin marketplace add corebits-io/mavan-contact-kit
/plugin install prospect-data-kit
```
The scripts find your `.env` by walking up from your working directory, so they work either way. Override with `--project /path` or `$PDK_PROJECT` if needed.

---

## What each skill needs

| Skill | Needs | Cost |
|---|---|---|
| `build-list` | Clay connector **or** `APIFY_API_TOKEN` | Apify: pay per run, always capped |
| `research-list` | nothing, free web search | free |
| `enrich-contacts` | `PROSPEO_API_KEY`, `BETTERCONTACT_API_KEY`, `BOUNCER_API_KEY`, `APIFY_API_TOKEN` | ~real money per row |
| `qualify-leads` | a rubric in `rubrics/` | free |

Only `enrich-contacts` spends meaningfully. **Always `--limit 5` first.**

---

## The full run

```bash
# 1. build or drop in a list        -> leads/list.csv (name, title, company, linkedin_url)
# 2. research it                    -> research/list-researched.csv
# 3. find + verify contact data
python3 skills/enrich-contacts/enrich.py --in leads/list.csv --out research/list-enriched.csv --limit 5
python3 skills/enrich-contacts/enrich.py --in leads/list.csv --out research/list-enriched.csv
python3 skills/enrich-contacts/repick_best_email.py --chunks 'research/list-enriched*.csv'

# 4. scrape profiles, 10 at a time (Apify free-plan cap)
python3 skills/enrich-contacts/apify_profiles.py --in leads/list.csv --start 0  --limit 10 --tag b0
python3 skills/enrich-contacts/apify_profiles.py --in leads/list.csv --start 10 --limit 10 --tag b10
python3 skills/enrich-contacts/join_apify.py --in leads/list.csv --scratch scratch/

# 5. grade for fit
cp rubrics/TEMPLATE.json rubrics/my-campaign.json      # then fill it in
python3 skills/qualify-leads/grade_fit.py --rubric rubrics/my-campaign.json --explain \
    --file research/list-enriched.csv
python3 skills/qualify-leads/grade_fit.py --rubric rubrics/my-campaign.json \
    --file research/list-enriched.csv --profiles scratch/profiles_joined.json --sort
```

Every script takes `--help`.

---

## The five rules

1. **Never invent data.** No fabricated signals, names, numbers, or sources. `confidence = none` is an honest and useful outcome. A made-up hook gets caught in the reply.
2. **Two finders, then a verifier.** One source is an address with no way to judge it. Never send to an address that hasn't been verified.
3. **`risky` is not a pass.** It means a catch-all domain accepted the probe. It proves nothing about that mailbox.
4. **Test on 5 rows before running the list.** Every enrichment row costs credits, and a bad column mapping burns all of them.
5. **Research is factual. Messaging is not this kit's job.** No hooks, no openers, no draft copy. That happens later, in the sender's own voice.

Full operating instructions in [CLAUDE.md](CLAUDE.md). Detailed procedures in [playbooks/](playbooks/).

---

## Layout

```
skills/            the four skills (SKILL.md + scripts)
playbooks/         the detailed procedure behind each skill
rubrics/           fit rubrics: TEMPLATE.json plus a real worked example
examples/          campaign-specific scripts kept as reference patterns, not for reuse
ICP.md             fill this in: who you're targeting and who to exclude
leads/             your input lists      (gitignored)
research/          output               (gitignored)
scratch/           intermediate JSON     (gitignored)
.env               your API keys         (gitignored, never commit)
```

---

## Have a company, need the person? Use `find-people`

```bash
python3 skills/find-people/find_people.py --domain acme.com --titles founder,ceo,"chief executive" --enrich 2 --fallback --out research/acme.com.csv
```

Lists everyone Prospeo knows at the domain, keeps the titles you asked for, finds a verified email for the first match (Better Contact as the fallback), and verifies it with BounceBan. One domain at a time. Only `bounceban = deliverable` rows go on a send list. Plain English walkthrough in [HOW-TO-USE.md](HOW-TO-USE.md).
