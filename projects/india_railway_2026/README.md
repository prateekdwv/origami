# India Railway 2026

Workspace for the next animation. The concept, storyboard, data, and visual
style will be defined in the next project brief.

## Structure

- `scene.py`: Manim entry point, `IndiaRailway2026`.
- `manim.cfg`: project-local render settings and output paths.
- `assets/`: source images, maps, data, audio, fonts, and accompanying licenses.

The starter inherits the repository's portrait format: 1080 × 1920 at 30 fps
with a warm white background. These are provisional defaults, not a final
creative direction. The scene currently renders one blank second solely to
confirm the project is wired up.

## Render

From the repository root, after `uv sync --locked`:

```bash
uv run manim --config_file projects/india_railway_2026/manim.cfg -o IndiaRailway_2026 projects/india_railway_2026/scene.py IndiaRailway2026
```

Output: `media/india_railway_2026/IndiaRailway_2026.mp4` (ignored by Git).

For a smaller draft:

```bash
uv run manim --config_file projects/india_railway_2026/manim.cfg -r 360,640 --media_dir media/india_railway_2026/draft -o IndiaRailway_2026 projects/india_railway_2026/scene.py IndiaRailway2026
```

Use the shared environment and add any future dependencies to the root
`pyproject.toml`; do not create a second virtual environment for this project.
