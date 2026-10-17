# India Railway 2026

An offline, representative passenger-journey replay of **10 October 2026,
00:00–24:00 IST**. It is not a national traffic census, live tracker, or timetable
simulation. Recorded station events constrain movement along cached track
geometry; positions between those events are interpolated.

## Structure

- `railway.py`: explicit collection, preparation, proof, render and verification commands.
- `acquire.py`, `store.py`: bounded HTTP acquisition and atomic, resumable cache.
- `model.py`: observation merging, station-to-track matching and movement intervals.
- `geography.py`, `assets/soi/`: official boundary, native projection and provenance.
- `fetch_tracks.py`, `prepare_tracks.py`, `tracks.py`, `assets/railways/`: attributed mapped track geometry.
- `design.py`, `scene.py`, `manim.cfg`: deterministic portrait composition and Manim scene.
- `replay.py`, `offline.py`: integrity checks, export audit and network denial.
- `test_railway.py`, `test_render.py`: isolated synthetic tests, never production observations.
- `data/` (ignored): manifest, versioned raw responses, coverage report and frozen replay.
- `../../media/india_railway_2026/` (ignored): generated proof, videos, stills and audit reports.

## Setup and collection

From the repository root, run `uv sync --locked`. The shared environment adds
PyShp for the official shapefile and PyProj for its geographic projection.
FFmpeg, Cairo and fonts are provided by the repository's system setup script.
The renderer also bundles Lato Regular/Bold in `assets/fonts/` under the included
SIL Open Font License, so typography works on Windows. Windows installs include
`tzdata` for the IST timezone; FFmpeg and FFprobe must be on `PATH`.

Create a free RailRadar account and configure `RAILRADAR_API_KEY` in the shell
or your workspace's secret manager. Do not paste the key into source, chat,
command arguments or tracked files. A local `.env` is ignored but is **not**
automatically loaded. The following Bash prompt avoids shell-history exposure:

```bash
read -rsp 'RailRadar API key: ' RAILRADAR_API_KEY
export RAILRADAR_API_KEY
```

Check your account dashboard first. `--remaining-quota` means the **current
remaining monthly account allowance**, including any use outside this project;
100 below is an example for an unused account, not an assumption about yours.
The collector leaves ten requests in reserve and honors any lower limit.

Initial pass, **during 10 October IST**:

```bash
uv run python projects/india_railway_2026/railway.py collect initial --remaining-quota 100
uv run python projects/india_railway_2026/railway.py status
```

Completion pass, **11 October 00:30 IST / 10 October 19:00 UTC or later**:

```bash
# Replace 60 with the account's remaining allowance at completion time.
uv run python projects/india_railway_2026/railway.py collect completion --remaining-quota 60
uv run python projects/india_railway_2026/railway.py prepare
```

These are manual, explicit commands. No timer, cron job or background polling is
installed. Reporting may still be incomplete at 00:30. Completion ends the
second pass even if individual requests fail; those gaps remain. No third pass
or automatic retries are scheduled. Preparation is prohibited before completion.

The train directory is fetched once. A deterministic shortlist seeks four
journey instances in each of six categories and geographic variety, using names
and region hints, not punctuality. Some long-distance origin dates are 9 October
or 8 October. These are candidates, not claims that each service operated or
overlapped the target day. Actual dated responses must confirm that. Unsupported
categories may remain absent, and coverage may be below 24 journeys.

Up to three dated live probes must establish actual timings in the target day
before broad acquisition proceeds. The first pass uses at most 40 requests;
completion at most 50; combined at most 90. Every attempt is recorded before
sending, including failures, probes and interrupted requests. Requests are at
least seven seconds apart. Successful responses are saved immediately with
parameters and retrieval times. Incomplete live records get one completion
update; successful directory/geometry records are reused. Known actuals survive
null fields in later responses. Per-pass failures are not automatically retried.

Re-run the same command to resume an interruption. Successful requests are not
duplicated. An uncertain in-flight attempt without a saved response is not
repeated in that pass. A saved response whose manifest update was interrupted is
recovered. A process lock prevents two collectors sharing this cache. A budget
stop ends the bounded pass with pending records once the feasibility gate passes.
Authentication/429 failures persist a halt; resolve the account condition and
review the manifest before deliberately clearing that halt. Do not delete the
cache to reset budgets. A failed history gate stops acquisition entirely for
manual review; it does not switch to schedules.

