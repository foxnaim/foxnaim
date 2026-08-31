#!/usr/bin/env python3
"""Refresh committed profile cards. Requires Python 3 and authenticated GitHub CLI.

Run: python3 scripts/update-profile-cards.py
Cards are served from this repository, so an API outage cannot replace them with
an error image. Failed requests leave all existing cards untouched. No token is
written to disk. Only public repositories and aggregate contributions are used.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOGIN = "foxnaim"
QUERY = '''query { user(login: "foxnaim") { contributionsCollection {
  contributionCalendar { totalContributions weeks {
    contributionDays { date contributionCount weekday }
  } }
} } }'''


def gh(*args):
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=True, timeout=90)
    return json.loads(result.stdout)


def text(x, y, value, size=14, color="#8b949e", weight=400):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'


def svg(height, title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="920" height="{height}" viewBox="0 0 920 {height}" role="img" aria-label="{escape(title, quote=True)}">'
            f'<title>{escape(title)}</title><rect x=".5" y=".5" width="919" height="{height-1}" rx="14" fill="#0d1117" stroke="#30363d"/>'
            f'<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">{body}</g></svg>\n')


def render(repos, calendar, date):
    public_repos = [repo for repo in repos if not repo.get("private", False)]
    languages = Counter(repo["language"] for repo in public_repos if repo.get("language"))
    stats = [(len(public_repos), "Public repositories"),
             (sum(repo["stargazers_count"] for repo in public_repos), "Stars across public repos"),
             (calendar["totalContributions"], "Contributions · last 12 months")]
    body = text(30, 38, "GitHub at a glance", 20, "#58a6ff", 600)
    body += text(675, 37, f"Snapshot · {date} UTC", 11)
    for index, (value, label) in enumerate(stats):
        x = 30 + index * 298
        body += text(x, 96, f"{value:,}", 34, "#e6edf3", 600)
        body += text(x, 123, label, 12)
    body += '<path d="M30 148H890" stroke="#21262d"/>'
    body += text(30, 177, "Primary language by repository", 12, "#8b949e")
    palette = ["#3178c6", "#f1e05a", "#e34c26", "#3572A5", "#a371f7"]
    x = 30
    coded = sum(languages.values())
    for index, (language, count) in enumerate(languages.most_common()):
        color = palette[index % len(palette)]
        width = count / coded * 860
        body += f'<rect x="{x:.2f}" y="192" width="{width:.2f}" height="6" fill="{color}"/>'
        lx = 30 + index * 222
        body += f'<circle cx="{lx+4}" cy="222" r="4" fill="{color}"/>'
        body += text(lx+15, 226, f"{language} · {count} repos", 12, "#c9d1d9")
        x += width
    body += text(30, 252, "Repositories without a primary language are excluded from the language bar.", 10)
    overview = svg(274, f"GitHub profile snapshot for {LOGIN}, updated {date}", body)

    weeks = calendar["weeks"]
    body = text(30, 37, "A year of building", 20, "#58a6ff", 600)
    body += text(30, 59, f'{calendar["totalContributions"]:,} contributions · {weeks[0]["contributionDays"][0]["date"]} to {weeks[-1]["contributionDays"][-1]["date"]}', 11)
    cell, gap = 11, 4
    prior_month = None
    for column, week in enumerate(weeks):
        for day in week["contributionDays"]:
            count = day["contributionCount"]
            color = "#161b22" if count == 0 else "#0e3158" if count < 5 else "#155ca2" if count < 15 else "#1f6feb" if count < 35 else "#58a6ff"
            x, y = 70 + column * (cell + gap), 88 + day["weekday"] * (cell + gap)
            body += f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"><title>{day["date"]}: {count} contributions</title></rect>'
        first = week["contributionDays"][0]["date"]
        month = first[:7]
        if month != prior_month and column < len(weeks)-2:
            body += text(70 + column * (cell + gap), 80, datetime.fromisoformat(first).strftime("%b"), 9)
            prior_month = month
    for label, weekday in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
        body += text(30, 97 + weekday * (cell + gap), label, 9)
    body += text(30, 225, f"Saved {date} UTC · Live activity: github.com/{LOGIN}", 10)
    body += text(714, 225, "Less", 9)
    for index, color in enumerate(["#161b22", "#0e3158", "#155ca2", "#1f6feb", "#58a6ff"]):
        body += f'<rect x="{747+index*16}" y="216" width="11" height="11" rx="2" fill="{color}"/>'
    body += text(835, 225, "More", 9)
    graph = svg(247, f"GitHub contribution calendar for {LOGIN}, snapshot {date}", body)
    return {"github-overview.svg": overview, "activity-graph.svg": graph}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-json", type=Path)
    parser.add_argument("--calendar-json", type=Path)
    args = parser.parse_args()
    if args.repos_json:
        repos = json.loads(args.repos_json.read_text())
    else:
        repos = []
        page = 1
        while True:
            chunk = gh(f"users/{LOGIN}/repos?per_page=100&page={page}")
            repos.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
    data = json.loads(args.calendar_json.read_text()) if args.calendar_json else gh("graphql", "-f", f"query={QUERY}")
    calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    if not repos or not calendar["weeks"]:
        raise ValueError("Incomplete response; existing cards have not been changed")
    cards = render(repos, calendar, datetime.now(timezone.utc).date().isoformat())
    destination = ROOT / "assets" / "profile"
    destination.mkdir(parents=True, exist_ok=True)
    for filename, content in cards.items():
        temporary = destination / f".{filename}.tmp"
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(destination / filename)
    print("Updated committed profile cards. Review and commit assets/profile/ to publish.")


if __name__ == "__main__":
    main()
