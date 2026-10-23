#!/usr/bin/env python3
"""
Grade every row in a list for fit with ONE campaign, against a rubric file.

The rubric lives in JSON, not in this code, because a fit rubric is a business
judgement that changes per campaign and has to stay reviewable. See
rubrics/TEMPLATE.json for the shape and rubrics/EXAMPLE-*.json for a real one.

Order of decisions (first match wins — deliberately):
  1. account disqualifiers   -> E   wrong company, nothing else matters
  2. role_type rules         -> D   right company, structurally wrong person
  3. wrong_person_titles     -> D   right company, wrong function
  4. owner_titles            -> A   owns this problem by job description
  5. decision_titles         -> B   can decide, no dedicated owner
  6. junior_titles           -> C   in the right function, not the entry point
  7. default                 -> C

Adds: fit_grade, fit_reason, employer_check
NEVER drops a row. Grading is advisory and must stay reviewable by a human.

Usage:
  python3 grade_fit.py --file research/list-enriched.csv --rubric rubrics/my-campaign.json
  python3 grade_fit.py --file ... --rubric ... --profiles scratch/profiles_joined.json
  python3 grade_fit.py --file ... --rubric ... --explain     # print the rubric and stop
"""
import os, re, sys, csv, json, argparse, collections

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "enrich-contacts"))
import _common as C

# words that carry no identity in a company name, so "Acme Capital Partners LLC"
# and "Acme" compare equal when checking a scraped current employer
NOISE = ("llc", "lp", "l p", "inc", "ltd", "limited", "company", "co", "corp",
         "capital", "partners", "group", "holdings", "investments", "investment",
         "ventures", "equity", "the", "management", "advisors", "associates")


def norm_co(s):
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    for w in NOISE:
        s = re.sub(rf"\b{w}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def any_in(haystack, needles):
    """Return the matching needle, so the reason can name what actually matched."""
    for n in needles or []:
        if n and n.lower() in haystack:
            return n
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="the list CSV to grade (updated in place unless --out)")
    ap.add_argument("--rubric", required=True, help="rubric JSON — see rubrics/TEMPLATE.json")
    ap.add_argument("--profiles", default="", help="profiles_joined.json from join_apify.py (enables employer_check)")
    ap.add_argument("--out", default="", help="write here instead of in place")
    ap.add_argument("--explain", action="store_true", help="print the rubric in plain English and exit")
    ap.add_argument("--sort", action="store_true", help="sort best-fit + most-contactable first")
    C.add_project_arg(ap)
    args = ap.parse_args()

    R = json.load(open(args.rubric))
    col = R.get("columns", {})
    def cv(row, logical, default=""):
        """Read a logical field through the rubric's column mapping."""
        return (row.get(col.get(logical, logical), default) or "")

    if args.explain:
        print(f"rubric : {R.get('name','(unnamed)')}")
        print(f"campaign: {R.get('campaign','(not stated)')}\n")
        for g, desc in (R.get("grades") or {}).items():
            print(f"  {g}  {desc}")
        print("\ndisqualifying company signals:")
        for d in R.get("account_disqualifiers") or []:
            print(f"  - '{d['match']}' -> E ({d['reason']})")
        print(f"\nowner titles (A)    : {', '.join(R.get('owner_titles') or []) or '-'}")
        print(f"decision titles (B) : {', '.join(R.get('decision_titles') or []) or '-'}")
        print(f"junior titles (C)   : {', '.join(R.get('junior_titles') or []) or '-'}")
        print(f"wrong-person (D)    : {', '.join(R.get('wrong_person_titles') or []) or '-'}")
        return

    profiles = json.load(open(args.profiles)) if args.profiles else {}

    with open(args.file) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("no rows")

    for idx, r in enumerate(rows):
        title = cv(r, "title").lower()
        desc = cv(r, "account_description").lower()

        # --- employer_check: does the scraped profile agree about where they work?
        # Advisory only. It cannot tell a rebrand from a departure, so it flags,
        # never downgrades.
        emp_check = ""
        prof = profiles.get(C.row_key(r, idx), {}) if profiles else {}
        exp = prof.get("experience") or []
        cur = (exp[0].get("company") if exp else "") or ""
        if cur:
            a, b = norm_co(cur), norm_co(cv(r, "company"))
            if a and b and a != b and a not in b and b not in a:
                emp_check = f"LinkedIn shows current employer '{cur}'"
        r["employer_check"] = emp_check

        grade = reason = ""

        # 1. wrong company beats everything
        for d in R.get("account_disqualifiers") or []:
            if d["match"].lower() in desc:
                grade, reason = d.get("grade", "E"), d["reason"]
                break
        if not grade and R.get("require_account_description") and not desc.strip():
            grade, reason = "E", "no company-level evidence on this row — unqualified, not disqualified"

        # 2. structural role rules (from a role_type column, if the list has one)
        if not grade:
            rt = cv(r, "role_type").strip().lower()
            rule = (R.get("role_type_rules") or {}).get(rt)
            if rule:
                grade, reason = rule["grade"], rule["reason"]

        # 3. wrong function at the right company
        if not grade:
            m = any_in(title, R.get("wrong_person_titles"))
            if m:
                grade, reason = "D", f"'{m}' — not the function that owns this problem"

        # 4. owns the problem by job description
        if not grade:
            m = any_in(title, R.get("owner_titles"))
            if m:
                grade, reason = "A", f"dedicated '{m}' role — owns this problem directly"

        # 5. can decide, with no dedicated owner in the seat
        if not grade:
            m = any_in(title, R.get("decision_titles"))
            excl = any_in(title, R.get("decision_title_exclusions"))
            if m and not excl:
                grade, reason = "B", f"'{m}' — decision-maker at a qualifying company"
                small = R.get("small_account") or {}
                size = cv(r, "account_size").strip()
                if small.get("threshold") and size.isdigit() and int(size) <= small["threshold"]:
                    reason += f" ({size}-person company: {small.get('note','likely no dedicated owner')})"

        # 6. right function, wrong seniority
        if not grade:
            m = any_in(title, R.get("junior_titles"))
            if m:
                grade, reason = "C", f"'{m}' — in the right function but likely not the entry point"

        # 7. fallback
        if not grade:
            dflt = R.get("default") or {}
            grade = dflt.get("grade", "C")
            reason = dflt.get("reason", "entry point unclear from the title alone")

        if emp_check and grade in ("A", "B", "C"):
            reason += f"; verify employer — {emp_check}"

        r["fit_grade"], r["fit_reason"] = grade, reason

    if args.sort:
        grank = {g: i for i, g in enumerate("ABCDE")}
        erank = {"high": 0, "medium": 1, "low": 2, "unusable": 3, "none": 4, "": 5}
        rows.sort(key=lambda x: (grank.get(x["fit_grade"], 9),
                                 erank.get(x.get("email_confidence", ""), 9),
                                 (x.get("company") or "").lower()))

    out = args.out or args.file
    C.write_csv(out, rows)
    mix = collections.Counter(r["fit_grade"] for r in rows)
    print(f"graded {len(rows)} rows -> {out}")
    print("fit mix:", dict(sorted(mix.items())))
    print("employer mismatches to eyeball:", sum(1 for r in rows if r["employer_check"]))
    reach = sum(1 for r in rows if r["fit_grade"] in ("A", "B")
                and r.get("email_confidence") in ("high", "medium"))
    print(f"A/B fit AND a verified email: {reach}")
    print("\nNothing was dropped. Read the D/E rows before you cut them — the rubric is blunt "
          "and a wrong grade is a lost prospect.")


if __name__ == "__main__":
    main()
