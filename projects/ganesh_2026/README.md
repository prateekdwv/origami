# Ganesh 2026

A 45-second continuous-line interpretation of the supplied Ganesh reference.
Black ink on subtly textured warm paper, 1080 × 1920, 30 fps, silent H.264 MP4.
The camera follows the ink tip at 3× magnification, then pulls back to reveal
the complete drawing. A fixed “श्री गणेशाय नमः” title sits at the top.

The drawing is one open SVG path, manually authored with 254 connected cubic
Bézier segments. The crown, ears, trunk, four arms, seated pose, and base follow
the reference. Smaller details are connected flourishes. Crossings are
intentional; the stroke never lifts or retraces a segment.
The lower hands use a raised blessing palm on the viewer's left and a cupped
palm on the viewer's right holding a small round laddu, with four fingers and
a thumb on each hand.

## Render

Run these commands from the repository root after `uv sync --locked`:

```bash
uv run manim --config_file projects/ganesh_2026/manim.cfg -o Ganesh_2026 projects/ganesh_2026/scene.py Ganesh2026
```

Outputs:

- `media/ganesh_2026/Ganesh_2026.mp4`
- `media/ganesh_2026/Ganesh_2026.png` — the actual final rendered frame

All generated files are ignored by Git. The explicit `-o` is needed because
Manim's command-line defaults override the output filename in a config file.
The project config keeps portrait settings separate from other projects.

For a faster 360 × 640 draft with the same timing and aspect ratio:

```bash
uv run manim --config_file projects/ganesh_2026/manim.cfg -r 360,640 --media_dir media/ganesh_2026/draft -o Ganesh_2026 projects/ganesh_2026/scene.py Ganesh2026
```

If the user cache directory is read-only, prefix `uv` commands with
`UV_CACHE_DIR=/tmp/origami-uv-cache`. You can also use `.venv/bin/manim` and
`.venv/bin/python` directly after synchronization, as in this workspace.

## Artwork and motion

Edit `ganesh.svg` as the source of truth. Keep one initial `M`, followed by
explicit `C` commands only, with no extra subpaths or closing command. Its
480 × 530 view box is proportionally fitted into an 820 × 1050-pixel box
with its forehead/crown axis centered at x=540 and its vertical layout centered
at y=900. The rendered line is four output pixels wide with
rounded caps and joins. There is no separate pen marker.

The route starts with the lower-left trailing line, climbs through the left
side and crown, weaves the facial and hand details into the trunk and torso,
and returns through the right leg to the base's lower-right endpoint.

The scene holds blank for 0.5 seconds, draws for 39 seconds, pulls back for
3 seconds, and holds the finished image for 2.5 seconds. A 256-sample-per-cubic arc-length table maps
elapsed time to distance. Manim reveals one continuous prefix of the original
curve; completed control points remain unchanged.

`motion.py` centralizes timing and camera parameters. The 3× camera covers
360 × 640 original-composition pixels; ink appears approximately 12 pixels
wide in the close-up and returns to 4 pixels in the full view. Tracking is
precomputed at 240 Hz. A 120 × 220-pixel safe box prevents camera-target
movement while the tip remains nearby. After the tip crosses an edge, the
target moves only enough to meet that edge, and a short exponential follow
smooths the rendered camera position. This keeps tight loops from making the
frame jitter. There is no rotation or separate pen marker. The Sanskrit title
is fixed at the top of the artwork canvas. The close-up crops it out; the
pullback reveals it with the finished artwork. It is not an animated stroke.
`NotoSansDevanagari-Regular.ttf` is bundled from the Noto Fonts project so the
title shapes consistently without relying on fonts installed on the host.
Its SIL Open Font License and copyright notice are included in `OFL.txt`.

At 39.5 seconds, drawing stops and a three-second pullback begins. Quintic
easing controls frame size; cubic Hermite interpolation matches the incoming
camera velocity and arrives at the original full composition at rest. The
final PNG is exported after this reveal.
After the pullback, the finished image holds for 2.5 seconds. There is no colored
tilak overlay. Light irregular shaded facets and faint fibers give the canvas
a visible crumpled-paper texture, rendered as lightweight vector geometry.

## Inspect and verify

```bash
uv run python projects/ganesh_2026/artwork.py
uv run python projects/ganesh_2026/verify.py
uv run python projects/ganesh_2026/audit_video.py media/ganesh_2026/Ganesh_2026.mp4
```

The first command renders a static Cairo proof directly from the SVG. The
tests check connectivity, bounds, duplicate/reversed curves, sustained
near-coincident runs, arc-length accuracy, and the connected prefix at every
animation frame. Camera checks cover tip visibility, transition continuity,
monotonic zoom-out, and the stationary final framing. Retracing detection is a sampled geometric check, supplemented
by visual inspection, rather than a symbolic proof.

The video audit checks all 1350 decoded frames against independently rasterized
source prefixes transformed by the expected camera pose, including the blank
opening, close-up tracking, pullback, and completed hold. It also
checks codec, timestamps, resolution, pixel format, and absence of audio, then
writes `verification.json` and a 12-frame `contact_sheet.png` beside the video.
