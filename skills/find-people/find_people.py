#!/usr/bin/env python3
"""Find the right people at a company from the terminal, then find and verify their email.

  find_people.py --domain acme.com                                   # list everyone Prospeo knows at the domain
  find_people.py --domain acme.com --titles founder,ceo,"chief executive" --enrich 2 --fallback --out research/acme.com.csv
  find_people.py --domain acme.com --pages 3 --out people.csv

Search Person = 1 Prospeo credit per page (25 people). Enrich = 1 credit per verified email found.
Better Contact fallback = about 7 credits. BounceBan verify = 1 credit per email.
Keys come from the kit's .env file and are never printed.
"""
import argparse, csv, json, os, re, subprocess, sys, time

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def find_env():
    """Locate .env: $PDK_PROJECT first, then the nearest .env walking up from the
    working directory, then the kit root (two folders above this script)."""
    if os.environ.get("PDK_PROJECT"):
        return os.path.join(os.path.abspath(os.environ["PDK_PROJECT"]), ".env")
    d = os.path.abspath(os.getcwd())
    while True:
        cand = os.path.join(d, ".env")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    kit = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(kit, ".env")

ENV = find_env()

def key(name):
    if not os.path.exists(ENV):
        sys.exit(f"no .env found at {ENV}. Copy .env.example to .env and fill in your keys.")
    for line in open(ENV):
        if line.startswith(name + "="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return v
    sys.exit(f"{name} is missing or empty in {ENV}")

def post(url, headers, body):
    cmd = ["curl", "-s", "-A", UA, "-X", "POST", url, "-H", "Content-Type: application/json"]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += ["-d", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return {"error": True, "raw": out[:300]}

def get(url, headers):
    cmd = ["curl", "-s", "-A", UA, url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return {"error": True, "raw": out[:300]}

def search(domain, pages, pkey):
    people = []
    for page in range(1, pages + 1):
        r = post("https://api.prospeo.io/search-person", {"X-KEY": pkey},
                 {"filters": {"company": {"websites": {"include": [domain]}}}, "page": page})
        if r.get("error"):
            print("search error:", json.dumps(r)[:400], file=sys.stderr)
            break
        for row in r.get("results", []):
            p, c = row.get("person", {}), row.get("company", {})
            people.append({
                "person_id": p.get("person_id") or p.get("id", ""),
                "full_name": p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
                "first_name": p.get("first_name", ""), "last_name": p.get("last_name", ""),
                "title": p.get("current_job_title") or p.get("title") or p.get("headline", ""),
                "seniority": p.get("seniority", ""), "department": p.get("department", ""),
                "location": (p.get("location") or {}).get("name", "") if isinstance(p.get("location"), dict) else p.get("location", ""),
                "linkedin_url": p.get("linkedin_url", ""), "company": c.get("name", ""), "domain": domain,
                "email": "", "email_status": "", "bounceban": "", "mobile": "",
            })
        pg = r.get("pagination", {})
        print(f"page {pg.get('current_page')}/{pg.get('total_page')} · {pg.get('total_count')} people at {domain}" + (" (free, cached)" if r.get("free") else ""), file=sys.stderr)
        if page >= (pg.get("total_page") or 1):
            break
    return people

def bettercontact(p, bckey):
    """Fallback finder when Prospeo has no match. About 7 credits per row."""
    name = p["full_name"].replace("-", " ")
    parts = name.split()
    body = {"data": [{"first_name": p["first_name"] or parts[0], "last_name": p["last_name"] or " ".join(parts[1:]),
                      "company": p["company"] or p["domain"], "company_domain": p["domain"], "linkedin_url": p["linkedin_url"]}],
            "enrich_email_address": True, "enrich_phone_number": False}
    r = post("https://app.bettercontact.rocks/api/v2/async", {"X-API-Key": bckey}, body)
    rid = r.get("id")
    if not rid:
        p["email_status"] = "bettercontact error " + json.dumps(r)[:100]; return p
    for _ in range(30):
        time.sleep(4)
        g = get(f"https://app.bettercontact.rocks/api/v2/async/{rid}", {"X-API-Key": bckey})
        if g.get("status") == "terminated":
            d = (g.get("data") or [{}])[0]
            p["email"] = d.get("contact_email_address") or ""
            p["email_status"] = "bettercontact " + str(d.get("contact_email_address_status") or "none")
            return p
    p["email_status"] = "bettercontact timeout"; return p

def enrich(p, pkey, bkey, mobile=False, bckey=""):
    attempts = []
    if p["linkedin_url"]:
        attempts.append({"linkedin_url": p["linkedin_url"]})
    if p["full_name"] and p["domain"]:
        attempts.append({"full_name": p["full_name"], "company_website": p["domain"]})
    res, r = {}, {}
    for data in attempts:
        r = post("https://api.prospeo.io/enrich-person", {"X-KEY": pkey},
                 {"only_verified_email": True, "enrich_mobile": mobile, "data": data})
        res = r.get("person") or {}
        if res and not r.get("error"):
            break
    if not res:
        p["email_status"] = "prospeo " + str(r.get("error_code") or json.dumps(r)[:80])
        if bckey:
            bettercontact(p, bckey)
    else:
        p["full_name"] = res.get("full_name") or p["full_name"]
        p["title"] = p["title"] or res.get("current_job_title") or ""
        loc = res.get("location") or {}
        p["location"] = p["location"] or ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
        em = res.get("email") or {}
        p["email"] = em.get("email") or "" if em.get("revealed") else ""
        p["email_status"] = "prospeo " + str(em.get("status") or "none")
        mb = res.get("mobile") or {}
        if mb.get("revealed"):
            p["mobile"] = mb.get("mobile") or ""
    if p["email"] and bkey:
        v = get(f"https://api.bounceban.com/v1/verify/single?email={p['email']}", {"Authorization": bkey})
        p["bounceban"] = v.get("result") or json.dumps(v)[:80]
    return p

def main():
    a = argparse.ArgumentParser()
    a.add_argument("--domain", required=True, help="company website, e.g. salescaptain.io")
    a.add_argument("--pages", type=int, default=2)
    a.add_argument("--titles", default="", help="comma list of keywords to keep, e.g. founder,ceo,head,talent,people,operations")
    a.add_argument("--enrich", type=int, default=0, help="enrich the first N matching people (1 credit per verified email)")
    a.add_argument("--mobile", action="store_true", help="also reveal mobiles (10 credits each)")
    a.add_argument("--linkedin", default="", help="comma list of LinkedIn URLs to enrich directly (skips the search)")
    a.add_argument("--fallback", action="store_true", help="try Better Contact when Prospeo has no match (about 7 credits)")
    a.add_argument("--out", default="")
    a.add_argument("--name", default="", help="comma list of real names matching --linkedin, e.g. \"Dani Pascarella\". Without this BetterContact only gets the URL slug and misses.")
    a.add_argument("--company", default="", help="company name for the BetterContact payload, e.g. \"OneEleven Financial Wellness\"")
    a.add_argument("--raw", action="store_true", help="dump the first raw search result for debugging")
    args = a.parse_args()
    pkey, bkey, bckey = key("PROSPEO_API_KEY"), key("BOUNCER_API_KEY"), key("BETTERCONTACT_API_KEY")
    if args.raw:
        r = post("https://api.prospeo.io/search-person", {"X-KEY": pkey}, {"filters": {"company": {"websites": {"include": [args.domain]}}}, "page": 1})
        print(json.dumps(r, indent=1)[:4000]); return
    if args.linkedin:
        urls = [u.strip() for u in args.linkedin.split(",") if u.strip()]
        names = [n.strip() for n in args.name.split(",")] if args.name else []
        people = []
        for i, u in enumerate(urls):
            full = names[i] if i < len(names) and names[i] else u.rstrip("/").split("/")[-1].replace("-", " ").replace(".", " ")
            parts = [x for x in full.split() if not x.isdigit() and len(x) > 1]
            people.append({"person_id": "", "full_name": " ".join(parts) or full, "first_name": parts[0] if parts else "",
                           "last_name": " ".join(parts[1:]) if len(parts) > 1 else "", "title": "", "seniority": "",
                           "department": "", "location": "", "linkedin_url": u, "company": args.company,
                           "domain": args.domain, "email": "", "email_status": "", "bounceban": "", "mobile": ""})
        args.enrich = args.enrich or len(people)
    else:
        people = search(args.domain, args.pages, pkey)
    kws = [k.strip().lower() for k in args.titles.split(",") if k.strip()]
    if kws:
        people = [p for p in people if any(k in (p["title"] + " " + p["seniority"] + " " + p["department"]).lower() for k in kws)]
    if args.enrich:
        for p in people[: args.enrich]:
            enrich(p, pkey, bkey, args.mobile, bckey if args.fallback else "")
            time.sleep(0.5)
    for p in people:
        print(f"{p['full_name']:<28} | {p['title'][:45]:<45} | {p['location'][:18]:<18} | {p['email'] or '':<32} {p['email_status']} {p['bounceban']} | {p['linkedin_url']}")
    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(people[0].keys()) if people else ["full_name"])
            w.writeheader(); w.writerows(people)
        print(f"saved {len(people)} rows to {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
