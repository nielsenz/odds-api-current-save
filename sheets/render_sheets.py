# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdfium2>=4.30", "pillow>=10"]
# ///
"""Render sheet PDFs to 300 dpi pages and overlapping strips for transcription.

Circa draws its text as vector outlines, so there is nothing for pdftotext or OCR-free
parsers to read; the strips are what TRANSCRIBE.md has agents read.

    uv run sheets/render_sheets.py <out_dir> <pdf or dir> [...] [--match 'NHL|NFL|CFB|CBK|NCAA']

Writes <out_dir>/png300/<book>__<stamp>__<name>_pN.png and <out_dir>/strips/..._sNN.png.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

STRIP_H, OVERLAP, DPI = 800, 120, 300


def page_prefix(pdf: Path) -> str:
    # sheets/pdfs/<book>/<stamp>/[archive/]<name>.pdf -> <book>__<stamp>__[archive_]<name>
    parts = pdf.parts
    if "pdfs" in parts:
        i = parts.index("pdfs")
        book, stamp = parts[i + 1], parts[i + 2]
        sub = "archive_" if pdf.parent.name == "archive" else ""
        return f"{book}__{stamp}__{sub}{pdf.stem}"
    return pdf.stem


def main() -> None:
    import pypdfium2 as pdfium
    from PIL import ImageOps

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--match", help="regex on the PDF name, e.g. 'NHL|NFL|CFB|CBK|NCAA|nhl|nfl|cfb|ncaa'")
    args = ap.parse_args()

    pdfs = sorted({p for i in args.inputs for p in ([i] if i.is_file() else i.rglob("*.pdf"))})
    if args.match:
        pdfs = [p for p in pdfs if re.search(args.match, p.name)]
    png_dir, strip_dir = args.out_dir / "png300", args.out_dir / "strips"
    png_dir.mkdir(parents=True, exist_ok=True)
    strip_dir.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        doc = pdfium.PdfDocument(pdf)
        for n in range(len(doc)):
            base = f"{page_prefix(pdf)}_p{n + 1}"
            img = doc[n].render(scale=DPI / 72).to_pil().convert("L")
            img.save(png_dir / f"{base}.png")
            bbox = ImageOps.invert(img).getbbox()
            if bbox is None:
                continue
            img = img.crop((0, bbox[1], img.width, bbox[3]))
            y, k = 0, 1
            while True:
                img.crop((0, y, img.width, min(y + STRIP_H, img.height))).save(strip_dir / f"{base}_s{k:02d}.png")
                if y + STRIP_H >= img.height:
                    break
                y, k = y + STRIP_H - OVERLAP, k + 1
            print(f"{base}: {k} strips")


if __name__ == "__main__":
    main()
