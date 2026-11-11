# Tech Updates Store

Curated technology-trend capture: raw runs -> deduped sources -> findings.

## Flow

1. **runs/** — raw capture, one file per run. Ephemeral: never edit after the
   run finishes.
2. **runs/sources/** — deduped survivors with provenance (one file per item,
   linking back to its run file).
3. **findings/** — curated output distilled from sources. This is the only
   layer meant for human reading.

## Rules

- **Coverage-gap rule:** if a topic area has no signal for more than two
  consecutive runs, record it under "Coverage gaps" in `watchlist.md` rather
  than inventing filler.
- **Placement rules:**
  - Raw capture goes ONLY in `runs/`.
  - A deduped item that appears in `runs/sources/` must cite its run file.
  - A finding must cite the source files it was distilled from. No orphan
    findings.
- **Log rule:** `log.md` is append-only. Never edit or delete past entries;
  add corrections as new entries.

## Files

- `log.md` — append-only run log.
- `watchlist.md` — curated signals, coverage gaps, next watch items.
