# JAVLibrary Sorter

A Windows desktop app that scans a folder of video files, identifies each one by its
content ID (e.g. `ABC-123`), fetches metadata for it, and organizes your library around
that metadata — with Kodi/Jellyfin/Plex-compatible `.nfo` files and cover art.

## What it does

1. **Scans** a source folder for video files.
2. **Extracts a content ID** from each filename, stripping the junk real-world files
   carry — site-tag prefixes (`hhd800.com@MIAB-369`), release-group suffixes
   (`MIDV-751-C_GG5`), and quality tags (`MIST-435.1080p`).
3. **Looks up metadata** (title, actresses, genres, studio, release date, cover art)
   from [r18.dev](https://r18.dev)'s JSON API, with a local SQLite cache so repeat
   scans don't re-fetch.
4. **Organizes** the file, in one of two modes:
   - **Sort in place** — the file stays in its folder but is renamed to its clean ID.
   - **Import into library** — the file is moved and renamed into `Library/<ID>/`.
5. **Writes an `.nfo`** and downloads cover art alongside the video.
6. **Builds category folders** — `Actress/`, `Genre/`, `Studio/`, `Year/` — each
   containing a **symlink** back to the canonical file, so a video with several
   actresses or genres appears under all of them without duplicating data.

## Genre blocklist

r18.dev mixes promotional and technical tags in with real genres — left alone you get
folders like `Sample Video`, `JET Video 40% Off Sale`, and
`Prestige Group Autumn Planning Festival` sitting next to the genres you actually
browse by. A built-in blocklist drops these, by exact name and by shape (anything
matching `40% off`, `sale`, `campaign`, `festival`, …).

Blocked tags are kept out of **both** the category folders and the NFO — a sale banner
is no more a genre in Jellyfin than it is on disk.

Edit it via **Blocked genres…** in the app. Your own additions are stored separately
from the built-in list, so future improvements to the built-in list still reach you.
The cache stores unfiltered metadata and the filter runs on read, so changing the
blocklist applies immediately — no need to clear the cache or re-scan.

## Requirements

- Windows
- Python 3.11+
- **Developer Mode or Administrator** — Windows only permits creating symlinks with
  elevated privileges or Developer Mode enabled
  (Settings → Privacy & security → For developers → Developer Mode).
  Without it, files are still sorted, renamed, and given an NFO + cover, but the
  category-folder links are skipped and reported — the app never silently substitutes
  a copy or hardlink.

## Setup

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Running

```bash
.venv\Scripts\python -m javsorter
```

Point **Source folder** at your unsorted videos, **Library folder** at where the
organized library should live, pick a sort mode and which category folders to build,
then **Scan** → review the table → **Run**.

Rows that don't resolve automatically (no ID parsed, an ambiguous `-C` marker, or no
match) can be **double-clicked** to correct the ID and look it up again.

**Stop** halts a scan or run after the item in progress finishes.

### Dry run — do this first

Tick **Dry run (preview only)** before your first real run. Run then prints exactly what
it *would* do — every move, rename, NFO, cover, and category link, plus warnings about
destination collisions and duplicates — and changes nothing at all. The preview shares
its destination logic with the real pipeline, so the two can't drift apart.

Start with a copy of a handful of real files, dry-run it, read the plan, then run for
real. And remember **Undo last run** exists if a real run goes somewhere unexpected.

### Undoing a run

Every run is journalled, so **Undo last run** reverses it: category links are removed,
generated NFO and cover files are deleted, and moved videos go back where they came
from. A partial or cancelled run is journalled too — that's exactly when undo matters
most.

Undo is deliberately conservative. A file that already existed before the run is never
recorded as created, so undo won't delete it (the old contents couldn't be restored
anyway), and if something new has appeared at a video's original location, that video
is left in the library and the conflict is reported rather than overwriting anything.

### Duplicates

Two files with the same ID but no `cd1`/`cd2` markers are competing copies, not discs
of one release — renaming both would collide. The largest is taken into the library and
the rest are **left exactly where they are** and reported in the Notes column, since
only you know which copy to keep.

### Logs

The log panel is mirrored to a rotating file at `%APPDATA%\JAVSorter\logs\javsorter.log`,
so a long run is still auditable after the window is closed.

## Rescanning an existing library

**Rescan library** brings an already-sorted library back in line with your current
settings and metadata. It:

- adds category folders you've since enabled, and removes ones you've turned off;
- drops genre folders that a changed blocklist now excludes;
- prunes links whose video has been deleted or moved away;
- writes any missing NFO and fetches any missing cover.

It **never moves or deletes a video** — only the library's own scaffolding. Releases it
can't find metadata for are left completely alone, links included, since without
metadata there's no way to tell a stale link from a good one. Links pointing outside the
library (as sort-in-place produces) are also left alone. Running it twice in a row
changes nothing the second time, and a rescan can be undone like any other run.

## Building a standalone .exe

```bash
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pyinstaller JAVLibrarySorter.spec
```

The result is `dist/JAVLibrarySorter/JAVLibrarySorter.exe`, a self-contained folder
(~126 MB) that runs without Python installed. Copy the whole `JAVLibrarySorter` folder,
not just the `.exe`.

It's a `onedir` build on purpose: `onefile` would unpack Qt to a temp folder on every
launch, which only makes startup slower. Developer Mode is still required on the target
machine for category-folder links.

## Development

```bash
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest          # offline suite
.venv\Scripts\python -m pytest -m live  # hits the real r18.dev API; run sparingly
```

The offline suite never touches the network: the scraper is tested against committed
JSON fixtures in `tests/fixtures/json/`, which double as the regression guard if
r18.dev's schema changes.

### Layout

| Package | Responsibility |
| --- | --- |
| `javsorter/core/` | Filename → content ID extraction, folder scanning, multi-part grouping |
| `javsorter/scraping/` | Rate-limited HTTP client, r18.dev lookup, JSON parsing, SQLite cache |
| `javsorter/organize/` | Move/rename, NFO writing, cover download, symlinks, run journal, pipeline |
| `javsorter/gui/` | PySide6 window, background workers, dialogs |
| `javsorter/config/` | JSON settings persistence in `%APPDATA%\JAVSorter\` |

`core`, `scraping`, and `organize` are free of Qt imports and take data in / return
data out, so they're testable without a GUI or a live network call.

## Notes on the metadata source

The project began targeting javlibrary.com (hence the name), but that site sits behind
a Cloudflare challenge that blocks automated requests. r18.dev exposes the same kind of
data as plain JSON with no bot protection, so it's used instead. Requests are
rate-limited with jitter and cached locally to stay polite.
