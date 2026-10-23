# Playbook — Build the list

**Goal:** a clean `leads/*.csv` of prospects matching the ICP, each with a real LinkedIn URL.

Optional. Skip it entirely if you already have a list — just drop the CSV in `leads/`.

## Inputs to read first
- `ICP.md` — the target (industry, size, stage, geography), the persona rules (who to target inside a company), and the hard exclusions
- `.env` — is `APIFY_API_TOKEN` set? Is Clay connected as an MCP connector?

## Steps

1. **Confirm the target in one line.** Restate industry/niche, size, stage, geography, and the titles to target. Get a quick yes **before spending anything.** This one line prevents the most expensive mistake available at this step.

2. **Choose the tool (graceful degradation):**
   - **Clay**, if its connector is available. Find fit companies, then the right person at each, with LinkedIn URLs.
   - **Apify**, if `APIFY_API_TOKEN` is set. `POST https://api.apify.com/v2/acts/<actor-id>/run-sync-get-dataset-items?token=<token>` with the actor's input JSON. **Always include `maxTotalChargeUsd`** so a run cannot overspend — some actors ignore `maxItems`.
   - **Neither:** stop. Ask for an export (Sales Navigator / Apollo / anywhere) with `name, title, company, linkedin_url` dropped into `leads/`. Do not improvise a list from web search.

3. **Companies first, then the person.** Pull companies that fit, then pick the one right contact per company using the persona rules in `ICP.md`. Get a real LinkedIn URL for each.

4. **Clean it.** De-dupe by company **and** by LinkedIn URL. Drop the hard exclusions (competitors and competitor-adjacent, existing clients, out-of-geography). Cap the list at the size that was asked for.

5. **Write and hand off.** Save `leads/<name>.csv` with `name, title, company, linkedin_url`. Show the first rows and the count. Hand off to `research-list`.

## Output
`leads/<name>.csv` — `name, title, company, linkedin_url`, real URLs only.

## Guardrails

- **Real LinkedIn URLs only.** Never fabricate or guess a profile URL. A guessed URL poisons everything downstream: research finds the wrong person, Prospeo returns the wrong email, and the profile scrape joins garbage onto a real name. If a row has no verifiable URL, drop it or flag it.
- **Cap spend explicitly on every paid run.** No exceptions.
- Respect the exclusions in `ICP.md`. Competitors are not prospects.
- One contact per company unless the ICP says otherwise. Two people at the same small company both getting outreach is how you look automated.

## Checkpoint
Summarize: final count, how many were dropped and why (excluded vs no verifiable URL), and the actual cost of the run. Then hand to `research-list`.
