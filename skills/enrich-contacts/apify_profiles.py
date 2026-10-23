#!/usr/bin/env python3
"""
Scrape full LinkedIn profiles (About text + per-experience descriptions) via Apify,
so a human-readable profile summary can be written for each prospect.

Actor: harvestapi/linkedin-profile-scraper — no LinkedIn cookies needed.
Mode:  "Profile details no email" (~$4/1k) because the finders already got email.

FREE-PLAN LIMITS — you will hit these:
  * 10 items per run, 20 runs per account, $5/month cap.
  * Past a limit the actor SUCCEEDS and returns a single {"error": ...} item
    instead of failing. A short batch means a limit was hit, NOT that those
    people don't exist. This script checks for that and says so.
  Keep a second token as APIFY_API_TOKEN_2 and switch with APIFY_KEY.

Usage:
  python3 apify_profiles.py --in leads/list.csv --start 0  --limit 10 --tag b0
  APIFY_KEY=APIFY_API_TOKEN_2 python3 apify_profiles.py --in leads/list.csv --start 10 --limit 10 --tag b10

The --tag must encode the start index (b<N>) — join_apify.py maps results back
to input rows positionally and reads that number.
"""
import os, sys, json, time, csv, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

ACTOR = "harvestapi~linkedin-profile-scraper"
MODE = "Profile details no email ($4 per 1k)"


def token(args):
    """APIFY_KEY names WHICH .env line to bill, so a second free account can take
    over when the first hits its monthly cap."""
    key = os.environ.get("APIFY_KEY", "APIFY_API_TOKEN")
    env = C.load_env(args)
    if not env.get(key):
        raise SystemExit(f"no {key} in .env (set APIFY_KEY to pick a different token line)")
    return env[key], key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="leads CSV with a linkedin_url column")
    ap.add_argument("--limit", type=int, default=10, help="batch size (free plan caps at 10)")
    ap.add_argument("--start", type=int, default=0, help="row index to start at")
    ap.add_argument("--tag", default="", help="batch tag, use b<start> e.g. b30")
    ap.add_argument("--out-dir", default="", help="where to write JSON (default $PDK_SCRATCH or <project>/scratch)")
    C.add_project_arg(ap)
    args = ap.parse_args()

    tok, which = token(args)
    print(f"billing Apify token: {which}")
    out_dir = args.out_dir or C.scratch_dir(args)
    os.makedirs(out_dir, exist_ok=True)

    with open(args.inp) as f:
        rows = list(csv.DictReader(f))
    batch = rows[args.start:]
    if args.limit:
        batch = batch[:args.limit]
    urls = [r["linkedin_url"] for r in batch if (r.get("linkedin_url") or "").strip()]
    if not urls:
        raise SystemExit(f"no linkedin_urls in rows {args.start}..{args.start + args.limit}")
    tag = args.tag or f"b{args.start}"
    print(f"scraping {len(urls)} profiles (rows {args.start}..{args.start + len(batch) - 1}, tag {tag})")

    st, run = C.post_json(f"https://api.apify.com/v2/acts/{ACTOR}/runs?token={tok}",
                          {}, {"profileScraperMode": MODE, "urls": urls}, timeout=60)
    run_id = (run.get("data") or {}).get("id")
    ds_id = (run.get("data") or {}).get("defaultDatasetId")
    if not run_id:
        raise SystemExit(f"failed to start run (HTTP {st}): {str(run)[:300]}")
    print(f"run {run_id} started (dataset {ds_id})")

    waited = 0
    status = None
    while waited < 1200:
        _, s = C.get_json(f"https://api.apify.com/v2/actor-runs/{run_id}?token={tok}", timeout=30)
        status = (s.get("data") or {}).get("status")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            print(f"run finished: {status}")
            break
        time.sleep(20)
        waited += 20
        print(f"  polling... {waited}s ({status})")

    _, items = C.get_json(f"https://api.apify.com/v2/datasets/{ds_id}/items?token={tok}&clean=true", timeout=120)
    if not isinstance(items, list):
        raise SystemExit(f"unexpected dataset payload: {str(items)[:300]}")

    # The silent-failure case: run SUCCEEDED but the dataset is one error object.
    errs = [it for it in items if isinstance(it, dict) and it.get("error") and not it.get("headline")]
    if errs and len(errs) == len(items):
        print(f"\n!! Apify returned only an error item, not profiles: {str(errs[0])[:200]}")
        print("!! This is almost always a free-plan limit (10 items/run, 20 runs, $5/mo).")
        print(f"!! Switch accounts:  APIFY_KEY=APIFY_API_TOKEN_2 python3 {os.path.basename(__file__)} ...")
        raise SystemExit(2)

    json.dump(items, open(os.path.join(out_dir, f"apify_raw_{tag}.json"), "w"))

    trim = []
    for it in items:
        if not isinstance(it, dict):
            continue
        exp = [{"position": e.get("position"), "company": e.get("companyName"),
                "duration": e.get("duration"), "description": e.get("description")}
               for e in (it.get("experience") or [])[:6]]
        edu = [{"school": e.get("schoolName") or e.get("title"),
                "degree": e.get("degree") or e.get("subtitle")}
               for e in (it.get("education") or [])[:3]]
        loc = it.get("location")
        trim.append({
            "linkedin_url": it.get("linkedinUrl") or it.get("originalQuery"),
            "name": f"{it.get('firstName','')} {it.get('lastName','')}".strip(),
            "headline": it.get("headline"),
            "about": it.get("about"),
            "location": loc.get("linkedinText") if isinstance(loc, dict) else loc,
            "topSkills": it.get("topSkills"),
            "experience": exp, "education": edu,
        })

    fname = f"apify_profiles_trim_{tag}.json"
    json.dump(trim, open(os.path.join(out_dir, fname), "w"), indent=1)
    got_about = sum(1 for t in trim if t["about"])
    print(f"DONE: {len(trim)} profiles | with About text: {got_about} -> {out_dir}/{fname}")
    if len(trim) < len(urls):
        print(f"  [warn] asked for {len(urls)}, got {len(trim)} — likely a plan limit. "
              "Re-run the shortfall on another token before treating this batch as complete.")


if __name__ == "__main__":
    main()
