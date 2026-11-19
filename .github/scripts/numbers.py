"""Write dist/numbers.svg: the "By the numbers" card on the profile README.

GitHub commits are counted live from the public search API on every run, so the
card stays current. LinkedIn connections and years of experience change rarely
and are set below. If the API call fails, the last published count is reused
rather than showing zero.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

USER = os.environ.get("GITHUB_USER", "anshumantewary-pm")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
PREVIOUS = f"https://raw.githubusercontent.com/{USER}/{USER}/output/numbers.json"

LINKEDIN_CONNECTIONS = "11K+"  # 11,196 in the LinkedIn export of 2026-10-22
CONSULTING_YEARS = "3+"


def fetch_json(url: str, token: str = "") -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def commit_count() -> int:
    try:
        return int(fetch_json(f"https://api.github.com/search/commits?q=author:{USER}", TOKEN)["total_count"])
    except Exception as error:  # network or rate limit: fall back to the last good value
        print(f"search API failed ({error}); reusing the previous count")
        try:
            return int(fetch_json(PREVIOUS)["commits"])
        except Exception:
            return 0


def tile(x: int, delay: float, emoji: str, value: str, label: str, sub: str) -> str:
    return f"""
  <g transform="translate({x} 0)" opacity="0">
    <animate attributeName="opacity" values="0;1" begin="{delay}s" dur="0.8s" fill="freeze" />
    <animateTransform attributeName="transform" type="translate" values="{x} 14; {x} 0" begin="{delay}s" dur="0.8s" fill="freeze" />
    <rect x="0" y="0" width="260" height="150" rx="18" fill="#1f1235" stroke="url(#edge)" stroke-width="2" />
    <text x="130" y="44" font-size="30" text-anchor="middle">{emoji}</text>
    <text x="130" y="92" font-size="40" font-weight="800" text-anchor="middle" fill="url(#gold)">{value}</text>
    <text x="130" y="118" font-size="15" font-weight="700" text-anchor="middle" fill="#fff4e0">{label}</text>
    <text x="130" y="137" font-size="12" text-anchor="middle" fill="#d9c6ff">{sub}</text>
  </g>"""


def main() -> None:
    commits = commit_count()
    tiles = "".join(
        [
            tile(20, 0.2, "💻", f"{commits:,}", "GitHub commits", "public, all repos · updated daily"),
            tile(300, 0.5, "🤝", LINKEDIN_CONNECTIONS, "LinkedIn connections", "and growing"),
            tile(580, 0.8, "🧠", f"{CONSULTING_YEARS} yrs", "Strategic consulting", "growth · product · operations"),
        ]
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="170" viewBox="0 0 860 170" role="img" aria-label="By the numbers: {commits} GitHub commits, {LINKEDIN_CONNECTIONS} LinkedIn connections, {CONSULTING_YEARS} years in strategic consulting">
  <defs>
    <linearGradient id="gold" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffd23f" /><stop offset="1" stop-color="#ff7b29" />
    </linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffaf7b" /><stop offset="0.5" stop-color="#d76d77" /><stop offset="1" stop-color="#7928ca" />
    </linearGradient>
  </defs>
  <g font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif">{tiles}
  </g>
</svg>
"""
    out = Path("dist")
    out.mkdir(exist_ok=True)
    (out / "numbers.svg").write_text(svg, encoding="utf-8")
    (out / "numbers.json").write_text(json.dumps({"commits": commits}), encoding="utf-8")
    print(f"numbers.svg written: {commits} commits")


if __name__ == "__main__":
    main()