### Diagnosing a directory HTTP failure

If the first directory request failed with an HTTP error, normal collection will
not repeat it. To explicitly make one diagnostic retry, preserving the failed
record and counting the new request against the same limits:

```bash
# Supply the current remaining allowance from your dashboard.
uv run python projects/india_railway_2026/railway.py diagnose-directory --remaining-quota 99
```

Bearer authentication is the default. To explicitly test RailRadar's documented
alternative authentication in PowerShell, set `$env:RAILRADAR_AUTH_MODE = "api-key"`
before the diagnostic command. The same setting applies to later collection in
that terminal. No automatic authentication fallback or extra request is made;
the selected mode is recorded without the key.

This prints the HTTP status and bounded, redacted JSON error code/message. It
never prints authorization headers or saves raw error bodies. Successful
responses are cached for the next normal collection command. It does not clear
account halts, reset budgets, or retry train probes. An earlier error message
that was discarded cannot be recovered without a new request.

## Preparation and movement semantics

Only timezone-aware `actualArrival` and `actualDeparture` events are eligible.
Future observations, scheduled/predicted fields, wrong origin dates and records
marked unobserved are rejected. Operational exceptions are conservatively
excluded pending manual route review. Route geometry must belong to the same
train. Stations must align with the ordered line within 2.5 km; timetable
distances can disambiguate revisited stations but never supply movement times.
Invalid or implausibly fast segments (>350 km/h) are gaps, not extrapolated.

Travel requires the current stop's actual departure and the next stop's actual
arrival. Dwell requires actual arrival and departure at the same stop. Both are
clipped to the target day. The next observation may be after midnight; without
it, the unresolved final travel segment is omitted. Nothing is inferred between
non-adjacent observed stops. Counters include evidenced station stops and count
only currently displayed sample journeys; missing intervals are not counted.

Preparation produces `coverage.json`, then freezes `prepared.json` and source
hashes. Repeated preparation checks and reuses the frozen dataset; collection
will no longer modify it. Rendering and verification validate those hashes.
Keep the acquisition cache if you want to reproduce the export.

## Official map and publication restrictions

