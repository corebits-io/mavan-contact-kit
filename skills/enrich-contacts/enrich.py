#!/usr/bin/env python3
"""
Find + verify contact data for a leads CSV.

Two INDEPENDENT finders, then one verifier. That is the whole point: a single
finder gives you an address with no way to judge it. Two finders agreeing, plus
a deliverability check, gives you something you can actually send to.

  Prospeo        FINDER   email + mobile from a LinkedIn URL
  Better Contact FINDER   email + phone, independent waterfall (async batch)
  BounceBan      VERIFIER is a given address deliverable? (cannot find anything)

Usage:
  python3 enrich.py --in leads/list.csv --out research/list-enriched.csv --limit 5
  python3 enrich.py --in leads/list.csv --out research/list-enriched.csv

Input needs: linkedin_url, company, and either first_name/last_name or name.
Costs real credits per row. ALWAYS do a --limit 5 run first.
"""
import os, re, sys, time, csv, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


# ---------- Prospeo (FINDER) ----------
def prospeo_find(env, linkedin_url):
    st, resp = C.post_json(
        "https://api.prospeo.io/enrich-person",
        {"X-KEY": env["PROSPEO_API_KEY"]},
        {"enrich_mobile": True, "only_verified_email": True,
         "data": {"linkedin_url": linkedin_url}},
        timeout=60,
    )
    out = {"email": "", "email_status": "", "mobile": "", "mobile_status": "", "headline": ""}
    if st == 200 and isinstance(resp, dict) and not resp.get("error"):
        p = resp.get("person") or {}
        em, mo = p.get("email") or {}, p.get("mobile") or {}
        if isinstance(em, dict):
            out["email"] = em.get("email", "") or ""
            out["email_status"] = em.get("status", "") or ""
        if isinstance(mo, dict):
            out["mobile"] = mo.get("mobile", "") or ""
            out["mobile_status"] = mo.get("status", "") or ""
        out["headline"] = p.get("headline", "") or ""
    return out


# ---------- Better Contact (FINDER, async batch) ----------
def bettercontact_submit(env, rows):
    data = []
    for r in rows:
        f, l = C.split_name(r)
        data.append({"first_name": f, "last_name": l,
                     "company": r.get("company", ""),
                     "linkedin_url": r.get("linkedin_url", "")})
    # Header auth, not a query param: the key contains a URL-unsafe character.
    st, resp = C.post_json(
        "https://app.bettercontact.rocks/api/v2/async",
        {"X-API-Key": env["BETTERCONTACT_API_KEY"]},
        {"data": data, "enrich_email_address": True, "enrich_phone_number": True},
        timeout=60,
    )
    if st in (200, 201) and isinstance(resp, dict) and resp.get("success"):
        return resp.get("id")
    print(f"  [bettercontact] submit failed: HTTP {st} {str(resp)[:200]}")
    return None


def bettercontact_poll(env, req_id, max_wait=2400):
    url = f"https://app.bettercontact.rocks/api/v2/async/{req_id}"
    waited = 0
    while waited < max_wait:
        st, resp = C.get_json(url, {"X-API-Key": env["BETTERCONTACT_API_KEY"]}, timeout=60)
        status = resp.get("status") if isinstance(resp, dict) else None
        if status == "terminated":
            return resp
        time.sleep(15)
        waited += 15
        print(f"  [bettercontact] polling... {waited}s (status={status})")
    print("  [bettercontact] gave up waiting")
    return None


