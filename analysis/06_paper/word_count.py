#!/usr/bin/env python3
"""Word count of the main text for the title page: sections 1 to 8, without floats, comments and
LaTeX commands, rounded to the nearest hundred. Writes paper/generated/wordcount.tex.

Usage:
    python analysis/06_paper/word_count.py
"""

from __future__ import annotations

import re
from pathlib import Path

PAPER = Path(__file__).resolve().parents[2] / "paper"
SECTIONS = sorted(PAPER.glob("sections/0[1-8]-*.tex"))


def words(text: str) -> int:
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = re.sub(r"\\begin\{(inlinefloat|table\*?|figure\*?|tabular)\}.*?\\end\{\1\}", " ", text, flags=re.S)
    text = re.sub(r"\\(cite[tp]?|ref|label|url|input|includegraphics)\*?(\[[^]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z]+\*?", " x ", text)  # a macro stands for one word, mostly a number
    text = re.sub(r"[{}\[\]$~\\&]", " ", text)
    return len([t for t in text.split() if re.search(r"[A-Za-z0-9]", t)])


def main() -> int:
    total = sum(words(p.read_text()) for p in SECTIONS)
    rounded = int(round(total, -2))
    (PAPER / "generated" / "wordcount.tex").write_text(
        "% Written by analysis/06_paper/word_count.py; sections 1 to 8 without floats.\n"
        f"\\newcommand{{\\WordCount}}{{about {rounded:,}}}\n".replace(",", "{,}")
    )
    print(f"main text: {total} words, reported as about {rounded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
