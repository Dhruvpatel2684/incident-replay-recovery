"""
Document Layout Engine - Typesetting and Pagination System

Processes input paragraphs from chapter data files, applies line-breaking
and page composition algorithms, then produces paginated layout output
with per-page quality metrics.
"""

import json
import configparser
import os
import textwrap
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Paragraph:
    """Represents a single paragraph with its metadata."""
    id: str
    priority: int
    mode: str
    text: str
    chapter_index: int
    lines: List[str] = field(default_factory=list)
    penalty: float = 0.0


@dataclass
class Page:
    """Represents a composed page in the output document."""
    page_number: int
    lines: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    penalty_total: float = 0.0


class LayoutEngine:
    """
    Core layout engine that handles line breaking, page composition,
    and quality metric computation for multi-chapter documents.
    """

    def __init__(self, config_path: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        # Load layout parameters from configuration
        self.line_width = self.config.getint("layout", "line_width")
        self.page_height = self.config.getint("layout", "page_height")
        self.penalty_threshold = self.config.getint("layout", "penalty_threshold")
        self.default_mode = self.config.get("layout", "default_mode")

        # Parse allowed typesetting modes from config
        raw_modes = self.config.get("layout", "allowed_modes")
        self._allowed_modes = set(raw_modes.split(","))

        self.paragraphs: List[Paragraph] = []
        self.pages: List[Page] = []
        self.break_candidates: List[Dict[str, Any]] = []

    def load_chapter(self, filepath: str, chapter_index: int) -> None:
        """Load paragraphs from a chapter JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        for para_data in data["paragraphs"]:
            mode = para_data.get("mode", self.default_mode)

            # Validate mode against allowed set
            if mode not in self._allowed_modes:
                mode = self.default_mode

            para = Paragraph(
                id=para_data["id"],
                priority=para_data["priority"],
                mode=mode,
                text=para_data["text"],
                chapter_index=chapter_index
            )
            self.paragraphs.append(para)

    def break_lines(self, paragraph: Paragraph) -> List[str]:
        """
        Break paragraph text into lines respecting the configured line width.
        Different modes produce different line arrangements.
        """
        text = paragraph.text
        width = self.line_width

        if paragraph.mode == "centered":
            # Center each line within the available width
            raw_lines = textwrap.wrap(text, width=width)
            lines = [line.center(width) for line in raw_lines]
        elif paragraph.mode == "ragged-right":
            # Simple left-aligned wrapping
            lines = textwrap.wrap(text, width=width)
        elif paragraph.mode == "hyphenated":
            # Simulate hyphenation with tighter wrapping
            lines = textwrap.wrap(text, width=width, break_on_hyphens=True)
        else:
            # Justified mode: wrap and pad lines to full width
            raw_lines = textwrap.wrap(text, width=width)
            lines = []
            for i, line in enumerate(raw_lines):
                if i < len(raw_lines) - 1 and len(line) < width:
                    # Pad with spaces for justification
                    words = line.split()
                    if len(words) > 1:
                        total_spaces = width - sum(len(w) for w in words)
                        gaps = len(words) - 1
                        base_space = total_spaces // gaps
                        extra = total_spaces % gaps
                        justified = ""
                        for j, word in enumerate(words[:-1]):
                            spaces = base_space + (1 if j < extra else 0)
                            justified += word + " " * spaces
                        justified += words[-1]
                        lines.append(justified)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)

            if not lines:
                lines = [text[:width]]

        return lines

    def compute_penalty(self, paragraph: Paragraph) -> float:
        """
        Compute layout penalty for a paragraph based on line variance
        and mode-specific quality factors.
        """
        if not paragraph.lines:
            return 0.0

        # Base penalty from line length variance
        lengths = [len(line.rstrip()) for line in paragraph.lines]
        if len(lengths) < 2:
            return 1.0

        avg_len = sum(lengths) / len(lengths)
        variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
        base_penalty = min(variance / (self.line_width * 2), 100.0)

        # Mode-specific adjustments
        if paragraph.mode == "justified":
            base_penalty *= 0.7
        elif paragraph.mode == "ragged-right":
            base_penalty *= 1.2
        elif paragraph.mode == "centered":
            base_penalty *= 0.9
        elif paragraph.mode == "hyphenated":
            base_penalty *= 0.6

        return round(base_penalty, 2)

    def compose_pages(self) -> None:
        """
        Arrange broken lines into pages respecting page height constraints.
        Tracks penalty accumulation and generates break candidates.
        """
        current_page = Page(page_number=1)
        self.pages = [current_page]
        line_count = 0

        for paragraph in self.paragraphs:
            paragraph.lines = self.break_lines(paragraph)
            paragraph.penalty = self.compute_penalty(paragraph)

            for line_idx, line in enumerate(paragraph.lines):
                if line_count >= self.page_height:
                    # Create page break candidate
                    # Note: position is local to each paragraph
                    candidate = {
                        "penalty": paragraph.penalty,
                        "position": line_idx,
                        "paragraph_id": paragraph.id,
                        "page": current_page.page_number
                    }
                    self.break_candidates.append(candidate)

                    # Start new page
                    current_page = Page(page_number=len(self.pages) + 1)
                    self.pages.append(current_page)
                    line_count = 0

                current_page.lines.append(line)
                line_count += 1

            # Track paragraph assignment to page
            current_page.paragraphs.append(paragraph.id)

            # Accumulate penalty scores for the page
            current_page.penalty_total += paragraph.penalty

    def select_optimal_breaks(self) -> List[Dict[str, Any]]:
        """
        Select optimal page break points from candidates using
        multi-key sorting for deterministic ordering.
        """
        if not self.break_candidates:
            return []

        # Sort candidates by penalty (ascending), then position
        sorted_candidates = sorted(
            self.break_candidates,
            key=lambda c: (c["penalty"], c["position"])
        )

        return sorted_candidates

    def compute_page_metrics(self) -> List[Dict[str, Any]]:
        """Compute quality metrics for each composed page."""
        metrics = []

        for page in self.pages:
            fill_ratio = len(page.lines) / self.page_height if self.page_height > 0 else 0
            avg_line_len = 0
            if page.lines:
                avg_line_len = sum(len(l.rstrip()) for l in page.lines) / len(page.lines)

            quality = max(0, 100 - page.penalty_total) * fill_ratio

            metrics.append({
                "page_number": page.page_number,
                "line_count": len(page.lines),
                "paragraph_count": len(page.paragraphs),
                "fill_ratio": round(fill_ratio, 4),
                "avg_line_length": round(avg_line_len, 2),
                "penalty_total": round(page.penalty_total, 2),
                "quality_score": round(quality, 2)
            })

        return metrics

    def run(self, data_dir: str, output_dir: str) -> Dict[str, Any]:
        """
        Execute the complete layout process: load chapters,
        break lines, compose pages, compute metrics.
        """
        # Load all chapters
        chapter_files = ["chapter1.json", "chapter2.json", "chapter3.json"]
        for idx, filename in enumerate(chapter_files):
            filepath = os.path.join(data_dir, filename)
            if os.path.exists(filepath):
                self.load_chapter(filepath, idx)

        # Compose pages
        self.compose_pages()

        # Select optimal breaks
        optimal_breaks = self.select_optimal_breaks()

        # Compute metrics
        page_metrics = self.compute_page_metrics()

        # Build result
        result = {
            "total_paragraphs": len(self.paragraphs),
            "total_pages": len(self.pages),
            "line_width": self.line_width,
            "page_height": self.page_height,
            "allowed_modes": sorted(list(self._allowed_modes)),
            "optimal_breaks": optimal_breaks[:10],
            "paragraphs_processed": [
                {
                    "id": p.id,
                    "mode": p.mode,
                    "line_count": len(p.lines),
                    "penalty": p.penalty,
                    "chapter_index": p.chapter_index
                }
                for p in self.paragraphs
            ]
        }

        # Write outputs
        os.makedirs(output_dir, exist_ok=True)

        with open(os.path.join(output_dir, "layout_result.json"), 'w') as f:
            json.dump(result, f, indent=2)

        with open(os.path.join(output_dir, "page_metrics.json"), 'w') as f:
            json.dump(page_metrics, f, indent=2)

        return result
