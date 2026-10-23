# Playbook — Research the list

**Goal:** for every prospect, one plain line on what the company does and one real, recent, specific signal. Written to `research/`. No fabrication.

Costs nothing but time — this is web search only.

## Inputs to read first
- the leads CSV in `leads/` (`name, title, company, linkedin_url`)
- `ICP.md` — which signals matter for this offer, and which look like signals but aren't

## Steps

1. **Count and confirm.** Load the CSV, report the row count, say research runs in batches of about 10 and roughly how long that will take.

2. **Per company (reliable).** Find their site and read what they actually do. Web-search the company name for recent news: funding, launches, hiring, product changes, leadership moves. Capture the single most relevant, most recent item — not a list.

3. **Per person (partial).** Web-search `"name" "company"` for public posts, podcasts, press, talks. Note anything that shows what they personally care about.

   Do not assume a LinkedIn profile will load — it is usually gated to anonymous fetches. Treat any LinkedIn content you do get as a bonus, never a dependency. (The `enrich-contacts` step scrapes profiles properly, via Apify.)

4. **Record it factually.**
   - `what_they_do` — one plain line, no buzzwords
   - `signal` — the one real recent thing
   - `signal_source` — the URL you actually read. If you can't produce a URL, it isn't a source
   - `confidence` — see below

5. **Tag confidence honestly.**

   | Value | Means |
   |---|---|
   | `verified` | you have a source URL you can point to |
   | `likely` | reasonable but softer — inference from something real |
   | `none` | nothing real found. Leave `signal` and `signal_source` empty |

6. **Respect limits.** Batch ~10 rows, pause between batches on large lists. Stay well under 300 requests/minute.

## Output
`research/<listname>-researched.csv` — the input columns plus `what_they_do, signal, signal_source, confidence`, and a compact on-screen table of the first few rows plus the confidence breakdown.

## Guardrails

- **Never invent a signal, source, number, or quote.** `none` is an acceptable, honest, useful outcome. A fabricated detail gets caught in the reply and costs more than an empty cell ever would.
- **Do not write any outreach copy here** — no hooks, no openers, no draft sentences, not even parked in a spare column. Research is facts. Messaging is written later by the sender, in their own voice, with their own approval gate. Mixing the two is how you end up with generic templated copy.
- Keep `what_they_do` to one plain line. If you can't say it plainly, you haven't understood it yet.
- A signal that is two years old is not a signal.

## Checkpoint
Report rows researched, the confidence breakdown, and how many came back `none`. A high `none` rate is information — usually it means the list skews toward companies with no public footprint, which is worth knowing before spending enrichment credits on them.
