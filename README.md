# tech-updates — Early-Adoption Intelligence Collector (shareable package)

A self-contained collector pipeline that watches catalogs, launch
surfaces, code platforms, adoption feeds and chatter for a topic you care
about, and writes human-readable markdown runs into a data root you control.

One dependency: `pyyaml` (parses sources.yaml) —
`pip install -r requirements.txt`. Everything else is Python 3 stdlib:
no database, no secrets required to run (optional tokens only raise API
rate limits).

## Package contents

- `scripts/` — the pipeline: `collect.py` (runner), `init_store.py`
  (data-tree scaffold), `config.py` (sources.yaml loader), `paths.py`
  (root resolver), `store.py`, `util.py`, `_lock.py`, `_textio.py`,
  `collectors/` (one module per source kind), `templates/` (data-tree
  templates), `store.config.example.json`.
- `sources.template.yaml` — starter source plate with `YOUR_*` placeholders.
- `sources.example.yaml` — the full 23-source production plate, for reference.

## Setup (friend flow)

Install the one dependency, then run:

    pip install -r requirements.txt
    python setup.py

It asks for your data root, lets you pick which of the 23 sources to
enable (recorded as `run.disable` in `sources.yaml`), prompts for API
keys **only** those picked sources need (stored via the OS keyring), scaffolds the data tree, creates `sources.yaml`
from the template, and points the pipeline at your root — idempotent,
safe to re-run, existing files never overwritten, missing keys
re-prompted. Non-interactive:

    python setup.py --root <path> --no-probe --sources 1,3-5 \
        --token GITHUB_TOKEN=... --token PRODUCTHUNT_TOKEN=...

Day-2 maintenance — these are one-shot and never re-run onboarding:

    python setup.py --token PRODUCTHUNT_TOKEN=...   # store/replace a key
    python setup.py --probe                         # health-check selected sources
                                                    # (same: scripts/collect.py --probe)

Manual equivalent (what setup.py automates), from a terminal inside
this folder:

1. Scaffold your data root (anywhere you like):

       python scripts/init_store.py --root ~/tech-updates-data

   This creates `runs/`, `runs/sources/`, `findings/`, `log.md`,
   `watchlist.md` at that root. It refuses to overwrite an existing tree
   unless you pass `--force`.

2. Create your source plate:

       cp sources.template.yaml sources.yaml
       # edit sources.yaml: replace every YOUR_* placeholder with your own
       # repos, packages, keywords, subreddits, arXiv categories, topics;
       # optionally edit run.disable to skip sources you don't want

   `sources.example.yaml` shows a fully-populated plate you can borrow from.
   Optional API keys: export the env vars, keep them in the package's
   `.env` file, or store them in the OS keyring (`setup.py --token
   GITHUB_TOKEN=...` does that; lookup order is env -> keyring -> `.env`)
   — everything also works keyless.

3. Point the pipeline at your data root:

       cp scripts/store.config.example.json scripts/store.config.json
       # edit scripts/store.config.json:
       #   "tech_updates_root": "/home/you/tech-updates-data"
       # (Alternatively set the TECH_UPDATES_ROOT environment variable —
       #  the env var wins over the config file.)

4. Probe all sources (no store writes — pure connectivity check):

       python scripts/collect.py --probe

5. First real run:

       python scripts/collect.py

   Writes `runs/<date>-<time>.md` plus per-source files under
   `runs/sources/`, appends to `log.md` and `watchlist.md`, and records
   dedupe cursors under your data root. Nothing outside that root is
   written.

6. Schedule it your way (crontab, systemd timer, CI, or an agent cron) —
   the collector is a plain one-shot command; cadence lives entirely in
   your scheduler. After runs accumulate, have an LLM (or yourself) curate
   `findings/` from the run files.

## Configuration precedence (data root)

1. `TECH_UPDATES_ROOT` env var (must point at an existing directory)
2. `tech_updates_root` in `scripts/store.config.json` (must exist)
3. default: `tech-updates/` inside the package folder

`scripts/store.config.json` is machine-local — never commit or share it.

## Privacy / what stays local

All state (cursors, tokens, run output) lives in YOUR data root. This
package ships no tokens, no cursors, and no run data. `state/`,
`tech-updates/` and internal notes from the maintainer's install are
deliberately excluded.
