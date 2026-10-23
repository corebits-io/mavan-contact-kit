#!/usr/bin/env python3
"""
Join the batched Apify trim files back onto the input rows.

WHY POSITIONAL, NOT BY URL: the actor returns the profile's *canonical* vanity
URL, not the URL you queried (brian-edgerley-96895346 -> brianedgerley). Joining
on URL silently loses those rows. Batches go out in input order and come back in
the same order, so item i of the batch starting at N is input row N+i.

Positional joins are dangerous if you don't check them, so every match is then
re-verified against the expected name and anything suspicious is REPORTED rather
than quietly trusted.

Usage:
  python3 join_apify.py --in leads/list.csv --scratch scratch/
Writes into the scratch dir:
  profiles_joined.json  {row_key: {profile...}}
  profiles_bad.json     rows that failed the name check — read this
"""
import os, re, sys, csv, json, glob, argparse, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


def deacc(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def slug(u):
    if isinstance(u, dict):
        u = u.get("url", "")
    m = re.search(r"/in/([^/?]+)", u or "")
    return m.group(1).lower() if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="the SAME leads CSV apify_profiles.py read")
    ap.add_argument("--scratch", default="", help="dir holding apify_profiles_trim_b*.json")
    C.add_project_arg(ap)
    args = ap.parse_args()

    scratch = args.scratch or C.scratch_dir(args)
    with open(args.inp) as f:
        rows = list(csv.DictReader(f))

    files = glob.glob(os.path.join(scratch, "apify_profiles_trim_b*.json"))
    if not files:
        raise SystemExit(f"no apify_profiles_trim_b*.json in {scratch}")
    files.sort(key=lambda p: int(re.search(r"_b(\d+)\.json$", p).group(1)))

    joined, bad, empty = {}, [], 0
    for fp in files:
        start = int(re.search(r"_b(\d+)\.json$", fp).group(1))
        items = json.load(open(fp))
        for i, it in enumerate(items):
            idx = start + i
            if idx >= len(rows):
                bad.append({"reason": "index past end of input — wrong --in file or wrong tag",
                            "batch": start, "i": i})
                continue
            row = rows[idx]
            key = C.row_key(row, idx)
            got_name = deacc(it.get("name") or "")
            exp_first, exp_last = (deacc(x) for x in C.split_name(row))
            in_slug, out_slug = slug(row.get("linkedin_url")), slug(it.get("linkedin_url"))
            has_data = bool(it.get("headline") or it.get("experience"))
            if not has_data:
                empty += 1

            ok = False
            if exp_last and exp_last in got_name:
                ok = True
            elif exp_first and exp_first in got_name:
                ok = True
            elif in_slug and out_slug and (in_slug == out_slug
                                           or in_slug.startswith(out_slug)
                                           or out_slug.startswith(in_slug.split("-")[0])):
                ok = True
            elif not has_data:
                ok = True      # the scrape failed; positional mapping is still correct

            rec = dict(it)
            rec.update({"row_key": key, "row_index": idx,
                        "input_linkedin_url": row.get("linkedin_url", ""),
                        "input_name": C.display_name(row),
                        "input_company": row.get("company", ""),
                        "input_title": row.get("title", ""),
                        "scrape_ok": has_data,
                        "name_check": "ok" if ok else "MISMATCH"})
            joined[key] = rec
            if not ok:
                bad.append({"row_key": key, "row_index": idx, "expected": rec["input_name"],
                            "got": it.get("name"), "batch": start, "i": i,
                            "in_slug": in_slug, "out_slug": out_slug})

    json.dump(joined, open(os.path.join(scratch, "profiles_joined.json"), "w"), indent=1)
    json.dump(bad, open(os.path.join(scratch, "profiles_bad.json"), "w"), indent=1)
    print(f"batches: {len(files)} | joined: {len(joined)}/{len(rows)} | "
          f"empty scrapes: {empty} | name mismatches: {len(bad)}")
    for b in bad[:15]:
        print("  MISMATCH", b)
    if bad:
        print(f"\nRead {scratch}/profiles_bad.json before using these. A mismatch means the "
              "positional mapping slipped — usually a batch was re-run with a different --tag.")
    if empty:
        print(f"{empty} profile(s) came back empty. Those get no summary — say so, don't guess.")


if __name__ == "__main__":
    main()
