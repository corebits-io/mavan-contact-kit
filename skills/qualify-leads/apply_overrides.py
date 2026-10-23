#!/usr/bin/env python3
"""
Apply human-verified overrides on top of the automated grade.

Why this exists: grade_fit.py's employer_check compares normalised company names.
Useful, but blunt. It cannot tell a rebrand (Calvert Street -> Parkway Capital)
from someone who left, it flags people who legitimately hold two roles, and it
says nothing when someone sits in a different arm of the same brand.

Those are human calls. Recording them in a JSON file keeps them REVIEWABLE —
anyone can see which grades a person overrode and why. Never bury them in code,
and never let a script silently "fix" a grade with no note attached.

Overrides file shape:
{
  "_comment": "free text, ignored",
  "ok_rebrand": {
    "note": "company renamed; the row is correct",
    "clears_employer_check": true,
    "contacts": {"row12": "Calvert Street rebranded to Parkway Capital in 2024"}
  },
  "left_company": {
    "grade": "E",
    "note": "no longer at the company we filed them under",
    "contacts": {"row40": "profile shows they moved to an operating role elsewhere"}
  }
}
Keys under "contacts" are row keys — the contact_id column if the list has one,
otherwise row<N> by zero-based input order (same key join_apify.py writes).

Usage:
  python3 apply_overrides.py --file research/list-enriched.csv --overrides overrides.json
"""
import os, sys, csv, json, argparse, collections

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "enrich-contacts"))
import _common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="graded CSV to update in place")
    ap.add_argument("--overrides", required=True, help="overrides JSON")
    ap.add_argument("--out", default="")
    ap.add_argument("--sort", action="store_true", help="re-sort best-fit + most-contactable first")
    C.add_project_arg(ap)
    args = ap.parse_args()

    O = json.load(open(args.overrides))
    lookup = {}
    for flag, block in O.items():
        if flag.startswith("_") or not isinstance(block, dict):
            continue
        for key, why in (block.get("contacts") or {}).items():
            lookup[key] = {"flag": flag,
                           "grade": block.get("grade"),
                           "clears": bool(block.get("clears_employer_check")),
                           "note": why or block.get("note", "")}

    with open(args.file) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("no rows")

    changed = matched = 0
    for idx, r in enumerate(rows):
        o = lookup.get(C.row_key(r, idx))
        r["status_flag"] = o["flag"] if o else "ok"
        r["status_note"] = o["note"] if o else ""
        if not o:
            continue
        matched += 1
        if o["clears"]:
            # a rebrand or a real dual role is NOT a reason to distrust the row
            r["employer_check"] = ""
            r["fit_reason"] = (r.get("fit_reason") or "").split("; verify employer")[0]
        elif o["grade"] and r.get("fit_grade") != o["grade"]:
            r["fit_grade"] = o["grade"]
            r["fit_reason"] = o["note"] or r.get("fit_reason", "")
            changed += 1

    unused = [k for k in lookup if k not in {C.row_key(r, i) for i, r in enumerate(rows)}]

    if args.sort:
        grank = {g: i for i, g in enumerate("ABCDE")}
        erank = {"high": 0, "medium": 1, "low": 2, "unusable": 3, "none": 4, "": 5}
        rows.sort(key=lambda x: (grank.get(x.get("fit_grade", ""), 9),
                                 erank.get(x.get("email_confidence", ""), 9),
                                 (x.get("company") or "").lower()))

    C.write_csv(args.out or args.file, rows)
    print(f"overrides matched {matched}/{len(lookup)} rows; grade changed on {changed}")
    print("status:", dict(sorted(collections.Counter(r["status_flag"] for r in rows).items())))
    print("fit   :", dict(sorted(collections.Counter(r.get("fit_grade", "") for r in rows).items())))
    if unused:
        print(f"\n[warn] {len(unused)} override key(s) matched no row — wrong file or stale keys: "
              f"{', '.join(unused[:10])}")


if __name__ == "__main__":
    main()
