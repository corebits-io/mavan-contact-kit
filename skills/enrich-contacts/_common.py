#!/usr/bin/env python3
"""
Shared plumbing for the enrich-contacts scripts.

The important thing this fixes: nothing here resolves paths relative to the
script's own location. These skills can live in three different places — a
plugin dir, a copied `.claude/skills/`, or a checkout of this repo — and only
the *working directory* is a reliable anchor for "where the data is".

Project root, in order of precedence:
  1. --project on the command line
  2. $PDK_PROJECT
  3. the nearest ancestor of the cwd containing a .env, else the cwd itself
"""
import os, re, json, argparse, subprocess, urllib.parse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# BounceBan's verdicts, ranked. `risky` = catch-all domain: the mail server
# accepts anything, so a "pass" proves nothing about this specific mailbox.
RANK = {"deliverable": 3, "risky": 2, "unknown": 1, "": 0, "undeliverable": -1}


def add_project_arg(ap):
    ap.add_argument("--project", default="",
                    help="project root holding .env (default: $PDK_PROJECT, else nearest .env above cwd, else cwd)")


def project_root(args=None):
    explicit = getattr(args, "project", "") if args else ""
    if explicit:
        return os.path.abspath(explicit)
    if os.environ.get("PDK_PROJECT"):
        return os.path.abspath(os.environ["PDK_PROJECT"])
    d = os.path.abspath(os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, ".env")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(os.getcwd())
        d = parent


def load_env(args=None, required=()):
    """Parse .env into a dict. Never prints a value — only ever a key name."""
    path = os.path.join(project_root(args), ".env")
    if not os.path.exists(path):
        raise SystemExit(
            f"no .env found at {path}\n"
            "Copy .env.example to .env and fill in your own API keys, or pass --project."
        )
    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in required if not d.get(k)]
    if missing:
        raise SystemExit(f"missing required key(s) in {path}: {', '.join(missing)}")
    return d


def scratch_dir(args=None, sub="scratch"):
    d = os.environ.get("PDK_SCRATCH") or os.path.join(project_root(args), sub)
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- http
# Everything shells out to curl on purpose: python's urllib fails DNS on
# api.bounceban.com in some sandboxes, and Better Contact's firewall 403s the
# default python User-Agent. curl with a browser UA works against all four APIs.
def curl(args, timeout=90):
    """Return (http_code, parsed_json | {"raw": ...}). Key values are inside
    `args` and are never logged by us."""
    base = ["curl", "-sS", "--max-time", str(timeout),
            "-H", f"User-Agent: {UA}", "-w", "\n%{http_code}"]
    try:
        p = subprocess.run(base + args, capture_output=True, text=True, timeout=timeout + 15)
    except subprocess.TimeoutExpired:
        return 0, {"error": "curl timeout"}
    out = p.stdout
    nl = out.rfind("\n")
    body, code = (out[:nl], out[nl + 1:].strip()) if nl != -1 else (out, "")
    try:
        code = int(code)
    except Exception:
        code = 0
    try:
        return code, json.loads(body) if body.strip() else {}
    except Exception:
        return code, {"raw": body[:300]}


def post_json(url, headers, body, timeout=90):
    args = ["-X", "POST", url, "-H", "Content-Type: application/json", "-d", json.dumps(body)]
    for k, v in headers.items():
        args += ["-H", f"{k}: {v}"]
    return curl(args, timeout)


def get_json(url, headers=None, timeout=90):
    args = [url]
    for k, v in (headers or {}).items():
        args += ["-H", f"{k}: {v}"]
    return curl(args, timeout)


# ---------------------------------------------------------------- bounceban
def bounceban_verify(env, email, timeout=30):
    """VERIFIER only — BounceBan cannot find an address, only judge one.
    1 credit per call. Returns {"result", "score"}; result "err:<code>" on
    a transport failure so a retry can tell that apart from a bad address."""
    if not email or "@" not in email:
        return {"result": "", "score": ""}
    q = urllib.parse.urlencode({"email": email})
    st, resp = get_json(f"https://api.bounceban.com/v1/verify/single?{q}",
                        {"Authorization": env["BOUNCER_API_KEY"]}, timeout)
    if st == 200 and isinstance(resp, dict) and resp.get("result"):
        return {"result": resp.get("result", ""), "score": resp.get("score", "")}
    return {"result": f"err:{st}", "score": ""}


# ---------------------------------------------------------------- csv helpers
def domain_of(email):
    return email.split("@")[-1].strip().lower() if email and "@" in email else ""


def same_domain(email, target_domain):
    """Loose match, so mail.acme.com / acme.co / acmecapital.com all count as
    'the company's own domain' against acme.com."""
    d = domain_of(email)
    td = (target_domain or "").strip().lower().replace("www.", "")
    if not d or not td:
        return False
    a, b = d.split(".")[0], td.split(".")[0]
    return d == td or a == b or a in b or b in a


def split_name(row):
    """Accept either first_name/last_name or a single name/full_name column."""
    f = (row.get("first_name") or "").strip()
    l = (row.get("last_name") or "").strip()
    if f or l:
        return f, l
    whole = (row.get("full_name") or row.get("name") or "").strip()
    parts = whole.split()
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return whole, ""


def display_name(row):
    f, l = split_name(row)
    return (f"{f} {l}").strip() or (row.get("name") or "").strip() or "?"


def row_key(row, idx):
    """Stable per-row id. Uses contact_id when the list has one, else the row
    index, so scripts work on a plain 4-column CSV with no id column."""
    return (row.get("contact_id") or "").strip() or f"row{idx}"


def pick_domain_column(rows):
    """Find whichever column holds the company's web domain, if any."""
    if not rows:
        return ""
    for c in ("firm_domain", "company_domain", "domain", "website_domain"):
        if c in rows[0]:
            return c
    return ""


def write_csv(path, rows):
    """Write via a temp file and swap, so a crash mid-write can never truncate
    a file that cost real API credits to produce."""
    if not rows:
        print(f"nothing to write to {path}")
        return
    cols = list(dict.fromkeys(k for r in rows for k in r.keys()))
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(tmp, "w", newline="") as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def email_confidence(agreement, bb_result, best_email):
    """One field an operator can filter on, so nobody has to remember how the
    two finders and the verifier interact."""
    res = str(bb_result or "").lower()
    if not best_email:
        return "none"
    if agreement == "match" and res == "deliverable":
        return "high"        # two independent finders agree AND it verifies
    if res == "deliverable":
        return "medium"      # verifies, but only one source found it
    if res == "risky":
        return "low"         # catch-all domain, unprovable
    return "unusable"        # undeliverable, or the verifier errored
