#!/usr/bin/env python3
"""setup.py — interactive onboarding for the tech-updates package (typer + rich).

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

Maintenance (one-shot, no prompts, exits immediately — no re-setup):
  python setup.py --token PRODUCTHUNT_TOKEN=...   # store/replace one key
  python setup.py --probe                         # health-check selected sources

Everything except tokens is re-runnable: existing files are never overwritten;
missing keys are re-prompted.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

PKG = Path(__file__).resolve().parent
SCRIPTS = PKG / "scripts"
INIT = SCRIPTS / "init_store.py"
TEMPLATE = PKG / "sources.template.yaml"

sys.path.insert(0, str(SCRIPTS))
import config  # shared plate parser — same one collect.py uses

app = typer.Typer(add_completion=False, no_args_is_help=False,
                  context_settings={"help_option_names": ["-h", "--help"]})
console = Console()
err = Console(stderr=True)


def ask(prompt: str, default: str = "") -> str:
    return Prompt.ask(f"[cyan]{prompt}[/cyan]", default=default).strip()


def ask_secret(prompt: str) -> str:
    return Prompt.ask(f"[cyan]{prompt}[/cyan] (input hidden, empty to skip)",
                      password=True).strip()


def load_catalog() -> list[tuple[str, str, str]]:
    """(runner key, plate entry, token) rows from collect.py --list-sources."""
    r = subprocess.run([sys.executable, str(SCRIPTS / "collect.py"), "--list-sources"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        err.print(Panel(f"collect.py --list-sources failed:\n{r.stderr}",
                        title="error", border_style="red"))
        raise typer.Exit(1)
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


def show_source_table(catalog: list[tuple[str, str, str]]) -> None:
    table = Table(title="Source picker", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("key", style="cyan")
    table.add_column("entry")
    table.add_column("key needed", style="magenta")
    for i, (key, plate, token) in enumerate(catalog, 1):
        need = "keyless" if token == "keyless" else token
        table.add_row(str(i), key, plate, need)
    console.print(table)
    console.print("Select sources (Enter = all, e.g. 1,3,5-7 or source keys)")


def pick_sources(catalog: list[tuple[str, str, str]], sources: str | None) -> set[str]:
    keys = [k for k, _, _ in catalog]
    if sources:
        try:
            return parse_selection(sources, keys)
        except ValueError as e:
            err.print(f"[red]--sources: {e}[/red]")
            raise typer.Exit(2)
    show_source_table(catalog)
    while True:
        try:
            return parse_selection(ask("Sources", "all"), keys)
        except ValueError as e:
            console.print(f"  [red]{e}[/red]")


def save_token(name: str, value: str) -> None:
    tokdir = PKG / "state" / "tokens"
    tokdir.mkdir(parents=True, exist_ok=True)
    p = tokdir / name
    p.write_text(value + "\n", encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass  # non-POSIX fs: file still private to the user profile
    console.print(f"— stored state/tokens/{name}")


def write_disable(plate: Path, disabled: list[str]) -> None:
    # Fresh template copy only: insert under the run: block, keep every comment.
    lines = plate.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.startswith("run:"):
            lines.insert(i + 1, f"  disable: [{', '.join(disabled)}]\n")
            break
    else:
        err.print("[red]sources.template.yaml has no run: block — cannot record selection[/red]")
        raise typer.Exit(1)
    plate.write_text("".join(lines), encoding="utf-8")


def run_probe() -> int:
    console.print("\n— Probing (no store writes)…")
    return subprocess.run([sys.executable, str(SCRIPTS / "collect.py"), "--probe"]).returncode


@app.command()
def main(
    root: Optional[Path] = typer.Option(None, "--root", help="data root (skip the prompt)"),
    token: List[str] = typer.Option([], "--token", metavar="NAME=VALUE",
                                    help="API key for state/tokens/NAME (repeatable)"),
    probe: Optional[bool] = typer.Option(None, "--probe/--no-probe",
                                         help="probe sources at the end (default: ask)"),
    sources: Optional[str] = typer.Option(None, "--sources",
                                          help="source selection: all (default) | 1,3,5-7 | source keys"),
    non_interactive: bool = typer.Option(False, "--non-interactive",
                                         help="fail instead of prompting (use with --root)"),
) -> None:
    """tech-updates onboarding."""
    # Maintenance shortcuts: --token and/or --probe with no setup flags do only
    # that and exit — never re-run onboarding. (--root/--sources still mean setup.)
    if (token or probe is not None) and not (root or sources):
        bad = [t for t in token if "=" not in t]
        if bad:
            err.print(f"[red]--token wants NAME=VALUE, got: {bad[0]}[/red]")
            raise typer.Exit(2)
        for kv in token:
            name, _, val = kv.partition("=")
            save_token(name, val)
        if probe:
            if not (PKG / "sources.yaml").exists():
                err.print("[red]sources.yaml missing — run `python setup.py` once first[/red]")
                raise typer.Exit(2)
            raise typer.Exit(run_probe())
        raise typer.Exit(0)

    def need(prompt: str, default: str = "") -> str:
        if non_interactive:
            err.print(f"[red]non-interactive: no input for '{prompt}'[/red]")
            raise typer.Exit(2)
        return ask(prompt, default)

    console.print(Panel("tech-updates setup", style="cyan"))

    # 1. Data root
    root_path = Path(root or need("Where should the data live?",
                                  str(Path.home() / "tech-updates-data"))).expanduser()
    root_path.mkdir(parents=True, exist_ok=True)

    # 2. Scaffold — skip when the tree is already complete (idempotent re-runs)
    targets = [root_path / d for d in ("runs", "runs/sources", "findings")] + [
        root_path / f for f in ("README.md", "log.md", "watchlist.md")
    ]
    existing = [t for t in targets if t.exists()]
    if len(existing) == len(targets):
        console.print(f"\n— Data tree already scaffolded at {root_path}, skipping")
    else:
        console.print(f"\n— Scaffolding data tree at {root_path}")
        cmd = [sys.executable, str(INIT), "--root", str(root_path)]
        if existing:
            if non_interactive or not Confirm.ask(
                f"{len(existing)}/{len(targets)} scaffold targets already exist at {root_path};"
                " overwrite with --force?", default=False
            ):
                if not non_interactive:
                    console.print("Aborted — nothing written.")
                    raise typer.Exit(1)
                err.print("[red]non-interactive: no input for scaffold overwrite prompt[/red]")
                raise typer.Exit(2)
            cmd.append("--force")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise typer.Exit(r.returncode)

    # 3. Source plate + picker (only when creating; an existing plate is never touched)
    catalog = load_catalog()  # needed by the picker AND the key prompts below
    plate = PKG / "sources.yaml"
    if plate.exists():
        console.print("\n— sources.yaml already exists, keeping it")
        console.print("  (to change which sources run, edit run.disable in it)")
    else:
        shutil.copy(TEMPLATE, plate)
        selected = pick_sources(catalog, sources)
        write_disable(plate, [k for k, _, _ in catalog if k not in selected])
        console.print(f"\n— Created sources.yaml: {len(selected)}/{len(catalog)} sources enabled")
        n = plate.read_text(encoding="utf-8-sig").count("YOUR_")
        if n:
            console.print(f"  [yellow]WARNING: {n} YOUR_* placeholders in sources.yaml — replace them[/yellow]")
            console.print("  with your own repos/keywords before the first real run")
            console.print("  (sources.example.yaml is the reference).")

    # 4. store.config.json
    cfg = SCRIPTS / "store.config.json"
    cfg_data = {
        "_comment": "Machine-local (never commit/share). Written by setup.py.",
        "tech_updates_root": str(root_path),
    }
    if cfg.exists():
        existing_cfg = json.loads(cfg.read_text(encoding="utf-8"))
        if existing_cfg.get("tech_updates_root") == str(root_path):
            console.print(f"— store.config.json already points at {root_path}")
        else:
            old = existing_cfg.get("tech_updates_root")
            replace = Confirm.ask(
                f"store.config.json points at {old}; replace with {root_path}?", default=True
            ) if not non_interactive else False
            if not replace:
                if non_interactive:
                    err.print("[red]non-interactive: store.config.json points elsewhere "
                              f"({old}); run interactively to confirm the change[/red]")
                raise typer.Exit(2)
            cfg.write_text(json.dumps(cfg_data, indent=2) + "\n", encoding="utf-8")
    else:
        cfg.write_text(json.dumps(cfg_data, indent=2) + "\n", encoding="utf-8")
        console.print(f"— Wrote {cfg.relative_to(PKG)} -> {root_path}")

    # 5. API keys for SELECTED sources -> state/tokens/<NAME> (what optional_token() reads)
    tokdir = PKG / "state" / "tokens"
    plate_data = config.load_sources(root_path)
    disabled = set((plate_data.get("run") or {}).get("disable") or [])
    selected_pairs = [(k, tok) for k, _, tok in catalog if k not in disabled]
    needed = sorted({tok for _, tok in selected_pairs if tok != "keyless"})

    if not needed:
        console.print("\n— No API keys needed: every selected source is keyless.")
        console.print("  (to add a keyed source later: re-run setup.py, or set the key with")
        console.print("   python setup.py --token NAME=VALUE)")
    else:
        flags = dict(kv.split("=", 1) for kv in token if "=" in kv)
        missing = []
        for name in needed:
            if os.environ.get(name) or (tokdir / name).exists():
                console.print(f"— {name}: already set, skipping")
                continue
            val = flags.get(name, "") or ("" if non_interactive else ask_secret(name))
            if val:
                save_token(name, val)
            else:
                missing.append(name)
        if missing:
            console.print(f"\n  [yellow]WARNING: no key for {', '.join(missing)} — those sources will[/yellow]")
            console.print("  report 'unknown coverage' each run (never 'no news').")
            console.print("  Add later with:  python setup.py --token NAME=VALUE")

    # 6. Probe
    do_probe = probe if probe is not None else (
        False if non_interactive else Confirm.ask("\nProbe all sources now?", default=True)
    )
    if do_probe:
        rc = run_probe()
        if rc != 0:
            console.print("\n  [yellow]WARNING: probe could not reach ANY source — check your network[/yellow]")
            console.print("  and sources.yaml, then re-run: python scripts/collect.py --probe")

    console.print(Panel(
        f"data root : {root_path}\n"
        f"first run : python scripts/collect.py\n"
        f"schedule  : add 'python {PKG / 'scripts' / 'collect.py'}' to your crontab/agent-cron\n"
        "curate    : after runs accumulate, curate findings/ from the run files\n"
        "(full details: README.md)",
        title="Setup complete", border_style="green",
    ))


if __name__ == "__main__":
    app()
