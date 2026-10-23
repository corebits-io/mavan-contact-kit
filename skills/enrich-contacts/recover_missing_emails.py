#!/usr/bin/env python3
"""
Recover emails both finders missed, by inferring the company's address pattern
and letting BounceBan adjudicate. Runs after enrich.py + repick_best_email.py.

Why this works: both finders report only what they have observed, so they go
blank on small companies with no public email footprint. The misses therefore
cluster BY COMPANY, not randomly. Where a colleague on the same domain did
verify, that company's pattern is visible, and the missing person's address can
be constructed and then actually tested.

Three rules keep it honest — do not relax them:
  - only keep a candidate BounceBan calls "deliverable". risky/accept-all is
    discarded, because on a catch-all domain literally every guess "verifies".
  - catch-all is detected FIRST, with a nonsense address. If that verifies, the
    whole domain is skipped and nothing is claimed for anyone there.
  - recovered rows are marked best_email_source=pattern_inferred and
    email_confidence=medium. Never "high" — nobody independently found these.

Usage:
  python3 recover_missing_emails.py --file research/list-enriched.csv --dry-run
  python3 recover_missing_emails.py --file research/list-enriched.csv
"""
import os, re, sys, csv, time, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


def clean(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


PATTERNS = {
    "first.last": lambda f, l: f"{f}.{l}",
    "flast":      lambda f, l: f"{f[0]}{l}",
    "first":      lambda f, l: f,
    "firstlast":  lambda f, l: f"{f}{l}",
    "last":       lambda f, l: l,
    "first_last": lambda f, l: f"{f}_{l}",
    "f.last":     lambda f, l: f"{f[0]}.{l}",
    "lastf":      lambda f, l: f"{l}{f[0]}",
    "firstl":     lambda f, l: f"{f}{l[0]}",
}


def detect(local, f, l):
    for name, fn in PATTERNS.items():
        try:
            if local == fn(f, l):
                return name
        except Exception:
            pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="enriched CSV to update in place")
    ap.add_argument("--domain-column", default="", help="column holding the company domain (auto-detected if omitted)")
    ap.add_argument("--max-tries", type=int, default=5, help="candidate patterns to test per person (1 credit each)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be tried, spend nothing")
    C.add_project_arg(ap)
    args = ap.parse_args()

    env = C.load_env(args, required=("BOUNCER_API_KEY",)) if not args.dry_run else {}

    with open(args.file) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("no rows")

    dom_col = args.domain_column or C.pick_domain_column(rows)
    if not dom_col:
        raise SystemExit(
            "no company-domain column found (looked for firm_domain / company_domain / domain).\n"
            "This step needs one to build candidate addresses. Pass --domain-column."
        )

    # 1. learn each domain's pattern from colleagues who DID verify there
    dom_pats = collections.defaultdict(collections.Counter)
    for r in rows:
        em, dom = (r.get("best_email") or ""), (r.get(dom_col) or "").lower()
        if not em or not dom or dom not in em.lower():
            continue
        if r.get("bounceban_result") != "deliverable":
            continue
        f, l = (clean(x) for x in C.split_name(r))
        if not f or not l:
            continue
        p = detect(em.split("@")[0].lower(), f, l)
        if p:
            dom_pats[dom][p] += 1
    print(f"learned a pattern for {len(dom_pats)} domain(s) from already-verified colleagues")

    targets = [r for r in rows if not (r.get("best_email") or "").strip() and (r.get(dom_col) or "").strip()]
    print(f"{len(targets)} row(s) with no email and a known domain\n")

    catchall, recovered, skipped = {}, 0, 0
    for r in targets:
        dom = (r.get(dom_col) or "").lower().replace("www.", "")
        f, l = (clean(x) for x in C.split_name(r))
        name = C.display_name(r)
        if not f or not l or len(l) < 2:
            print(f"  SKIP  {name:<24} name unusable for pattern building")
            skipped += 1
            continue

        # 2. catch-all check — if a nonsense address passes, nothing here is provable
        if dom not in catchall:
            if args.dry_run:
                catchall[dom] = False
            else:
                res = C.bounceban_verify(env, f"zz-no-such-user-9182@{dom}")["result"].lower()
                catchall[dom] = res in ("deliverable", "risky")
                time.sleep(0.2)
        if catchall[dom]:
            print(f"  SKIP  {name:<24} {dom} is catch-all — a guess there cannot be verified")
            skipped += 1
            continue

        # 3. this company's own observed pattern first, then the common fallbacks
        order = [p for p, _ in dom_pats[dom].most_common()]
        order += [p for p in ("flast", "first.last", "first", "firstlast", "last") if p not in order]

        hit = None
        for p in order[:args.max_tries]:
            cand = f"{PATTERNS[p](f, l)}@{dom}"
            if args.dry_run:
                print(f"  WOULD TRY {name:<20} {cand} ({p})")
                continue
            v = C.bounceban_verify(env, cand)
            time.sleep(0.2)
            if str(v["result"]).lower() == "deliverable":
                hit = (cand, v["score"], p)
                break
        if args.dry_run:
            continue

        if hit:
            cand, score, p = hit
            r["best_email"] = cand
            r["best_email_source"] = "pattern_inferred"
            r["bounceban_result"] = "deliverable"
            r["bounceban_score"] = score
            r["email_confidence"] = "medium"      # never "high" — not independently found
            r["email_agreement"] = "inferred"
            flag = f"email not found by either finder; built from the {p} pattern used at {dom} and BounceBan-verified"
            r["data_flags"] = ((r.get("data_flags") or "") + " | " if r.get("data_flags") else "") + flag
            recovered += 1
            print(f"  FOUND {name:<24} {cand}  ({p}, score {score})")
        else:
            print(f"  none  {name:<24} no pattern verified at {dom}")

    if args.dry_run:
        print("\n(dry run — nothing written, no credits spent)")
        return

    C.write_csv(args.file, rows)
    still = sum(1 for x in rows if not (x.get("best_email") or "").strip())
    print(f"\nrecovered {recovered} | skipped {skipped} | still missing {still} -> {args.file}")


if __name__ == "__main__":
    main()
