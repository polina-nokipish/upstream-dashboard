#!/usr/bin/env python3
"""Fetches Jira data and writes data.json for the Upstream dashboard."""
import os, json, base64
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from datetime import datetime, timezone

JIRA_BASE = "https://tatari.atlassian.net"
EMAIL = os.environ["JIRA_EMAIL"]
TOKEN = os.environ["JIRA_TOKEN"]
AUTH  = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
FIELDS = "summary,status,issuetype,assignee,parent,fixVersions,updated"

QUERIES = {
    "v62":            'project=TVP AND fixVersion="Version 62" ORDER BY status ASC',
    "sprint62_extra": 'project=TVP AND sprint="Sprint 62" AND (fixVersion!="Version 62" OR fixVersion is EMPTY) ORDER BY status ASC',
    "v63":            'project=TVP AND fixVersion="Version 63" ORDER BY status ASC',
}

def jira_get(path):
    req = Request(f"{JIRA_BASE}{path}", headers={"Authorization": f"Basic {AUTH}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Jira {e.code} {path}: {body[:200]}")

def jira_search(jql, max_results=100):
    params = urlencode({"jql": jql, "maxResults": max_results, "fields": FIELDS})
    return jira_get(f"/rest/api/3/search/jql?{params}")["issues"]

def slim(issues):
    out = []
    for i in issues:
        f = i["fields"]
        p = f.get("parent")
        out.append({
            "key":         i["key"],
            "url":         f"{JIRA_BASE}/browse/{i['key']}",
            "summary":     f["summary"][:80],
            "status":      f["status"]["name"],
            "type":        f["issuetype"]["name"],
            "assignee":    f["assignee"]["displayName"] if f.get("assignee") else None,
            "epic":        {"key": p["key"], "summary": p["fields"]["summary"][:70]} if p else None,
            "fixVersions": [v["name"] for v in f.get("fixVersions", [])],
            "updated":     f.get("updated", "")[:10] if f.get("updated") else None,
        })
    return out

def fmt_date(d):
    """Convert YYYY-MM-DD to readable string."""
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%b %d, %Y")
    except Exception:
        return d

def fetch_version_dates(project_key, version_name):
    """Get start and release date for a Jira version."""
    try:
        data = jira_get(f"/rest/api/3/project/{project_key}/versions")
        for v in data:
            if v.get("name") == version_name:
                return {
                    "startDate":   fmt_date(v.get("startDate")),
                    "releaseDate": fmt_date(v.get("releaseDate")),
                    "released":    v.get("released", False),
                }
    except Exception as e:
        print(f"  Warning: could not fetch version dates: {e}")
    return {"startDate": None, "releaseDate": None, "released": False}

def fetch_sprint_dates(project_key, sprint_name):
    """Get start and end date for a sprint via Jira Agile API."""
    try:
        # Get all boards for the project
        boards = jira_get(f"/rest/agile/1.0/board?projectKeyOrId={project_key}")
        for board in boards.get("values", []):
            bid = board["id"]
            # Get sprints for this board
            sprints = jira_get(f"/rest/agile/1.0/board/{bid}/sprint?state=active,closed,future")
            for s in sprints.get("values", []):
                if s.get("name") == sprint_name:
                    def parse_dt(dt_str):
                        if not dt_str:
                            return None
                        try:
                            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            return dt.strftime("%b %d, %Y")
                        except Exception:
                            return dt_str
                    return {
                        "startDate": parse_dt(s.get("startDate")),
                        "endDate":   parse_dt(s.get("endDate")),
                        "state":     s.get("state"),
                    }
    except Exception as e:
        print(f"  Warning: could not fetch sprint dates: {e}")
    return {"startDate": None, "endDate": None, "state": None}

# ── Fetch issues ──────────────────────────────────────────────────────────────
result = {}
for key, jql in QUERIES.items():
    print(f"Fetching {key}…", end=" ", flush=True)
    issues = jira_search(jql)
    result[key] = slim(issues)
    print(f"{len(issues)} issues")

# ── Fetch dates ───────────────────────────────────────────────────────────────
print("Fetching Version 62 dates…", end=" ", flush=True)
v62_dates = fetch_version_dates("TVP", "Version 62")
print(v62_dates)

print("Fetching Sprint 62 dates…", end=" ", flush=True)
sprint_dates = fetch_sprint_dates("TVP", "Sprint 62")
print(sprint_dates)

result["meta"] = {
    "version":     "Version 62",
    "sprint":      "Sprint 62",
    "vStartDate":  v62_dates["startDate"],
    "vReleaseDate":v62_dates["releaseDate"],
    "vReleased":   v62_dates["released"],
    "sStartDate":  sprint_dates["startDate"],
    "sEndDate":    sprint_dates["endDate"],
    "sState":      sprint_dates["state"],
}

result["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

print(f"data.json written — v62={len(result['v62'])}, extra={len(result['sprint62_extra'])}, v63={len(result['v63'])}")
print(f"Version dates: {v62_dates['startDate']} → {v62_dates['releaseDate']}")
print(f"Sprint dates:  {sprint_dates['startDate']} → {sprint_dates['endDate']}")
