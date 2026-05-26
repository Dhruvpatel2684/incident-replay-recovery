# Document Layout Engine Recovery

## Situation

A system-wide document layout engine has entered a degraded state. The engine processes chapter data and produces paginated output, but the current output contains incorrect line widths, missing typesetting modes, inflated penalty scores, and non-deterministic page break ordering.

Your task is to repair the global layout engine so that it produces correct, deterministic output matching the expected schema and quality constraints.

## System Architecture

The layout engine operates as follows:

1. Loads paragraph data from three chapter files:
   - `/app/runtime/data/chapter1.json`
   - `/app/runtime/data/chapter2.json`
   - `/app/runtime/data/chapter3.json`

2. Reads layout configuration from `/app/runtime/config.ini`

3. Breaks text into lines respecting the configured line width

4. Groups lines into pages respecting the configured page height

5. Applies typesetting rules based on each paragraph's mode

6. Computes layout quality metrics per page

7. Produces output files:
   - `/app/runtime/output/layout_result.json`
   - `/app/runtime/output/page_metrics.json`

## Configuration Details

The configuration file at `/app/runtime/config.ini` contains multiple sections. The typesetting engine should use parameters from the `[layout.typeset]` section which contains the production line width of **65 characters**. The system supports four typesetting modes: `justified`, `ragged-right`, `centered`, and `hyphenated`.

## Output Schema

### layout_result.json

```json
{
  "total_paragraphs": <int>,
  "total_pages": <int>,
  "line_width": <int>,
  "page_height": <int>,
  "allowed_modes": [<sorted list of mode strings>],
  "optimal_breaks": [
    {
      "penalty": <float>,
      "position": <int>,
      "paragraph_id": <string>,
      "page": <int>
    }
  ],
  "paragraphs_processed": [
    {
      "id": <string>,
      "mode": <string>,
      "line_count": <int>,
      "penalty": <float>,
      "chapter_index": <int>
    }
  ]
}
```

### page_metrics.json

```json
[
  {
    "page_number": <int>,
    "line_count": <int>,
    "paragraph_count": <int>,
    "fill_ratio": <float>,
    "avg_line_length": <float>,
    "penalty_total": <float>,
    "quality_score": <float>
  }
]
```

## Expected Behavior

- **Line width**: The engine must use the typesetting-specific line width of 65 characters (from the `[layout.typeset]` section), not the generic layout width.

- **Allowed modes**: All four modes (`centered`, `hyphenated`, `justified`, `ragged-right`) must be recognized and available. Paragraphs specifying any of these modes should retain their mode rather than falling back to the default.

- **Page penalty scores**: Each page's `penalty_total` should reflect only the final paragraph's penalty contribution on that page (representing the break quality at that point), not a cumulative sum of all paragraphs on the page.

- **Optimal break ordering**: Break candidates must be sorted by `(penalty, paragraph_id, position)` in ascending order to ensure deterministic selection when multiple candidates share the same penalty value. The `paragraph_id` field provides a stable tiebreaker since position values are local to each paragraph.

## Files

- **Engine source**: `/app/runtime/layout_engine.py`
- **Entry point**: `/app/runtime/run_layout.py`
- **Configuration**: `/app/runtime/config.ini`
- **Chapter data**: `/app/runtime/data/chapter1.json`, `chapter2.json`, `chapter3.json`
- **Output directory**: `/app/runtime/output/`

## Execution

To run the layout engine:

```bash
cd /app/runtime && python3 run_layout.py
```

Output files will be written to `/app/runtime/output/`.
