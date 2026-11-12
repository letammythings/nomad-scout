# nomad-scout

A city research tool for a digital-nomad couple. Give it a city, get back a City Scout Report: which neighborhood to target, where the outdoor pull-up bars are, which cafes you can actually work from for four hours, what the budget really buys, and where the listings live.

It encodes the criteria once — in `nomad_scout/criteria.py` — and applies them the same way to every city, so Bangkok and Fukuoka get judged against the same Hai Chau benchmark instead of whatever the internet happens to say that week.

---

## Setup

```bash
git clone https://github.com/letammythings/nomad-scout.git
cd nomad-scout
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Then add your API key. Either export it:

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

or put `ANTHROPIC_API_KEY=...` in a `.env` file in the project folder (`.env` is gitignored).

Get a key at [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).

Check it works:

```bash
./nomad-scout list
```

---

## Using it

### Scout a new city

```bash
./nomad-scout scout "Fukuoka"
```

Takes a few minutes — it runs a live web search pass, then structures the findings. Each dot on screen is one search. The report prints to your terminal and is saved to `reports/fukuoka.md`.

Narrow it to neighborhoods you're already considering:

```bash
./nomad-scout scout "Osaka" -n Nakatsu -n "Nishinakajima" -n Tennoji
```

Other options:

```bash
./nomad-scout scout "Busan" --budget 900          # different budget
./nomad-scout scout "Hanoi" --notes "arriving in November, want to avoid the wet season"
./nomad-scout scout "Taipei" --effort medium      # faster and cheaper, less thorough
./nomad-scout scout "Tokyo" --refresh             # re-research a city already saved
```

### Everything else

```bash
./nomad-scout list                    # every city in the database
./nomad-scout show "Chiang Mai"       # reprint a saved report (free, no API call)
./nomad-scout show "Osaka" --raw      # the original research prose
./nomad-scout compare                 # rank scouted cities by best-neighborhood fit
./nomad-scout checklist "Fukuoka"     # just the pre-arrival checklist
./nomad-scout criteria                # print the criteria and scorecard weights
```

### Score an apartment you viewed

```bash
./nomad-scout score --name "Unit 4B, Santitham" --city "Chiang Mai"
```

It asks for a 0-10 on each of the eight weighted criteria and prints the total with a BOOK IT / GOOD / MAYBE / PASS verdict, plus the criteria costing you the most points — which is what to push back on when you negotiate. With `--city` it saves to that city's record so you can compare shortlisted places later.

---

## What's in a report

| Section | What it gives you |
|---|---|
| Bottom line | Is this city a fit, which neighborhood first, biggest risk |
| Neighborhoods | Ranked with a 0-100 fit score, rent band, and where each sits vs. Hai Chau |
| Outdoor fitness | Named parks, whether pull-up and dip bars are confirmed, walk time, map link |
| Working cafes | Opening time, outlets, whether a 4-hour session is welcome |
| Food & groceries | Local spots and the nearest convenience store, with prices |
| Housing | What the budget buys, the actual Facebook groups and sites, lease norms, red flags |
| Logistics | Transit, real internet speeds, cost of living for two, visa basics |
| Watch-outs | Seasons, noise, pollution, areas to skip |
| Pre-arrival checklist | The four-phase housing SOP plus city-specific additions |

Every place carries an honest caveat and a confidence level. `UNVERIFIED` means it came from a single source and should be checked on the ground — the tool says so rather than presenting a guess as a finding.

The neighborhood fit score uses the same weights as the apartment scorecard, applied to what's knowable before you land.

---

## The scorecard

| Criterion | Weight |
|---|---|
| WiFi 30+ Mbps upload | 20% |
| Cafe within 5 min walk | 15% |
| Gym / pull-up bars within 10-15 min | 15% |
| Neighborhood vibe (local not touristy) | 15% |
| Fully furnished (AC + washer + kitchen) | 15% |
| Price value under $800 | 10% |
| Quiet / no noise | 5% |
| Safety + building quality | 5% |

**80+ book it · 65-79 good · 50-64 maybe · below 50 pass**

---

## Changing the criteria

Everything lives in [`nomad_scout/criteria.py`](nomad_scout/criteria.py) — the budget, the non-negotiables, the scorecard weights, the Hai Chau reference scale, and the four-phase SOP. Edit that file and the prompts, scores, and reports all follow. Nothing is hardcoded anywhere else.

If you raise the budget permanently, change `BUDGET_USD`. If the weights change, keep them summing to 100 (the test suite checks this).

---

## What's already in the database

`data/cities.json` is seeded with the research already done: Ho Chi Minh City, Chiang Mai, Tokyo (Ōta-ku), Osaka, Seoul, Busan, and Fukuoka. Those are marked as prior research rather than tool output — `show` will print what's known, including the open questions each one still has. Run `scout --refresh` on any of them for a full report.

---

## Optional: Google Maps verification

Without a Maps key the tool still works — walk times and ratings are the model's estimates, and the report says so.

With one, every place gets looked up on Google Places: you find out which ones actually exist, their real rating and review count, and a walk-time estimate computed from real coordinates rather than guessed. Places Google can't find get flagged `NOT FOUND`, which is often the most useful line in the report.

Enable **Places API (New)** in Google Cloud, create a key, and add it to `.env`:

```
GOOGLE_MAPS_API_KEY=AIza...
```

Skip it for a single run with `--no-maps`.

---

## Cost

Each `scout` run is one deep research pass on Claude Opus 5 with live web search. Expect roughly **$1-3 per city**, most of it the search results being read. `--effort medium` cuts it meaningfully; `show`, `list`, `compare`, `checklist`, and `score` cost nothing because they only read the local database.

---

## Tests

```bash
.venv/bin/python tests/run_tests.py
```

24 checks covering the scoring maths, the report renderer, the JSON schema, and the whole API call path against a mocked HTTP transport — including what happens on a refusal, a rate limit, a bad key, and a truncated response. No API key needed.

---

## Layout

```
nomad-scout            run it from anywhere
nomad_scout/
  criteria.py          the criteria, weights, and SOP — edit this
  prompts.py           what the researcher is told
  schema.py            the structured findings schema
  client.py            Claude API calls: research pass + extraction pass
  research.py          orchestration
  maps.py              optional Google Places verification
  scoring.py           weighted scoring
  report.py            markdown rendering
  database.py          the city database
  cli.py               commands
data/cities.json       every city scouted, plus prior research
reports/               generated markdown reports
tests/run_tests.py     the test suite
```

---

## How it works

Two API calls per city. The first runs Claude Opus 5 with the web search and web fetch tools and the criteria as its system prompt, and produces a scouting report in prose. The second re-reads that report with a strict JSON schema and no tools, turning it into structured findings — so scoring, map links, and the database all work off typed data rather than parsed prose. The optional Maps pass then verifies each place against Google Places.

Splitting it in two is deliberate: the research pass needs tools and long-running search, the extraction pass needs a rigid output shape, and mixing the two makes both less reliable.
