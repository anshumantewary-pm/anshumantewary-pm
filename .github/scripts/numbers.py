"""Write the profile's live cards into dist/:

* numbers.svg   "By the numbers": all-time GitHub contributions (highlighted), LinkedIn
                connections, years consulting
* trophies.svg  Trophy shelf ranked from real GitHub data (the public trophy
                service is often down, so the profile generates its own)
* github-stats.svg  Commits, contributions, repos, stars and a top-languages bar (replaces the
                   public github-readme-stats cards, which are often rate-limited or stale)
* numbers.json  The raw values, reused as a fallback if the API fails next time

Every element is visible without animation; the fade-ins are extras. Viewers that
do not play SVG animation (GitHub mobile, reduced motion) still see everything.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

USER = os.environ.get("GITHUB_USER", "anshumantewary-pm")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
PREVIOUS = f"https://raw.githubusercontent.com/{USER}/{USER}/output/numbers.json"

LINKEDIN_CONNECTIONS = "11K+"  # 11,196 in the LinkedIn export of 2026-10-22
CONSULTING_YEARS = 3  # shown as "3+"

FONT = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def fetch_json(url: str, token: str = "") -> object:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def graphql(query: str, variables: dict, token: str) -> dict:
    """Run a GitHub GraphQL query (needs a token; GITHUB_TOKEN works in Actions)."""
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.load(response)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def contributions(created: datetime) -> tuple[int, int]:
    """(last-year total, all-time total), the same numbers as the profile's contribution graph.

    contributionsCollection covers at most one year per query, so the all-time total asks for
    each calendar year since the account was created, in one request via aliases.
    """
    now = datetime.now(timezone.utc)
    years = range(created.year, now.year + 1)
    per_year = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z")'
        " { contributionCalendar { totalContributions } }"
        for y in years
    )
    query = (
        "query($login: String!) { user(login: $login) {"
        " lastYear: contributionsCollection { contributionCalendar { totalContributions } }\n"
        f"{per_year} }} }}"
    )
    user = graphql(query, {"login": USER}, TOKEN)["user"]
    last_year = int(user["lastYear"]["contributionCalendar"]["totalContributions"])
    all_time = sum(int(user[f"y{y}"]["contributionCalendar"]["totalContributions"]) for y in years)
    return last_year, all_time


def top_languages(repos: list[dict[str, Any]]) -> list[list[Any]]:
    """[[language, share], ...] by bytes of code across owned, non-fork repos (top 6)."""
    totals: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        try:
            langs = fetch_json(repo["languages_url"], TOKEN)
        except Exception:
            continue
        for name, size in dict(langs).items():  # type: ignore[arg-type]
            totals[name] = totals.get(name, 0) + int(size)
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    return [[name, size / grand] for name, size in ranked]


def gather() -> dict[str, Any]:
    """Live stats from the GitHub API; fall back to the last published values."""
    try:
        api = "https://api.github.com"
        user = fetch_json(f"{api}/users/{USER}", TOKEN)
        repos = fetch_json(
            f"{api}/users/{USER}/repos?per_page=100&type=owner&sort=pushed", TOKEN
        )
        created = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))  # type: ignore[index]
        last_year, all_time = contributions(created)
        commits = fetch_json(f"{api}/search/commits?q=author:{USER}", TOKEN)["total_count"]  # type: ignore[index]
        stats: dict[str, Any] = {
            "commits": int(commits),
            "contributions": last_year,
            "contributions_all_time": all_time,
            "repos": int(user["public_repos"]),  # type: ignore[index]
            "languages": len({r["language"] for r in repos if r.get("language")}),  # type: ignore[union-attr]
            "stars": sum(int(r["stargazers_count"]) for r in repos),  # type: ignore[union-attr]
            "github_years": (datetime.now(timezone.utc) - created).days // 365,
        }
    except Exception as error:
        print(f"GitHub API failed ({error}); reusing the previous values")
        empty: dict[str, Any] = {"commits": 0, "contributions": 0, "contributions_all_time": 0,
                                 "repos": 0, "languages": 0, "stars": 0, "github_years": 0,
                                 "top_languages": []}
        try:
            return {**empty, **dict(fetch_json(PREVIOUS))}  # type: ignore[arg-type]
        except Exception:
            return empty
    # The extras each fail on their own, so one bad call never blanks the whole card.
    for key, call in (
        ("top_languages", lambda: top_languages(repos)),  # type: ignore[arg-type]
    ):
        try:
            stats[key] = call()
        except Exception as error:
            print(f"{key} failed ({error})")
            stats[key] = []
    return stats


def fade(delay: float) -> str:
    """Fade in from the start of the timeline; the element's own opacity stays 1."""
    return (
        f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{delay / (delay + 0.8):.3f};1" '
        f'dur="{delay + 0.8:.2f}s" />'
    )