The bundled [Survey of India outline](https://surveyofindia.gov.in/pages/outline-maps-of-india)
retains all 629,724 points and 1,151 rings without simplification, including both
island groups. All routes, stations and approximate city-label anchors share its
native WGS84 Lambert Conformal Conic projection. The national outline was
visually checked against the [13th-edition 2026 political map](https://surveyofindia.gov.in/UserFiles/files/POL_MAP_4M_ENGLISH_13thEdn2026%281%29.pdf);
this is not survey-grade equivalence between different map scales. Attribution,
download hashes and review scope are in `assets/soi/provenance.json`.

**Noncommercial only under the supplied SOI notice.** Read the bundled
`assets/soi/usage-notice.pdf` before publishing. Monetized or sponsored Reels
must not be assumed permitted. SOI retains its copyright; no broader license is
asserted. RailRadar data/API redistribution rights also need review before
publicly sharing raw responses. They are ignored by Git.

## Proof, render and verification

### Populated synthetic preview (no API key)

To preview the visual design before collecting real observations:

```bash
# Busy 60-second test video, including poster and contact sheet:
uv run python projects/india_railway_2026/test_render.py --draft
# Same invented day at 1080 × 1920:
uv run python projects/india_railway_2026/test_render.py
# Images only, without waiting for video encoding:
uv run python projects/india_railway_2026/test_render.py --draft --stills-only
```

Open `media/india_railway_2026/synthetic_test/draft/SYNTHETIC_TEST.mp4`
(or `full/SYNTHETIC_TEST.mp4`). Each directory also contains
`IndiaRailway_2026_poster.png`, `contact_sheet.png` and `preview_dataset.json`.
The demo uses a national OpenStreetMap railway layer fetched from Esri India's
public OSM Railway Network service: 97,900 source features, split into 97,944
line parts. These are geographic track coordinates, projected through the same
native Lambert Conformal Conic transform as the SOI boundary. The source does
not supply its snapshot date, so October 2026 completeness is not asserted.

The full network appears as subdued background lines. Simulated services follow
108 mapped city-pair paths across all six categories. Paths use connected track
vertices, rounded to about one metre to reunite administrative splits. No larger
network gaps are bridged. Approximate city anchors snap within 15 km; unavailable
connections or excessive detours are omitted. Display paths are simplified to
150 metres (well below one pixel at this map scale), retaining track distances.
These shortest paths are demonstration itineraries, not verified named-train routes.

**Journey identities, timings and stops remain invented.** The map labels this
as simulated traffic on mapped tracks. It is a visual stress test, not a traffic
census, timetable, or replay of recorded observations. Nothing is written to
`data/`, no RailRadar API is used, and the production loader rejects demo datasets.

`assets/railways/` contains the compressed source GeoJSON, derived geometry,
source/hash/method provenance and the ODbL license. Exports credit OpenStreetMap
contributors. The railway database is under ODbL; the existing SOI boundary
notice still applies. Rendering uses only these frozen local files.

To explicitly refresh geometry (network access is confined to the fetch command):

```bash
uv run python projects/india_railway_2026/fetch_tracks.py
uv run python projects/india_railway_2026/prepare_tracks.py media/india_railway_2026/tooling/railways.geojson
```

Review the resulting provenance, omitted paths, national extent, and stills before
rendering. Geometry hashes are checked during rendering and frame verification.

The new palette uses warm paper, pale sage land, dark labels, visible grey-green
tracks and richer category colours. Markers and trails are larger for phone
viewing. Both real rendering and the synthetic preview share this visual style.
On slower machines, use `--render-only`, then `--verify-only` as separate runs.
If a runner limits job duration, audit using `--audit-part 0`, `--audit-part 1`,
and `--audit-part 2`, then `--merge-audits` (add `--draft` for the smaller video).
The merge checks video/dataset hashes and complete, non-overlapping frame coverage
before marking the full audit passed.

### Real-data rendering and empty map proof

The proof works immediately without a key or train data and is conspicuously
labeled as awaiting observations. It contains no invented trains or rail lines.

```bash
uv run python projects/india_railway_2026/railway.py proof
uv run python projects/india_railway_2026/railway.py render --draft
uv run python projects/india_railway_2026/railway.py render
uv run python projects/india_railway_2026/railway.py verify
```

`render` requires the frozen dataset. It invokes `IndiaRailway2026` with the
project-local Manim config and automatically exports and audits the result.
The frame compositor is rasterized through Manim's Cairo scene; the static
boundary is rasterized once, while markers/HUD are recomposed per frame. A
project-local pixel-aligned camera copies the prepared frame without a redundant
perspective warp. Drafts use Lanczos downsampling before that copy.
Python socket/DNS access is disabled in preparation, proof, scene and verification.
All subprocess inputs are local; no API module is called by rendering.

Outputs: `IndiaRailway_2026.mp4`, `IndiaRailway_2026_poster.png` (peak sampled
activity), `IndiaRailway_2026_final.png`, `contact_sheet.png`, `verification.json`.
Drafts go in `media/india_railway_2026/draft/`; all outputs are Git-ignored.

Final video: **1080 × 1920, 30 fps, 1,800 frames, 60 seconds**, silent H.264/
yuv420p. Seconds 0–3 introduce the map; 3–57 advance uniformly through the day;
57–60 hold 24:00 and the daily summary. The complete activity chart is shown
as context, with its cursor following the clock. Only the moving markers
represent current observed trains. All eighteen city labels remain fixed.

The audit checks encoded metadata, decodes every frame, compares map/HUD and
marker patches against the model, and checks the stationary final hold. Pixel
thresholds allow encoding/resampling error. This cannot certify upstream data
truth or replace a visual review of route alignment and readable labels.

```bash
uv run python -m unittest discover -s projects/india_railway_2026 -p 'test_*.py' -v
# Optional: 60-second synthetic renderer/audit tests, clearly watermarked.
uv run python projects/india_railway_2026/test_render.py --draft
uv run python projects/india_railway_2026/test_render.py
```

Synthetic exports stay under `media/india_railway_2026/synthetic_test/`, never
`data/`, and are not deliverable train replays. Tests cover cache recovery,
two-pass versioning, quotas, midnight boundaries, station dwell, missing
observations, rejected predictions, diversions, repeated stations and map extent.

API contracts: [dated live status](https://railradar.in/docs/live-train-status),
[track geometry](https://railradar.in/docs/train-route-geometry),
[train directory](https://railradar.in/docs/train-lookup). A documented journey
date parameter does not guarantee historical retention or local-train coverage.
