---
name: find-people
description: Find the right person at a company from its website domain (founder, CEO, owner, managing director, partner) and get a verified work email. Prospeo search and enrich, Better Contact fallback, BounceBan verify. Use when you have a company and need the person.
allowed-tools: Read Write Bash Glob Grep
---

# find-people

One script, three APIs, keys read from the kit's `.env` (never printed).

```
python3 skills/find-people/find_people.py --domain acme.com --titles founder,ceo,"chief executive" --enrich 2 --fallback --out research/acme.com.csv
```

## What it does, in order
1. **Prospeo Search Person** lists everyone at the domain (25 per page, `--pages 2` default). 1 credit per page, repeats free for 30 days.
2. `--titles` keeps rows whose title matches any keyword. `--enrich N` enriches the first N kept rows.
3. **Prospeo Enrich Person** (`only_verified_email: true`) returns a verified email. 1 credit each, free again within 90 days. Mobiles are 10 credits, only with `--mobile`.
4. `--fallback` sends Prospeo NO_MATCH rows to **Better Contact** (async, about 7 credits, polls up to two minutes). Founders often only resolve here.
5. **BounceBan** verifies every email found: `deliverable`, `risky`, `undeliverable`. Only `deliverable` goes on a send list.
6. Prints a table and writes the CSV: person_id, name, title, seniority, department, location, linkedin_url, email, email_status, bounceban, mobile.

## Title sets for the Mavan ICP
- Group A (owner operators): `--titles founder,ceo,"chief executive"`
- Matching is by substring, so `president` also catches `Vice President` and `owner` catches `Procurement Owner`. Add them only with `--enrich 2` or more and read the titles before trusting a row.
- Group B (sell side bankers): `--titles "managing director,partner,principal,founder"`

## One person, name and LinkedIn known
```
python3 skills/find-people/find_people.py --domain acme.com \
  --linkedin https://www.linkedin.com/in/jane-doe/ \
  --name "Jane Doe" --company "Acme" --fallback
```
Always pass `--name` and `--company` with `--linkedin`. Without them Better Contact only gets the URL slug and misses.

## Guardrails
- Never guess an email. No verified address means the row is `not found`, which is a real answer.
- `risky` is a catch all domain. It never counts as found.
- Run one domain at a time. No parallel runs.
- Keys from `.env` only. Never print them, never paste them into a reply.
- Check the location column: a same named company in another country shows up in the search.
- Output goes to `research/<domain>.csv`. One person per company unless `ICP.md` says otherwise.
