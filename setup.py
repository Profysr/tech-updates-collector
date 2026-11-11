#!/usr/bin/env python3
"""setup.py — interactive onboarding for the tech-updates package.

Replaces the manual friend flow (README steps 1-3) with one command:
  python setup.py

Asks for:
  1. Data root            (default ~/tech-updates-data)
  2. Source selection     (numbered picker over all 23 sources; recorded as
                          run.disable in sources.yaml)
  3. API keys             (only for SELECTED sources that need one — hidden
                          input, stored in state/tokens/<NAME>; keyless works)
  4. Whether to probe all sources when done

What it does:
  - scaffolds the data tree (init_store.py --root <root>, refuses overwrite)
  - copies sources.template.yaml -> sources.yaml (if absent) + records selection
  - writes scripts/store.config.json pointing at your data root
  - writes state/tokens/<NAME> for each key you give (never stored anywhere else)

Non-interactive use:
  python setup.py --root ~/data --no-probe --sources 1,3-5 --token GITHUB_TOKEN=...

Everything except tokens is re-runnable: existing files are never overwritten;
missing keys are re-prompted.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
SCRIPTS = PKG / "scripts"
INIT = SCRIPTS / "init_store.py"
TEMPLATE = PKG / "sources.template.yaml"

sys.path.insert(0, str(SCRIPTS))
import config  # shared plate parser — same one collect.py uses


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def ask_secret(prompt: str) -> str:
    import getpass
    try:
        val = getpass.getpass(f"{prompt} (input hidden, empty to skip): ").strip()
    except Exception:
        val = input(f"{prompt} (empty to skip): ").strip()
    return val


def load_catalog() -> list[tuple[str, str, str]]:
    """(runner key, plate entry, token) rows from collect.py --list-sources."""
    r = subprocess.run([sys.executable, str(SCRIPTS / "collect.py"), "--list-sources"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        print("collect.py --list-sources failed:\n" + r.stderr, file=sys.stderr)
        sys.exit(1)
    return [tuple(line.split("|")) for line in r.stdout.splitlines() if line.strip()]


def parse_selection(spec: str, keys: list[str]) -> set[str]:
    """'all' | '1,3,5-7' | comma list of numbers/ranges/source keys."""
    spec = spec.strip() or "all"
    if spec.lower() == "all":
        return set(keys)
    out: set[str] = set()
    for tok in (t.strip() for t in spec.split(",")):
        if not tok:
            continue
        if tok in keys:
            out.add(tok)
        elif tok.isdigit() and 1 <= int(tok) <= len(keys):
            out.add(keys[int(tok) - 1])
        elif "-" in tok and all(p.isdigit() for p in tok.split("-")):
            a, b = (int(p) for p in tok.split("-"))
            for i in range(min(a, b), max(a, b) + 1):
                if 1 <= i <= len(keys):
                    out.add(keys[i - 1])
        else:
            raise ValueError(f"bad source selector: {tok}")
    if not out:
        raise ValueError("no sources selected")
    return out


def pick_sources(catalog: list[tuple[str, str, str]], args) -> set[str]:
    keys = [k for k, _, _ in catalog]
    if args.sources:
        try:
            return parse_selection(args.sources, keys)
        except ValueError as e:
            print(f"--sources: {e}", file=sys.stderr)
            sys.exit(2)
    if args.non_interactive:
        return set(keys)
    print("\nSelect sources (Enter = all, e.g. 1,3,5-7 or source keys):")
    w = max(len(k) for k in keys)
    for i, (key, plate, token) in enumerate(catalog, 1):
        need = "keyless" if token == "keyless" else f"needs {token}"
        print(f" {i:2}. {key:<{w}}  {plate:<34} {need}")
    while True:
        try:
            return parse_selection(ask("Sources", "all"), keys)
        except ValueError as e:
            print(f"  {e}")


def write_disable(plate: Path, disabled: list[str]) -> None:
    # Fresh template copy only: insert under the run: block, keep every comment.
    lines = plate.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.startswith("run:"):
            lines.insert(i + 1, f"  disable: [{', '.join(disabled)}]\n")
            break
    else:
        print("sources.template.yaml has no run: block — cannot record selection",
              file=sys.stderr)
        sys.exit(1)
    plate.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="tech-updates onboarding")
    ap.add_argument("--root", help="data root (skip the prompt)")
    ap.add_argument("--token", action="append", default=[], metavar="NAME=VALUE",
                    help="API key for state/tokens/NAME (repeatable)")
    ap.add_argument("--probe", dest="probe", action="store_true", default=None,
                    help="probe sources at the end (default: ask)")
    ap.add_argument("--no-probe", dest="probe", action="store_false",
                    help="skip the probe")
    ap.add_argument("--sources", help="source selection: all (default) | 1,3,5-7 | source keys")
    ap.add_argument("--non-interactive", action="store_true",
                    help="fail instead of prompting (use with --root)")
    args = ap.parse_args()

    def need(prompt: str, default: str = "") -> str:
        if args.non_interactive:
            print(f"non-interactive: no input for '{prompt}'", file=sys.stderr)
            sys.exit(2)
        return ask(prompt, default)

    print("=== tech-updates setup ===\n")

    # 1. Data root
    root = Path(args.root or need("Where should the data live?", str(Path.home() / "tech-updates-data"))).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    # 2. Scaffold — skip when the tree is already complete (idempotent re-runs)
    targets = [root / d for d in ("runs", "runs/sources", "findings")] + [
        root / f for f in ("README.md", "log.md", "watchlist.md")
    ]
    existing = [t for t in targets if t.exists()]
    if len(existing) == len(targets):
        print(f"\n— Data tree already scaffolded at {root}, skipping")
    else:
        print(f"\n— Scaffolding data tree at {root}")
        cmd = [sys.executable, str(INIT), "--root", str(root)]
        if existing:
            ans = need(
                f"{len(existing)}/{len(targets)} scaffold targets already exist at {root}; overwrite with --force? (y/n)", "n"
            )
            if not ans.lower().startswith("y"):
                print("Aborted — nothing written.")
                return 1
            cmd.append("--force")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            return r.returncode

    # 3. Source plate + picker (only when creating; an existing plate is never touched)
    catalog = load_catalog()  # needed by the picker AND the key prompts below
    plate = PKG / "sources.yaml"
    if plate.exists():
        print(f"\n— sources.yaml already exists, keeping it")
        print("  (to change which sources run, edit run.disable in it)")
    else:
        shutil.copy(TEMPLATE, plate)
        selected = pick_sources(catalog, args)
        write_disable(plate, [k for k, _, _ in catalog if k not in selected])
        print(f"\n— Created sources.yaml: {len(selected)}/{len(catalog)} sources enabled")
        n = plate.read_text(encoding="utf-8-sig").count("YOUR_")
        if n:
            print(f"  WARNING: {n} YOUR_* placeholders in sources.yaml — replace them")
            print("  with your own repos/keywords before the first real run")
            print("  (sources.example.yaml is the reference).")

    # 4. store.config.json
    cfg = SCRIPTS / "store.config.json"
    cfg_data = {
        "_comment": "Machine-local (never commit/share). Written by setup.py.",
        "tech_updates_root": str(root),
    }
    if cfg.exists():
        existing = json.loads(cfg.read_text(encoding="utf-8"))
        if existing.get("tech_updates_root") == str(root):
            print(f"— store.config.json already points at {root}")
        else:
            old = existing.get("tech_updates_root")
            new = need(f"store.config.json points at {old}; replace with {root}? (y/n)", "y")
            if new.lower().startswith("y"):
                cfg.write_text(json.dumps(cfg_data, indent=2) + "\n", encoding="utf-8")
    else:
        cfg.write_text(json.dumps(cfg_data, indent=2) + "\n", encoding="utf-8")
        print(f"— Wrote {cfg.relative_to(PKG)} -> {root}")

    # 5. API keys for SELECTED sources -> state/tokens/<NAME> (what optional_token() reads)
    plate_data = config.load_sources(root)
    disabled = set((plate_data.get("run") or {}).get("disable") or [])
    selected = [(k, tok) for k, _, tok in catalog if k not in disabled]
    needed = sorted({tok for _, tok in selected if tok != "keyless"})

    if not needed:
        print("\n— No API keys needed: every selected source is keyless.")
        print("  (to add a keyed source later: re-run setup.py, or set the key with")
        print("   python setup.py --token NAME=VALUE)")
    else:
        tokdir = PKG / "state" / "tokens"
        flags = dict(kv.split("=", 1) for kv in args.token if "=" in kv)
        missing = []
        for name in needed:
            if os.environ.get(name) or (tokdir / name).exists():
                print(f"— {name}: already set, skipping")
                continue
            val = flags.get(name, "") or ("" if args.non_interactive else ask_secret(name))
            if val:
                tokdir.mkdir(parents=True, exist_ok=True)
                (tokdir / name).write_text(val + "\n", encoding="utf-8")
                try:
                    os.chmod(tokdir / name, 0o600)
                except OSError:
                    pass  # non-POSIX fs: file still private to the user profile
                print(f"— stored state/tokens/{name}")
            else:
                missing.append(name)
        if missing:
            print(f"\n  WARNING: no key for {', '.join(missing)} — those sources will")
            print("  report 'unknown coverage' each run (never 'no news').")
            print("  Add later with:  python setup.py --token NAME=VALUE")

    # 6. Probe
    do_probe = args.probe if args.probe is not None else (
        False if args.non_interactive else ask("\nProbe all sources now? (y/n)", "y").lower().startswith("y")
    )
    if do_probe:
        print("\n— Probing (no store writes)…")
        r = subprocess.run([sys.executable, str(SCRIPTS / "collect.py"), "--probe"])
        if r.returncode != 0:
            print("\n  WARNING: probe could not reach ANY source — check your network")
            print("  and sources.yaml, then re-run: python scripts/collect.py --probe")

    print(
        "\n=== Setup complete ===\n"
        f"  data root : {root}\n"
        f"  first run : python scripts/collect.py\n"
        f"  schedule  : add 'python {PKG / 'scripts' / 'collect.py'}' to your crontab/agent-cron\n"
        "  curate    : after runs accumulate, curate findings/ from the run files\n"
        "  (full details: README.md)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
