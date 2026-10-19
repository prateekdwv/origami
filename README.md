# Origami

Independent video projects using [Manim Community](https://www.manim.community/)
or Matplotlib/PyAV. Each project owns its artwork, assets, rendering commands and verification.
The repository shares one Python environment; it is not an application or an
installable Python package.

## Repository layout

```text
projects/
  ganesh_2026/          # Ganesh artwork, scene, assets, and verification tools
  india_railway_2026/   # Scheduled-video drawing, preparation, assets and tests/
scripts/               # Shared environment setup
media/                 # Generated exports and caches (ignored by Git)
pyproject.toml          # Shared Python dependencies
uv.lock                # Reproducible dependency versions
```

Each project owns its renderer, any configuration, and README. Store new input assets
inside the project's `assets/` directory, including any required licenses.
Render from the repository root so output paths resolve consistently.

## Setup

### Windows (PowerShell)

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

This is a one-time setup. It reuses tools already on PATH or installs uv and
FFmpeg/FFprobe under `%LOCALAPPDATA%\Programs\`, adding those directories to your
Windows **user PATH**. Python is managed by uv in your user account. Only Python
libraries (including Manim) live in this repository's ignored `.venv/`.
Native Python dependencies use wheels; `srt` is packaged from pure Python without
a compiler. No administrator access, WSL, data collection or rendering is required.
The execution policy override applies only to the setup process.

After setup, restart your terminal application (and VS Code if using its integrated
terminal) so it picks up the updated user PATH. Normal work needs no activation
or terminal setup scripts. From the repository root:

```powershell
uv sync --locked
# Then run the chosen project's command from its README.
```

The railway project bundles licensed Lato fonts and uses fixed IST timetable offsets.
Python 3.13 is pinned because the locked native dependencies provide Windows
wheels for it; Python 3.14 would require compiling some dependencies.
Its renderer does not need LaTeX. Projects using Manim `Tex`/`MathTex` also
require a working LaTeX installation and `dvisvgm` on PATH.

### Linux

The project uses [`uv`](https://docs.astral.sh/uv/) to create an isolated Python
environment and lock all Python dependencies.

On Debian or Ubuntu, install the native rendering and LaTeX dependencies once:

```bash
./scripts/install-system-deps.sh
```

Then install `uv` if needed and synchronize the project environment:

```bash
python3 -m pip install --user uv
uv sync --locked
```

Check that Manim and its external tools are available:

```bash
uv run manim checkhealth
```

## Projects

- [Ganesh 2026](projects/ganesh_2026/README.md): a 45-second portrait drawing
  made with one continuous stroke. Includes editable vector artwork, a
  project-specific render configuration, and frame-by-frame verification.
- [India Railway 2026](projects/india_railway_2026/README.md): nationwide passenger
  timetable collection and a scheduled-traffic preview for 15 October 2026 IST,
  including suburban/local trains. Uses the official Survey of India outline
  and mapped OSM tracks. Scheduled previews use Matplotlib/PyAV and run offline
  without an API key.

Follow each project's README for its render command. For Manim, use its explicit config
to preserve the intended aspect ratio; for a portrait draft, override only
resolution with `-r 360,640` instead of a landscape quality preset.

Keep generated videos, stills, and caches under `media/<project_name>/`.
Retained railway input snapshots live under its `assets/` directory.
The shared `.venv/` is local tooling, not a project asset, and is also ignored.
Tools and dependency download caches live outside `media/`; deleting generated
media does not remove your development environment.
