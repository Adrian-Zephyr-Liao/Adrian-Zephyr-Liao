"""Refresh locally stored profile graphics from public GitHub card services."""

import argparse
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
USERNAME = "Adrian-Zephyr-Liao"
COLORS = {
    "bg_color": "11151d",
    "title_color": "ffb68b",
    "text_color": "b3bdce",
    "icon_color": "ff9a66",
    "hide_border": "true",
    "border_radius": "12",
    "disable_animations": "true",
}


def endpoint(base, **options):
    return base + "?" + urlencode({"username": USERNAME, **COLORS, **options})


CARDS = {
    "assets/github-stats.svg": endpoint(
        "https://github-stats-extended.vercel.app/api",
        show_icons="true",
        hide_rank="true",
        hide="stars",
        card_width="420",
        custom_title="GitHub Stats",
    ),
    "assets/github-languages.svg": endpoint(
        "https://github-stats-extended.vercel.app/api/top-langs/",
        layout="compact",
        langs_count="6",
        card_width="420",
        custom_title="Top Languages",
    ),
}

BADGES = {
    "typescript": ("TypeScript", "typescript", "3178C6"),
    "react": ("React", "react", "61DAFB"),
    "vue": ("Vue", "vuedotjs", "4FC08D"),
    "nodejs": ("Node.js", "nodedotjs", "5FA04E"),
    "python": ("Python", "python", "FFD343"),
    "git": ("Git", "git", "F05032"),
    "docker": ("Docker", "docker", "2496ED"),
    "postgresql": ("PostgreSQL", "postgresql", "4169E1"),
}


def download(item):
    path, url = item
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "Adrian-Profile-Cards"})
            with urlopen(request, timeout=20) as response:
                if response.headers.get_content_type() != "image/svg+xml":
                    raise ValueError(f"{path}: response is not an SVG image")
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError(f"{path}: SVG exceeds the size limit")
            svg = ET.fromstring(data)
            if svg.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError(f"{path}: invalid SVG root")
            text = " ".join(svg.itertext()).casefold()
            if any(message in text for message in (
                "something went wrong", "api rate limit exceeded",
                "could not resolve to a user", "maximum retries exceeded",
            )):
                raise ValueError(f"{path}: card service returned an error image")
            return path, data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


class ContributionCalendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.dates = {}
        self.counts = {}
        self.tooltip_id = None
        self.tooltip_text = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "td" and attributes.get("data-date"):
            self.dates[attributes["id"]] = date.fromisoformat(attributes["data-date"])
        if tag == "tool-tip":
            self.tooltip_id = attributes.get("for")
            self.tooltip_text = []

    def handle_data(self, text):
        if self.tooltip_id:
            self.tooltip_text.append(text)

    def handle_endtag(self, tag):
        if tag != "tool-tip":
            return
        match = re.match(r"([\d,]+|No) contributions? on", "".join(self.tooltip_text).strip())
        if self.tooltip_id in self.dates and match:
            count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
            self.counts[self.dates[self.tooltip_id]] = count
        self.tooltip_id = None


