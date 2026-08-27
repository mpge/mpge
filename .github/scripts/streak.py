"""Render a contribution-streak card as a committed SVG.

The hosted streak services are unusable from a README. streak-stats.demolab.com
cold-starts: the first request after an idle period takes about thirty seconds
and answers 503, and GitHub's image proxy gives up long before that and caches a
504. The card then stays broken until camo's cache expires, whatever the service
does in the meantime.

So this computes the same three numbers locally and commits the SVG, which is
the pattern already used for code-per-day and profile-3d-contrib in this
repository. A file in the repo cannot time out.

Contribution data comes from the GraphQL contributionsCollection, one query per
year the account has contributed in, because a single calendar query covers at
most one year.
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

USER = os.environ.get("STREAK_USER") or "mpge"
OUT = os.environ.get("STREAK_OUT") or "streak/streak.svg"

# The accent already used in the README's contribution graph, and greys that
# stay legible on GitHub's light and dark themes alike -- the card is drawn on
# a transparent background, so it has to work on both.
ACCENT = "#006AFF"
LABEL = "#768390"
VALUE = "#768390"


def graphql(query, variables):
    """Run a GraphQL query through the gh CLI, which already holds a token."""
    args = ["gh", "api", "graphql", "-f", "query=" + query]
    for key, value in variables.items():
        args += ["-F", f"{key}={value}"]

    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"graphql failed: {out.stderr.strip()}")

    return json.loads(out.stdout)


YEARS = """
query($login: String!) {
  user(login: $login) { contributionsCollection { contributionYears } }
}
"""

CALENDAR = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def contributions(login):
    """Every day the account has contributed on, as {date: count}."""
    years = graphql(YEARS, {"login": login})["data"]["user"]
    years = years["contributionsCollection"]["contributionYears"]

    days = {}

    for year in years:
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z"

        weeks = graphql(CALENDAR, {"login": login, "from": start, "to": end})
        weeks = weeks["data"]["user"]["contributionsCollection"]
        weeks = weeks["contributionCalendar"]["weeks"]

        for week in weeks:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]

    return days


def streaks(days, today):
    """Total, current streak and longest streak.

    A streak is consecutive calendar days with at least one contribution. The
    current one is allowed to end yesterday rather than today, because a day
    with nothing in it yet has not broken anything -- which is the same rule
    the hosted card uses, and the reason a card checked before your first
    commit does not read zero.
    """
    total = sum(days.values())

    dates = sorted(d for d, n in days.items() if n > 0)
    if not dates:
        return total, (0, None, None), (0, None, None), None

    longest = current = 1
    longest_end = current_end = dates[0]
    previous = datetime.strptime(dates[0], "%Y-%m-%d").date()

    for iso in dates[1:]:
        day = datetime.strptime(iso, "%Y-%m-%d").date()

        if day - previous == timedelta(days=1):
            current += 1
        else:
            current = 1

        current_end = iso

        if current >= longest:
            longest, longest_end = current, iso

        previous = day

    last = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    if (today - last).days > 1:
        current, current_end = 0, None

    def span(length, end):
        if not length or not end:
            return length, None, None

        finish = datetime.strptime(end, "%Y-%m-%d").date()
        return length, finish - timedelta(days=length - 1), finish

    first = datetime.strptime(dates[0], "%Y-%m-%d").date()

    return total, span(current, current_end), span(longest, longest_end), first


def pretty(day):
    return f"{day.day} {day.strftime('%b')} {day.year}" if day else ""


def render(total, current, longest, first, today):
    current_n, current_from, current_to = current
    longest_n, longest_from, longest_to = longest

    def panel(x, value, label, sub, big=False):
        size = 34 if big else 28
        ring = ""
        if big:
            ring = (
                f'<circle cx="{x}" cy="58" r="44" fill="none" '
                f'stroke="{ACCENT}" stroke-width="4" opacity="0.9"/>'
            )

        return f"""{ring}
  <text x="{x}" y="{68 if big else 62}" text-anchor="middle"
        font-size="{size}" font-weight="700" fill="{ACCENT}">{value}</text>
  <text x="{x}" y="{116 if big else 96}" text-anchor="middle"
        font-size="14" font-weight="600" fill="{LABEL}"
        letter-spacing="0.5">{label}</text>
  <text x="{x}" y="{136 if big else 116}" text-anchor="middle"
        font-size="11" fill="{VALUE}" opacity="0.85">{sub}</text>"""

    left = panel(
        120, f"{total:,}", "Total Contributions",
        f"{pretty(first)} &#8211; Present" if first else "&#8211;",
    )
    middle = panel(
        330, str(current_n), "Current Streak",
        f"{pretty(current_from)} &#8211; {pretty(current_to)}" if current_n else "&#8211;",
        big=True,
    )
    right = panel(
        540, str(longest_n), "Longest Streak",
        f"{pretty(longest_from)} &#8211; {pretty(longest_to)}" if longest_n else "&#8211;",
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="660" height="160"
     viewBox="0 0 660 160" font-family="Segoe UI, Ubuntu, sans-serif"
     role="img" aria-label="Contribution streak for {USER}">
  <title>{USER}: {total:,} contributions, {current_n}-day current streak, {longest_n}-day longest streak</title>
  <line x1="225" y1="34" x2="225" y2="126" stroke="{LABEL}" stroke-width="1" opacity="0.35"/>
  <line x1="435" y1="34" x2="435" y2="126" stroke="{LABEL}" stroke-width="1" opacity="0.35"/>
{left}
{middle}
{right}
</svg>
"""


def main():
    today = date.today()
    days = contributions(USER)
    total, current, longest, first = streaks(days, today)

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(total, current, longest, first, today))

    print(f"{USER}: total={total} current={current[0]} longest={longest[0]} -> {OUT}")


if __name__ == "__main__":
    main()
