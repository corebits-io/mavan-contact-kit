#!/usr/bin/env python3
"""
Post-process enriched chunks. Costs almost nothing — reuses data already paid for.

1. Retry BounceBan wherever the VERIFIER itself errored (err:*), so a transient
   network failure never gets recorded as a bad address.

2. Re-pick best_email preferring the target company's OWN domain. enrich.py
   breaks ties toward Prospeo, which is the wrong rule once you care about which
   inbox you land in: a prospect's old-employer or portfolio-company address can
   verify perfectly and still be the wrong place to reach them for this campaign.

The company domain is read from a column on the row itself (firm_domain /
company_domain / domain), or from a separate accounts CSV via --accounts.
Without a domain anywhere, step 2 is skipped and only step 1 runs.

Usage:
  python3 repick_best_email.py --chunks 'research/list-enriched-*.csv'
  python3 repick_best_email.py --chunks 'research/*.csv' --accounts leads/accounts.csv \
      --accounts-key row_id --rows-key account_row_id --accounts-domain domain
"""
import os, re, sys, csv, glob, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True,
                    help="glob of enriched CSVs to rewrite in place, e.g. 'research/x-*.csv'")
    ap.add_argument("--accounts", default="", help="optional company-level CSV holding the domain")
    ap.add_argument("--accounts-key", default="row_id", help="join column in the accounts CSV")
    ap.add_argument("--rows-key", default="account_row_id", help="join column in the lead rows")
    ap.add_argument("--accounts-domain", default="domain", help="domain column in the accounts CSV")
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    C.add_project_arg(ap)
    args = ap.parse_args()

    env = C.load_env(args, required=("BOUNCER_API_KEY",))

    accounts = {}
    if args.accounts:
        with open(args.accounts) as f:
            for a in csv.DictReader(f):
                accounts[a.get(args.accounts_key, "")] = a

    files = sorted(glob.glob(args.chunks))
    if not files:
        raise SystemExit(f"no files matched {args.chunks}")
    # numeric sort when the names are numbered, so chunk 10 follows chunk 9
    def order(p):
        m = re.search(r"(\d+)", os.path.basename(p))
        return (int(m.group(1)) if m else 0, p)
    files.sort(key=order)

    retried = changed = no_domain = 0
    for fp in files:
        with open(fp) as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        dom_col = C.pick_domain_column(rows)

        for r in rows:
            r.setdefault("best_email_prev", "")   # keep the header stable across rows
            r["best_email_prev"] = ""
            pe = (r.get("prospeo_email") or "").strip()
            be = (r.get("bettercontact_email") or "").strip()

            # 1. retry verifier errors
            for em, rk, sk in ((pe, "prospeo_bb_result", "prospeo_bb_score"),
                               (be, "bettercontact_bb_result", "bettercontact_bb_score")):
                if em and str(r.get(rk, "")).startswith("err"):
                    v = C.bounceban_verify(env, em)
                    r[rk], r[sk] = v["result"], v["score"]
                    retried += 1
                    time.sleep(0.2)

            # 2. re-pick, preferring the company's own domain among equal verdicts
            target_domain = ""
            if dom_col:
                target_domain = r.get(dom_col, "")
            if not target_domain and accounts:
                target_domain = accounts.get(r.get(args.rows_key, ""), {}).get(args.accounts_domain, "")
            if not target_domain:
                no_domain += 1

            cands = []
            if pe:
                cands.append((pe, r.get("prospeo_bb_result", ""), r.get("prospeo_bb_score", ""), "prospeo"))
            if be and be.lower() != pe.lower():
                cands.append((be, r.get("bettercontact_bb_result", ""),
                              r.get("bettercontact_bb_score", ""), "bettercontact"))
            if not cands:
                continue
            cands.sort(key=lambda c: (C.RANK.get(str(c[1]).lower(), 0),
                                      1 if C.same_domain(c[0], target_domain) else 0,
                                      int(c[2] or 0),
                                      1 if c[3] == "prospeo" else 0), reverse=True)
            best, res, score, src = cands[0]
            if best != r.get("best_email"):
                changed += 1
                r["best_email_prev"] = r.get("best_email", "")
                if args.dry_run:
                    print(f"  {C.display_name(r):<24} {r.get('best_email','-')} -> {best}")
            r["best_email"], r["best_email_source"] = best, src
            r["bounceban_result"], r["bounceban_score"] = res, score
            r["email_confidence"] = C.email_confidence(r.get("email_agreement"), res, best)

        if not args.dry_run:
            C.write_csv(fp, rows)

    print(f"files: {len(files)} | bounceban retries: {retried} | best_email changed: {changed}")
    if no_domain:
        print(f"  [note] {no_domain} row(s) had no company domain — domain preference "
              "could not be applied there. Add a firm_domain/company_domain column, or pass --accounts.")
    if args.dry_run:
        print("  (dry run — nothing written)")


if __name__ == "__main__":
    main()
