"""Render a concise Markdown research report to a paginated, shareable PDF.

This intentionally handles the simple headings and paragraphs used in the P1 report.
Run: python -m study.render_report_pdf
"""
from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _plain(value: str) -> str:
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    return re.sub(r"\*\*|\*|`", "", value).strip()


def render(source: Path, destination: Path) -> None:
    paragraphs: list[tuple[str, str]] = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            paragraphs.append(("title", _plain(line[2:])))
        elif line.startswith("### "):
            paragraphs.append(("subheading", _plain(line[4:])))
        elif line.startswith("## "):
            paragraphs.append(("heading", _plain(line[3:])))
        elif line.startswith("- "):
            paragraphs.append(("bullet", _plain(line[2:])))
        else:
            paragraphs.append(("body", _plain(line)))

    page_number = 0
    fig = None
    y = 0.0

    def new_page(pdf):
        nonlocal fig, y, page_number
        if fig is not None:
            pdf.savefig(fig)
            plt.close(fig)
        page_number += 1
        fig = plt.figure(figsize=(8.27, 11.69), facecolor="white")
        fig.text(0.08, 0.965, "COLLUSION STUDY  |  8 OCTOBER 2026",
                 fontsize=8, color="#64748b", family="DejaVu Sans")
        fig.text(0.08, 0.035, f"Research working draft  •  page {page_number}",
                 fontsize=8, color="#64748b", family="DejaVu Sans")
        y = 0.925

    with PdfPages(destination) as pdf:
        new_page(pdf)
        for kind, paragraph in paragraphs:
            if kind == "title":
                size, width, line_step, gap, color = 17, 58, 0.026, 0.016, "#0f172a"
            elif kind == "heading":
                size, width, line_step, gap, color = 11.5, 86, 0.020, 0.010, "#0f172a"
            elif kind == "subheading":
                size, width, line_step, gap, color = 9.8, 96, 0.018, 0.008, "#172033"
            else:
                size, width, line_step, gap, color = 8.7, 104, 0.0165, 0.009, "#263445"
            prefix = "•  " if kind == "bullet" else ""
            lines = textwrap.wrap(prefix + paragraph, width=width,
                                  subsequent_indent="   " if kind == "bullet" else "",
                                  break_long_words=False, break_on_hyphens=False)
            required = len(lines) * line_step + gap
            if y - required < 0.075:
                new_page(pdf)
            for line in lines:
                fig.text(0.08, y, line, fontsize=size, color=color, family="DejaVu Sans",
                         va="top", fontweight="bold" if kind in {"title", "heading", "subheading"} else "normal")
                y -= line_step
            y -= gap
        pdf.savefig(fig)
        plt.close(fig)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("P1_COMPARISON_REPORT.md"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("P1_COMPARISON_REPORT.pdf"))
    args = parser.parse_args(argv)
    render(args.source, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
