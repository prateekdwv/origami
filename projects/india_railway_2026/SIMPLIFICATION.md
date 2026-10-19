# Railway simplification results

Measured on this Windows laptop with Python 3.13, against commit `8890495`.
Code counts include the final-export option; benchmark timings describe the original simplification.

| Measurement | Before | After |
| --- | ---: | ---: |
| Production Python lines | 2,343 | 1,286 (45.1% fewer) |
| Production Python files | 17 | 11 |
| Drawing code, including moved helpers | 305 | 230 (24.6% fewer) |
| 150-frame composition + encoding, median | 43.9 s | 40.2 s (8.4% less time) |
| Renderer import + initialization, median | 9.8 s | 22.1 s |
| Benchmark peak working set, median | 1139 MiB | 1225 MiB |
| Cold movement preparation, one run | 34.0 s | 40.1 s |
| Unique libraries in the shared cross-platform lock | 43 | 49 |

Production counts exclude tests, documentation, assets and disposable benchmarks.
The drawing comparison includes the 52 lines moved into model/settings helpers.
It therefore credits removed code rather than moved code. Matplotlib passed both
selection gates: at least 20% less drawing code and no more than 10% slower rendering.

Each of three fresh-process trials composed the same 150 full-resolution frames
at video seconds 20 through 24.9667 and encoded them using the same PyAV/libx264
settings (30fps, medium, CRF23). Initialization and input loading are excluded from
that interval. This compares the drawing backends with a common encoder; it is
not a full-video comparison against the former Manim wrapper. Peak working set
includes loading, initialization and encoding. The candidate was benchmarked
before minor text alignment and shared-helper cleanup in the selected version.

The complete new export took **434.0 seconds** including cached
input validation, initialization, stills, encoding and sampled auditing. Composition
plus encoding accounted for **386.7 seconds**;
peak working set was **1262 MiB**. Cached preparation and
validation took **13.5 seconds**, without routing again.
The cold runs do not establish a preparation speed improvement. Presentation
changes now reuse mapped movements and do not rewrite an unchanged cache.

Matplotlib trades extra dependencies, startup time and memory for native paths,
collections, text and axes. Nine library names were added and three retired names
removed; all retained dependency versions stayed fixed. Manim remains installed
for Ganesh. Railway rendering uses one Matplotlib/Agg backend and direct PyAV
encoding; there is no backend registry or application framework.

All **45 tests passed**. Rebuilt journeys, categories, coordinates, movement
intervals, coverage and sampled activity match the baseline exactly: **9,763
journeys**, with an exact peak of **2,402**. Native font antialiasing and overlap
compositing produce small pixel differences. Midnight, morning, noon, evening and
final-hold stills were compared. The complete 1080x1920, 30fps, 60-second silent
H.264/yuv420p export passed metadata and **18-frame sampled pixel checks**;
this does not claim comparison of all 1,800 encoded frames.

Generated evidence, ignored by Git:

- [Detailed statistics](../../media/india_railway_2026/refactor-stats.json)
- [Raw benchmark trials](../../media/india_railway_2026/simplification/benchmark-results.json)
- [Before/after stills: old top row, new bottom row](../../media/india_railway_2026/simplification/comparison.png)
- [Video and audit](../../media/india_railway_2026/scheduled_test/2026-10-15/verification.json)