def contribution_days():
    # The default endpoint returns a rolling year; date filters select a calendar year.
    url = f"https://github.com/users/{USERNAME}/contributions"
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "Adrian-Profile-Cards"})
            with urlopen(request, timeout=20) as response:
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("Contribution calendar exceeds the size limit")
            parser = ContributionCalendar()
            parser.feed(data.decode("utf-8"))
            last = min(date.today(), max(parser.counts))
            first = last - timedelta(days=364)
            days = [(day, parser.counts[day]) for day in
                    (first + timedelta(days=i) for i in range(365))]
            return days
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def contribution_svg(days, mobile=False):
    total = sum(count for _, count in days)
    weeks = [sum(count for _, count in days[i:i + 7]) for i in range(0, 365, 7)]
    width, height = (720, 460) if mobile else (1280, 300)
    left, top, chart_width, chart_height = (36, 238, 648, 138) if mobile else (342, 80, 894, 144)
    baseline = top + chart_height
    ceiling = max(10, ((max(weeks) + 9) // 10) * 10)
    step = chart_width / len(weeks)
    bars = []
    for index, count in enumerate(weeks):
        bar_height = count / ceiling * chart_height
        x = left + index * step + 1
        if count:
            bars.append(f'<rect x="{x:.2f}" y="{baseline - bar_height:.2f}" '
                        f'width="{step - 3:.2f}" height="{bar_height:.2f}" rx="2" fill="#ff9a66"/>')
        else:
            bars.append(f'<rect x="{x:.2f}" y="{baseline - 2}" '
                        f'width="{step - 3:.2f}" height="2" rx="1" fill="#39404e"/>')
    ticks = []
    for fraction in (0, .5, 1):
        y = baseline - fraction * chart_height
        ticks.append(f'<path d="M{left} {y}h{chart_width}" stroke="#b3bdce" stroke-opacity=".1"/>')
    for index, anchor in ((0, "start"), (26, "middle"), (52, "end")):
        label = days[min(index * 7, 364)][0].strftime("%b %Y")
        x = left + index / 52 * chart_width
        ticks.append(f'<text x="{x:.2f}" y="{baseline + 30}" text-anchor="{anchor}" '
                     f'class="mono" font-size="{18 if mobile else 15}" fill="#9daabe">{label}</text>')
    padding = 36 if mobile else 44
    number_y = 145 if mobile else 153
    number_size = 88 if mobile else 78
    subtitle_y = 185 if mobile else 191
    range_text = escape(f'{days[0][0]:%b %d, %Y} – {days[-1][0]:%b %d, %Y}')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">
<title id="title">Public GitHub contribution activity</title>
<desc id="description">{total} public contributions over 365 days, from {days[0][0]} to {days[-1][0]}. Bars show consecutive seven-day totals; the final bar covers the remaining day.</desc>
<style>.display{{font-family:'Geist','Avenir Next','Segoe UI',sans-serif;font-weight:650;letter-spacing:-2px}}.mono{{font-family:'SFMono-Regular',Consolas,'Liberation Mono',monospace}}</style>
<rect width="{width}" height="{height}" rx="16" fill="#11151d"/>
<text x="{padding}" y="48" class="mono" font-size="{21 if mobile else 18}" letter-spacing="1.2" fill="#ffb68b">CONTRIBUTION ACTIVITY</text>
<text x="{padding}" y="{number_y}" class="display" font-size="{number_size}" fill="#f3f5f8">{total:,}</text>
<text x="{padding}" y="{subtitle_y}" class="mono" font-size="{23 if mobile else 18}" fill="#b3bdce">public contributions</text>
<text x="{padding}" y="{432 if mobile else 262}" class="mono" font-size="{17 if mobile else 14}" fill="#9daabe">{range_text}</text>
<text x="{width - padding}" y="{218 if mobile else 48}" text-anchor="end" class="mono" font-size="{17 if mobile else 14}" fill="#9daabe">WEEKLY TOTALS</text>
{''.join(ticks)}{''.join(bars)}
</svg>'''
    return svg.encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-badges", action="store_true")
    args = parser.parse_args()
    sources = dict(CARDS)
    if args.refresh_badges:
        for slug, (name, logo, color) in BADGES.items():
            sources[f"assets/badges/{slug}.svg"] = (
                f"https://img.shields.io/badge/{name}-11151d?"
                + urlencode({"style": "for-the-badge", "logo": logo, "logoColor": color})
            )

    # Validate the entire refresh before replacing any last known good graphics.
    with ThreadPoolExecutor(max_workers=4) as pool:
        calendar = pool.submit(contribution_days)
        results = list(pool.map(download, sources.items()))
        days = calendar.result()
    results.extend([
        ("assets/github-contributions.svg", contribution_svg(days)),
        ("assets/github-contributions-mobile.svg", contribution_svg(days, mobile=True)),
    ])
    for relative, data in results:
        data = b"\n".join(line.rstrip() for line in data.splitlines()).rstrip() + b"\n"
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".svg.tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
        print(f"Updated {relative} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