def bettercontact_list(resp):
    """Per-row results in SUBMISSION ORDER. Better Contact does not echo back
    the linkedin_url, so index is the only join key available."""
    out = []
    for item in (resp or {}).get("data", []):
        out.append({"email": item.get("contact_email_address") or "",
                    "email_status": item.get("contact_email_address_status") or "",
                    "phone": item.get("contact_phone_number") or "",
                    "phone_status": item.get("contact_phone_number_status") or ""})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="leads CSV")
    ap.add_argument("--out", dest="out", required=True, help="enriched CSV to write")
    ap.add_argument("--limit", type=int, default=0, help="only process N rows (use 5 for a test run)")
    ap.add_argument("--start", type=int, default=0, help="skip the first N rows (for chunking)")
    C.add_project_arg(ap)
    args = ap.parse_args()

    env = C.load_env(args, required=("PROSPEO_API_KEY", "BETTERCONTACT_API_KEY", "BOUNCER_API_KEY"))

    with open(args.inp) as f:
        rows = list(csv.DictReader(f))
    if args.start:
        rows = rows[args.start:]
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        raise SystemExit("no rows to process")

    missing_url = [C.display_name(r) for r in rows if not (r.get("linkedin_url") or "").strip()]
    if missing_url:
        print(f"[warn] {len(missing_url)} row(s) have no linkedin_url; Prospeo will return nothing for them")
    print(f"Processing {len(rows)} rows")

    # Better Contact is async, so submit the whole batch up front and let it work
    # while Prospeo runs row by row. Poll for it afterwards.
    bc_id = bettercontact_submit(env, rows)
    print(f"Better Contact request id: {bc_id}")

    results = []
    for i, r in enumerate(rows):
        pr = prospeo_find(env, r.get("linkedin_url", "")) if r.get("linkedin_url") else \
             {"email": "", "email_status": "", "mobile": "", "mobile_status": ""}
        results.append({**r,
                        "prospeo_email": pr["email"], "prospeo_email_status": pr["email_status"],
                        "prospeo_mobile": pr["mobile"], "prospeo_mobile_status": pr["mobile_status"]})
        print(f"  prospeo {i+1}/{len(rows)} {C.display_name(r)}: "
              f"email={pr['email'] or '-'} ({pr['email_status'] or '-'}) mobile={pr['mobile'] or '-'}")
        time.sleep(0.3)

    bc_list = bettercontact_list(bettercontact_poll(env, bc_id) if bc_id else None)
    if bc_list and len(bc_list) != len(results):
        print(f"  [warn] Better Contact returned {len(bc_list)} rows for {len(results)} submitted; "
              "order-mapping may be off — check a few by hand before trusting this chunk")
    for i, row in enumerate(results):
        hit = bc_list[i] if i < len(bc_list) else {}
        row["bettercontact_email"] = hit.get("email", "")
        row["bettercontact_email_status"] = hit.get("email_status", "")
        row["bettercontact_phone"] = hit.get("phone", "")
        row["bettercontact_phone_status"] = hit.get("phone_status", "")

    # Cross-check the finders, then verify EVERY distinct address either one
    # returned — not just the one we happen to prefer. Verifying only the
    # favourite is how you end up discarding the address that was actually good.
    for i, row in enumerate(results):
        pe = (row["prospeo_email"] or "").strip()
        be = (row["bettercontact_email"] or "").strip()
        if pe and be:
            row["email_agreement"] = "match" if pe.lower() == be.lower() else "differ"
        elif pe or be:
            row["email_agreement"] = "one_source"
        else:
            row["email_agreement"] = "none"

        bb_p = C.bounceban_verify(env, pe) if pe else {"result": "", "score": ""}
        if be and be.lower() == pe.lower():
            bb_b = bb_p                       # same address — don't burn a 2nd credit
        else:
            bb_b = C.bounceban_verify(env, be) if be else {"result": "", "score": ""}
        row["prospeo_bb_result"], row["prospeo_bb_score"] = bb_p["result"], bb_p["score"]
        row["bettercontact_bb_result"], row["bettercontact_bb_score"] = bb_b["result"], bb_b["score"]

        cands = [c for c in ((pe, bb_p, "prospeo"), (be, bb_b, "bettercontact")) if c[0]]
        cands.sort(key=lambda c: (C.RANK.get(str(c[1]["result"]).lower(), 0),
                                  int(c[1]["score"] or 0),
                                  1 if c[2] == "prospeo" else 0), reverse=True)
        best, bb, src = cands[0] if cands else ("", {"result": "", "score": ""}, "")
        row["best_email"], row["best_email_source"] = best, src
        row["bounceban_result"], row["bounceban_score"] = bb["result"], bb["score"]
        row["email_confidence"] = C.email_confidence(row["email_agreement"], bb["result"], best)

        # Phone: there is no phone verifier on the market we trust, so two
        # independent finders returning the same number is the ONLY real signal.
        pm, bp = row["prospeo_mobile"] or "", row["bettercontact_phone"] or ""
        dp, db = re.sub(r"\D", "", pm)[-10:], re.sub(r"\D", "", bp)[-10:]
        if dp and db:
            row["phone_agreement"] = "match" if dp == db else "differ"
        elif dp or db:
            row["phone_agreement"] = "one_source"
        else:
            row["phone_agreement"] = "none"
        row["best_mobile"] = pm or bp
        row["phone_confidence"] = {"match": "high", "differ": "low",
                                   "one_source": "medium", "none": "none"}[row["phone_agreement"]]

        print(f"  verify {i+1}/{len(results)} {C.display_name(row)}: best={best or '-'} "
              f"[{src or '-'}] bb={bb['result'] or '-'} agree={row['email_agreement']} "
              f"conf={row['email_confidence']} phone={row['phone_agreement']}")
        time.sleep(0.2)

    C.write_csv(args.out, results)
    got_email = sum(1 for r in results if r["best_email"])
    deliv = sum(1 for r in results if r["bounceban_result"] == "deliverable")
    risky = sum(1 for r in results if r["bounceban_result"] == "risky")
    print(f"\nDONE -> {args.out}")
    print(f"  emails found: {got_email}/{len(results)} | deliverable: {deliv} | "
          f"risky/catch-all: {risky} | mobiles: {sum(1 for r in results if r['best_mobile'])}")
    if risky:
        print("  note: 'risky' means a catch-all domain accepted the probe. It is not "
              "proof the mailbox exists.")


if __name__ == "__main__":
    main()
