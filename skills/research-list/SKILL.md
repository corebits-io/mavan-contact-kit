---
name: research-list
description: Research every prospect in a leads CSV using free web search and write the factual findings into a new researched file. Use after a list exists in leads/ and before enriching or writing outreach.
allowed-tools: Read Write Edit Bash WebSearch WebFetch Glob
---

# Research List

Turn a plain list into a researched list: what each company does, and one real, recent, specific signal per row. Costs nothing but time — it is web search only.

**Read:** the leads CSV in `leads/` and `ICP.md` (so you know which signals matter for this offer).

**Write:** `research/<listname>-researched.csv` — the original columns plus `what_they_do, signal, signal_source, confidence`.

## Steps (full detail in playbooks/research-list.md)
1. Load the CSV, report the row count, and say research runs in batches of ~10.
2. **Per company (reliable):** find the site, read what they actually do. Search the company name for recent news — funding, launches, hiring, product changes. Keep the single most relevant recent item.
3. **Per person (partial):** search `"name" "company"` for public posts, podcasts, press, talks. Note anything showing what they personally care about.
4. Fill `what_they_do` (one plain line, no buzzwords), `signal` (the one real recent thing), `signal_source` (the URL you actually read), and `confidence`.
5. Save to `research/`. Show a compact table of the first rows plus the confidence breakdown.

## Rules
- **Never invent a signal, source, number, or quote.** `confidence = none` with empty `signal` is an honest, acceptable, and useful outcome. A fabricated hook is worse than no hook — it gets caught in the reply.
- `confidence`: `verified` = you have a source URL you can point to. `likely` = reasonable but softer. `none` = nothing real found.
- **Do not write outreach copy here.** No hook sentences, no openers, no draft messages. Research is factual only; messaging happens later, in the sender's own voice.
- LinkedIn profiles are usually gated to anonymous fetches. Treat any LinkedIn content you do get as a bonus, never a dependency.
- Batch ~10 rows and pause between batches. Stay well under 300 requests/minute.
