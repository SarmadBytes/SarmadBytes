# -----------------------------------------------------------------------------
# update_readme.py — keeps the GitHub profile README ("GitHub resume") current
# Purpose : Rebuild the Projects table (repos with topic `portfolio`) and the
#           Latest field notes list (newest folders in the notes repo), then
#           stamp the date. Only text between the <!-- X:START/END --> markers changes.
# Usage   : python scripts/update_readme.py   (env: GH_USER, NOTES_REPO, GITHUB_TOKEN)
#           Runs daily from .github/workflows/update-readme.yml.
# Prereqs : Python 3.10+, standard library only. Public data only.
# -----------------------------------------------------------------------------
import json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone

USER = os.environ.get("GH_USER", "")
NOTES = os.environ.get("NOTES_REPO", "")          # e.g. "<user>/openshift-field-notes"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = "README.md"


def gh(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "profile-readme"})
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def projects():
    repos = gh(f"https://api.github.com/users/{USER}/repos?per_page=100&sort=pushed")
    rows = [r for r in repos if "portfolio" in (r.get("topics") or []) and not r["fork"] and not r["archived"]]
    if not rows:
        return "_First projects are being published._"
    # group: "for OpenShift" ports (topic openshift-port) · labs (topic lab) · tools/notes (rest)
    groups = {"Tools & field notes": [], "Open-source tools ported to OpenShift": [], "Labs": []}
    for r in rows:
        t = r.get("topics") or []
        key = "Open-source tools ported to OpenShift" if "openshift-port" in t else "Labs" if "lab" in t else "Tools & field notes"
        groups[key].append(r)
    out = []
    for title, items in groups.items():
        if not items:
            continue
        out += [f"**{title}**", "", "| Project | What it does | Stack | ★ | Updated |", "|---|---|---|---|---|"]
        for r in items:
            stack = ", ".join(t for t in r.get("topics", []) if t not in ("portfolio", "openshift-port", "lab"))[:60]
            out.append(f"| [{r['name']}]({r['html_url']}) | {r.get('description') or ''} | {stack} | {r['stargazers_count']} | {r['pushed_at'][:10]} |")
        out.append("")
    return "\n".join(out).rstrip()


def contrib(limit=8):
    """Merged pull requests in repositories owned by someone else."""
    q = f"is:pr author:{USER} is:merged -user:{USER}"
    res = gh("https://api.github.com/search/issues?per_page=30&sort=updated&q=" + urllib.parse.quote(q))
    out = []
    for it in res.get("items", [])[:limit]:
        repo = it["repository_url"].split("/repos/")[1]
        out.append(f"- [{repo}](https://github.com/{repo}) — [{it['title']}]({it['html_url']}) · merged {(it.get('pull_request') or {}).get('merged_at', it['closed_at'])[:10]}")
    return "\n".join(out) or "_First upstream pull requests coming this month — OpenShift docs, llm-d, KubeArmor._"


def notes(limit=7):
    if not NOTES:
        return "_Field notes start soon._"
    commits = gh(f"https://api.github.com/repos/{NOTES}/commits?per_page=30")
    seen, out = set(), []
    for c in commits:
        msg = c["commit"]["message"].splitlines()[0]
        if msg.lower().startswith(("note:", "how-to:", "fix:")) and msg not in seen:
            seen.add(msg)
            out.append(f"- {c['commit']['author']['date'][:10]} · [{msg.split(':', 1)[1].strip()}]({c['html_url']})")
        if len(out) >= limit:
            break
    if out:
        return "\n".join(out)
    # fallback: newest note folders under issues/ (e.g. "007-graceful-node-reboot")
    try:
        items = gh(f"https://api.github.com/repos/{NOTES}/contents/issues")
    except Exception:
        return "_Field notes start soon._"
    dirs = sorted((i for i in items if i["type"] == "dir"), key=lambda i: i["name"], reverse=True)[:limit]
    for d in dirs:
        num, _, slug = d["name"].partition("-")
        out.append(f"- #{num} · [{slug.replace('-', ' ').capitalize()}]({d['html_url']})")
    return "\n".join(out) or "_Field notes start soon._"


def replace(text, key, body):
    pat = re.compile(rf"(<!-- {key}:START -->)(.*?)(<!-- {key}:END -->)", re.S)
    sep = "" if key == "DATE" else "\n"
    return pat.sub(lambda m: m.group(1) + sep + body + sep + m.group(3), text)


if __name__ == "__main__":
    old = open(README, encoding="utf-8").read()
    text = replace(old, "PROJECTS", projects())
    text = replace(text, "NOTES", notes())
    text = replace(text, "CONTRIB", contrib())
    # stamp the date ONLY when real content changed (no daily filler commits)
    if text != old:
        text = replace(text, "DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        open(README, "w", encoding="utf-8").write(text)
        print("README updated")
    else:
        print("no change")
