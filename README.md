# Origami

Mathematical animations made with [Manim Community](https://www.manim.community/).

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
uv sync
```

Check that Manim and its external tools are available:

```bash
uv run manim checkhealth
```

## Rendering

Put scene files in the repository and render one by its class name. For example:

```bash
uv run manim -pql scenes/example.py ExampleScene
```

Use `-pqh` instead of `-pql` for a high-quality final render. Generated videos,
images, and intermediate files are written under `media/` and ignored by Git.

## Projects

- [Ganesh 2026](projects/ganesh_2026/README.md): a 45-second portrait drawing
  made with one continuous stroke. Includes editable vector artwork, a
  project-specific render configuration, and frame-by-frame verification.