def numbers_svg(stats: dict[str, Any]) -> str:
    def tile(x: int, delay: float, emoji: str, value: str, label: str, sub: str,
             highlight: bool = False) -> str:
        # The highlighted tile has a thicker gold border, inset so it is not clipped.
        rect = (
            'x="2" y="2" width="256" height="146" stroke="url(#gold)" stroke-width="4"'
            if highlight
            else 'x="0" y="0" width="260" height="150" stroke="url(#edge)" stroke-width="2"'
        )
        return f"""
  <g transform="translate({x} 0)">{fade(delay)}
    <rect {rect} rx="18" fill="#1f1235" />
    <text x="130" y="44" font-size="30" text-anchor="middle">{emoji}</text>
    <text x="130" y="92" font-size="40" font-weight="800" text-anchor="middle" fill="url(#gold)">{value}</text>
    <text x="130" y="118" font-size="15" font-weight="700" text-anchor="middle" fill="#fff4e0">{label}</text>
    <text x="130" y="137" font-size="12" text-anchor="middle" fill="#d9c6ff">{sub}</text>
  </g>"""

    tiles = "".join(
        [
            tile(20, 0.2, "🔥", f"{stats['contributions_all_time']:,}", "Total contributions",
                 f"all years · {stats['contributions']:,} in the last year", highlight=True),
            tile(300, 0.5, "🤝", LINKEDIN_CONNECTIONS, "LinkedIn connections", "and growing"),
            tile(580, 0.8, "🧠", f"{CONSULTING_YEARS}+ yrs", "Strategic consulting", "growth · product · operations"),
        ]
    )
    label = (
        f"By the numbers: {stats['contributions_all_time']} GitHub contributions in total, "
        f"{LINKEDIN_CONNECTIONS} LinkedIn "
        f"connections, {CONSULTING_YEARS}+ years in strategic consulting"
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="170" viewBox="0 0 860 170" role="img" aria-label="{label}">
  <defs>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffd23f" /><stop offset="1" stop-color="#ff7b29" /></linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffaf7b" /><stop offset="0.5" stop-color="#d76d77" /><stop offset="1" stop-color="#7928ca" /></linearGradient>
  </defs>
  <g font-family="{FONT}">{tiles}
  </g>
</svg>
"""


# (title, unit, value key, thresholds for S / A / B / C)
TROPHIES = [
    ("Commits", "commits", "commits", (1000, 500, 100, 10)),
    ("Repositories", "repos", "repos", (50, 30, 10, 1)),
    ("Languages", "languages", "languages", (8, 5, 3, 1)),
    ("GitHub years", "years", "github_years", (5, 3, 2, 1)),
    ("Consulting", "years", "consulting_years", (5, 3, 2, 1)),
]
RANK_COLOURS = {"S": "#ffd23f", "A": "#ffaf7b", "B": "#d76d77", "C": "#b392f0", "-": "#6e6a86"}


def rank(value: int, thresholds: tuple[int, int, int, int]) -> str:
    for letter, minimum in zip("SABC", thresholds):
        if value >= minimum:
            return letter
    return "-"


def trophies_svg(stats: dict[str, Any]) -> str:
    values = {**stats, "consulting_years": CONSULTING_YEARS}
    cards = []
    for i, (title, unit, key, thresholds) in enumerate(TROPHIES):
        value = values[key]
        letter = rank(value, thresholds)
        colour = RANK_COLOURS[letter]
        x = 10 + i * 168
        cards.append(f"""
  <g transform="translate({x} 0)">{fade(0.15 * i + 0.1)}
    <rect x="0" y="0" width="156" height="170" rx="16" fill="#1f1235" stroke="{colour}" stroke-opacity="0.7" stroke-width="2" />
    <g transform="translate(78 62)" fill="{colour}">
      <path d="M-26 -34 h52 v14 a26 26 0 0 1 -52 0 z" />
      <path d="M-26 -28 h-12 a12 12 0 0 0 12 18 z M26 -28 h12 a12 12 0 0 1 -12 18 z" opacity="0.75" />
      <rect x="-5" y="-2" width="10" height="16" />
      <rect x="-18" y="14" width="36" height="8" rx="2" />
      <text x="0" y="-12" font-size="18" font-weight="900" text-anchor="middle" fill="#1f1235">{letter}</text>
    </g>
    <text x="78" y="118" font-size="15" font-weight="800" text-anchor="middle" fill="#fff4e0">{title}</text>
    <text x="78" y="140" font-size="13" text-anchor="middle" fill="#d9c6ff">{value:,} {unit}</text>
    <text x="78" y="158" font-size="11" text-anchor="middle" fill="{colour}">Rank {letter}</text>
  </g>""")
    width = 10 + len(TROPHIES) * 168
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="180" viewBox="0 0 {width} 180" role="img" aria-label="GitHub trophies">
  <g font-family="{FONT}">{"".join(cards)}
  </g>
</svg>
"""


LANG_COLOURS = ["#ffd23f", "#ff7b29", "#ff0080", "#b392f0", "#00dfd8", "#7928ca"]


def stats_svg(stats: dict[str, Any], now: datetime) -> str:
    tiles = [
        ("Commits", stats["commits"], "all time"),
        ("Contributions", stats["contributions"], "past year"),
        ("Repositories", stats["repos"], "public"),
        ("Stars", stats["stars"], "earned"),
    ]
    cells = "".join(
        f"""
  <g transform="translate({20 + (i % 2) * 200} {20 + (i // 2) * 92})">{fade(0.15 * i + 0.1)}
    <rect width="186" height="80" rx="14" fill="#1f1235" stroke="url(#edge)" stroke-width="1.5" />
    <text x="16" y="28" font-size="13" font-weight="700" fill="#d9c6ff">{label}</text>
    <text x="16" y="60" font-size="28" font-weight="800" fill="url(#gold)">{value:,}</text>
    <text x="170" y="28" font-size="11" text-anchor="end" fill="#8f86a8">{sub}</text>
  </g>"""
        for i, (label, value, sub) in enumerate(tiles)
    )
    langs = stats.get("top_languages") or []
    bar, legend, x = "", "", 0.0
    for i, (name, share) in enumerate(langs):
        width = 380 * float(share)
        colour = LANG_COLOURS[i % len(LANG_COLOURS)]
        bar += f'<rect x="{x:.1f}" y="0" width="{max(width, 2):.1f}" height="14" fill="{colour}" />'
        x += width
        legend += (
            f'<g transform="translate({(i % 2) * 190} {36 + (i // 2) * 26})">'
            f'<circle cx="6" cy="-4" r="6" fill="{colour}" />'
            f'<text x="18" y="0" font-size="13" fill="#fff4e0">{escape(name)}</text>'
            f'<text x="170" y="0" font-size="12" text-anchor="end" fill="#d9c6ff">{float(share) * 100:.1f}%</text></g>'
        )
    if not langs:
        legend = '<text x="0" y="40" font-size="13" fill="#8f86a8">No language data yet</text>'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="230" viewBox="0 0 860 230" role="img" aria-label="GitHub stats: {stats['commits']} commits, {stats['contributions']} contributions in the last year, {stats['repos']} repositories">
  <defs>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffd23f" /><stop offset="1" stop-color="#ff7b29" /></linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffaf7b" /><stop offset="0.5" stop-color="#d76d77" /><stop offset="1" stop-color="#7928ca" /></linearGradient>
    <clipPath id="pill"><rect width="380" height="14" rx="7" /></clipPath>
  </defs>
  <g font-family="{FONT}">{cells}
  <g transform="translate(440 20)">{fade(0.7)}
    <rect width="400" height="172" rx="14" fill="#1f1235" stroke="url(#edge)" stroke-width="1.5" />
    <text x="16" y="28" font-size="13" font-weight="700" fill="#d9c6ff">Top languages</text>
    <g transform="translate(10 44)"><g clip-path="url(#pill)"><rect width="380" height="14" fill="#2c1d48" />{bar}</g></g>
    <g transform="translate(16 74)">{legend}</g>
  </g>
  <text x="840" y="218" font-size="11" text-anchor="end" fill="#8f86a8">Updated {now:%d %b %Y, %H:%M} UTC</text>
  </g>
</svg>
"""


def main() -> None:
    stats = gather()
    out = Path("dist")
    out.mkdir(exist_ok=True)
    (out / "numbers.svg").write_text(numbers_svg(stats), encoding="utf-8")
    (out / "trophies.svg").write_text(trophies_svg(stats), encoding="utf-8")
    now = datetime.now(timezone.utc)
    (out / "github-stats.svg").write_text(stats_svg(stats, now), encoding="utf-8")
    (out / "numbers.json").write_text(json.dumps(stats), encoding="utf-8")
    print(f"cards written: {stats}")


if __name__ == "__main__":
    main()
