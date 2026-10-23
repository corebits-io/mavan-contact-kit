---
name: build-list
description: Build a prospect list from an ICP using a data tool (Clay or Apify) when you do not already have one. Optional. Use before research-list. Falls back to bring-your-own CSV if no tool is configured.
allowed-tools: Read Write Edit Bash WebSearch WebFetch Glob
---

# Build List

Produce a clean prospect list matching the ICP, each row with a real LinkedIn URL.

Optional. If a list already exists, skip this and drop the CSV in `leads/`.

**Read:** `ICP.md` (the target definition and hard exclusions) and `.env` (which data tool is available).

**Write:** `leads/<name>.csv` with columns `name, title, company, linkedin_url`.

## Steps (full detail in playbooks/build-list.md)
1. Read the ICP and the hard exclusions. Restate the target back in one line — industry, stage, geography, titles — and get a yes before spending anything.
2. Pick the tool: **Clay** (via its MCP connector) if connected; else **Apify** (`APIFY_API_TOKEN`); else **stop** and ask for a CSV export in `leads/`.
3. Companies first, then the right person at each, per the persona rules in `ICP.md`. Get a real LinkedIn URL for every row.
4. Cap size and cost. With Apify always pass `maxTotalChargeUsd` — some actors ignore `maxItems`. De-dupe by company and by LinkedIn URL. Drop the hard exclusions.
5. Write the CSV. Show the first rows, the count, how many were dropped and why, and the run cost. Hand off to `research-list`.

## Rules
- **Real LinkedIn URLs only.** Never fabricate or guess a profile URL. No verifiable URL means drop the row or flag it — a guessed URL poisons every step after this one.
- Cap spend explicitly on every paid run.
- One contact per company unless the ICP says otherwise.
