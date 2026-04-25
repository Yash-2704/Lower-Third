# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Module identity

`lower_third` is a CPU-only broadcast graphics generator. Natural-language prompt → LLM-emitted MotionIR → deterministic corrections → Cairo/Pango raster frames → FFmpeg VP9-RGBA WebM with alpha. No GPU, no model downloads. LLM is Groq `llama-3.3-70b-versatile` (primary) with Ollama `qwen2.5:7b` fallback.

## Environment

Imports use the absolute prefix `lower_third.*`, so the **parent** of this directory must be on `PYTHONPATH`. On macOS, `cairocffi` also needs Homebrew's `libcairo` on `DYLD_LIBRARY_PATH`. Both are wired by `activate_dev.sh`:

```bash
source activate_dev.sh        # venv + DYLD_LIBRARY_PATH + PYTHONPATH + .env
```

`.env` must define `GROQ_API_KEY` (and optionally `OLLAMA_BASE_URL`).

## Common commands

```bash
# Run all tests (251+ passing, ~19 skipped)
python3 -m pytest lower_third/tests/ -q

# Run a single test file or test
python3 -m pytest lower_third/tests/test_geometry_corrector.py -q
python3 -m pytest lower_third/tests/test_geometry_corrector.py::test_badge_text_line1_y_corrected -v

# Backend API (FastAPI on :8001, hot-reload)
python3 -m lower_third.api          # or: uvicorn lower_third.api:app --reload --port 8001

# Frontend (Vite on :5173)
cd lower_third/frontend && npm run dev
cd lower_third/frontend && npm test         # vitest
```

Tests must be run from the **repo root** (`/Users/yashaggarwal/Desktop/CC-Modules`) so `lower_third` resolves as a package. `cd lower_third && pytest` will fail with import errors.

## Pipeline architecture

`pipeline.py::generate_lower_third` is the orchestrator. The order matters; do not reshuffle without understanding why:

1. **`choreography/brand_resolver.py`** — runs *before* the LLM. Computes the single source of truth for canvas geometry (canvas 1920×1080, `bar_y=944`, `label_row_h=56`, `ticker_row_h=80`, circle `cx=60 cy=1012 rx=ry=60`). Every later stage reads these from `ResolvedBrand`. If you add a new geometric constant, put it here.
2. **`parser/llm_parser.py`** + `system_prompt.txt` — prompts the LLM with brand values interpolated in, parses into `LowerThirdSpec` (Pydantic) via the `instructor` library.
3. **`motion/geometry_corrector.py::apply_geometric_corrections`** — deterministic guardrails over the LLM's MotionIR. The LLM is unreliable about pixel-exact placement, so this stage *enforces* invariants (circle position, badge text position, label text vertical centring, ticker row y, scroll bar fill/position, draw order rect→path→text, timing consistency, loop sentinels). Each fix is a separate `_fix_*` function called in sequence; new corrections add a `_fix_*` and one line in `apply_geometric_corrections`.
4. **`motion/shape_resolver.py`** — runs *after* corrections so corrected `shape_intent` produces correct path `d`.
5. **`motion/ticker_corrector.py`** — sets ticker keyframe x-distances from measured text width.
6. **`motion/interpolation_engine.py::InterpolationEngine`** — per-frame state. Builds a plain `dict` from `ElementDef` for the renderer. **When you add a new field to `ElementDef`, you must also add it to the dict in `get_frame()`** — otherwise the renderer silently sees the default. (This was the root cause of the `text_align` regression.)
7. **`renderer/cairo_renderer.py`** — Cairo + Pango raster. For text, `move_to(x, y)` treats `(x, y)` as the **layout top-left**, not baseline. Vertical-centring math must account for Pango's ascent and cap-height — see the formula in `_fix_label_text_position`.
8. **`renderer/ffmpeg_encoder.py`** — VP9 RGBA WebM (alpha channel preserved for compositing).
9. **`cache/template_cache.py`** — content-addressed cache keyed on `PIPELINE_VERSION + spec_json`. **Bump `PIPELINE_VERSION`** in `template_cache.py:9` whenever pipeline behaviour changes; otherwise cached renders mask your fix.
10. **`qc/validator.py`** — frame-diff and encoding QC; warnings only, never blocks.

## MotionIR conventions

`motion/motion_ir.py` defines `ElementDef`, `AnimationTrack`, `Keyframe`, `MotionIR`. All Pydantic v2.

- **Never mutate** `ElementDef` or `MotionIR` in place. Use `model_copy(update={...})` and rebuild the elements list. The corrector tests check object identity assumptions.
- `text_align` defaults to `"left"`. Centring requires both `text_align="center"` AND a positive `w` (Pango uses `w` as layout width to centre within).
- `clip_to` references another element's `id`; the renderer clips to that element's bounding box.
- Path elements need either `shape_intent` (preferred — shape_resolver expands to `d`) or a literal `d`.

## Geometry corrector philosophy

The corrector owns canonical positions. The LLM owns *design choices* (colour, font_size, text content). Hard rule from session feedback: **do not enforce font_size in the corrector** — it is a design choice. Position, draw order, clip targets, and circle geometry are corrector-owned and may be overwritten regardless of LLM output.

When adding a new correction, follow the existing pattern:
- Identify elements by id substring or structural signal (clip_to, x-range), not by y-coordinate alone (the LLM gets y wrong constantly).
- Log at INFO with `"X corrected: %d → %d"` so failures are visible in `python3 -m lower_third.api` output.
- Use `model_copy`; preserve element order.
- Add to `apply_geometric_corrections` in the right spot — corrections that depend on circle position must run *after* `_fix_circle_badge_position`; corrections that need the ticker row in place must run *after* `_fix_ticker_row_position`.

## Cache invalidation gotcha

If a corrector or renderer change does not appear in re-rendered output, you forgot to bump `PIPELINE_VERSION`. The cache key includes the version string, so a bump invalidates all prior renders.
