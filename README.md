# Origami

Independent animation projects made with [Manim Community](https://www.manim.community/).

## Repository layout

```text
projects/
  ganesh_2026/          # Ganesh artwork, scene, assets, and verification tools
  india_railway_2026/   # Starter for the next animation
scripts/               # Shared environment setup
media/                 # Generated exports and caches (ignored by Git)
pyproject.toml          # Shared Python dependencies
uv.lock                # Reproducible dependency versions
```

Each project owns its scene, `manim.cfg`, and README. Store new input assets
inside the project's `assets/` directory, including any required licenses.
Render from the repository root so output paths resolve consistently.

## Setup

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
- [India Railway 2026](projects/india_railway_2026/README.md): prepared workspace
  for the next animation; content and storyboard are not yet defined.

Follow each project's README for its render command. Use its explicit config
to preserve the intended aspect ratio; for a portrait draft, override only
resolution with `-r 360,640` instead of a landscape quality preset.

Keep generated videos, stills, and caches under `media/<project_name>/`.
The shared `.venv/` is local tooling, not a project asset, and is also ignored.
