#!/usr/bin/env python3
"""
Oracle repair script for the document layout engine.

Patches all four bugs in layout_engine.py:
1. Config space in comma-split list (allowed_modes parsing)
2. Wrong config section name (line_width from wrong section)
3. Penalty accumulation (should be last-write-wins per page)
4. Sort tiebreaker (missing paragraph_id in sort key)
"""

import re


def repair():
    engine_path = "/app/runtime/layout_engine.py"

    with open(engine_path, 'r') as f:
        content = f.read()

    # Bug 1: Fix allowed_modes parsing - strip whitespace from split items
    content = content.replace(
        'self._allowed_modes = set(raw_modes.split(","))',
        'self._allowed_modes = set(item.strip() for item in raw_modes.split(","))'
    )

    # Bug 2: Fix config section - use layout.typeset instead of layout
    content = content.replace(
        'self.line_width = self.config.getint("layout", "line_width")',
        'self.line_width = self.config.getint("layout.typeset", "line_width")'
    )

    # Bug 3: Fix penalty accumulation - use assignment instead of +=
    content = content.replace(
        'current_page.penalty_total += paragraph.penalty',
        'current_page.penalty_total = paragraph.penalty'
    )

    # Bug 4: Fix sort tiebreaker - add paragraph_id to sort key
    content = content.replace(
        'key=lambda c: (c["penalty"], c["position"])',
        'key=lambda c: (c["penalty"], c["paragraph_id"], c["position"])'
    )

    with open(engine_path, 'w') as f:
        f.write(content)

    print("Layout engine repaired successfully.")


if __name__ == "__main__":
    repair()
