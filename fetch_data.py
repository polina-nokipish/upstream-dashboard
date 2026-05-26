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
FIELDS = "summary,status,issuetype,assignee,parent,fixVersions"

QUERIES = {
    "v62":           'project=TVP AND fixVersion="Version 62" ORDER BY status ASC',
    "sprint62_extra": 'project=TVP AND sprint="Sprint 62" AND (fixVersion!="Version 62" OR fixVersion is EMPTY) ORDER BY status ASC',
    "v63":           'project=TVP AND fixVersion="Version 63" ORDER BY status ASC',
}

def jira_search(jql, max_results=100):
    params = urlencode({"jql": jql, "maxResults": max_results, "fields": FIELDS})
    url = f"{JIRA_BASE}/rest/api/3/search/jql?{params}"
    req = Request(url, headers={"Authorization": f"Basic {AUTH}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["issues"]
    except HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Jira {e.code}: {body[:200]}")

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
        })
    return out

result = {}
for key, jql in QUERIES.items():
    print(f"Fetching {key}…", end=" ", flush=True)
    issues = jira_search(jql)
    result[key] = slim(issues)
    print(f"{len(issues)} issues")

result["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

print(f"data.json written — v62={len(result['v62'])}, extra={len(result['sprint62_extra'])}, v63={len(result['v63'])}")
