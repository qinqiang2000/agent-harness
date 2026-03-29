"""Audit plugin regression tests.

Tests fuzzy matching, PDF highlight placement, and native text search.
Run: python -m pytest tests/audit/test_highlight.py -v
"""

import json
import sys
from pathlib import Path

import pytest

# Project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES_DIR / "highlight_cases.json").read_text("utf-8"))

# Resolve PDF paths relative to fixtures dir
PDF_FILES = {}
for doc_type, rel_path in CASES["pdf_files"].items():
    p = (FIXTURES_DIR / rel_path).resolve()
    if p.exists():
        PDF_FILES[doc_type] = p


# ---------------------------------------------------------------------------
# Import plugin functions under test
# ---------------------------------------------------------------------------
from plugins.bundled.audit.plugin import (
    _fuzzy_match,
    _find_field_rect,
    _run_ocr,
    _search_text,
)


# ===========================================================================
# 1. Fuzzy match tests
# ===========================================================================
class TestFuzzyMatch:
    """Test _fuzzy_match with known OCR text vs target pairs."""

    @pytest.mark.parametrize(
        "case",
        CASES["fuzzy_match_cases"],
        ids=[c["name"] for c in CASES["fuzzy_match_cases"]],
    )
    def test_fuzzy_match(self, case):
        result = _fuzzy_match(case["ocr_text"], case["target"])
        assert result == case["expected"], (
            f"_fuzzy_match({case['ocr_text']!r}, {case['target']!r}) "
            f"returned {result}, expected {case['expected']}"
        )


# ===========================================================================
# 2. PDF highlight placement tests (require PyMuPDF + test PDFs)
# ===========================================================================
fitz = pytest.importorskip("fitz", reason="PyMuPDF not installed")


def _need_pdf(doc_type):
    if doc_type not in PDF_FILES:
        pytest.skip(f"Test PDF not found: {doc_type}")
    return PDF_FILES[doc_type]


class TestHighlightPlacement:
    """Test that _find_field_rect returns correct positions on real PDFs."""

    @pytest.mark.parametrize(
        "case",
        CASES["highlight_cases"],
        ids=[c["name"] for c in CASES["highlight_cases"]],
    )
    def test_highlight_rect(self, case):
        pdf_path = _need_pdf(case["pdf"])
        doc = fitz.open(str(pdf_path))
        pg = doc[case["page"] - 1]
        ocr_cache = {}

        rects = _find_field_rect(pg, case["value"], case.get("label", ""), ocr_cache)
        doc.close()

        if case["expect_hit"]:
            assert len(rects) >= 1, (
                f"Expected highlight hit for value={case['value']!r}, got 0 rects"
            )
            # Check region if specified
            region = case.get("expect_rect_region")
            if region:
                r = rects[0]
                x_range = region["x_range"]
                y_range = region["y_range"]
                cx = (r.x0 + r.x1) / 2
                cy = (r.y0 + r.y1) / 2
                assert x_range[0] <= cx <= x_range[1], (
                    f"Rect center x={cx:.1f} outside expected range {x_range}. "
                    f"Full rect=({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f})"
                )
                assert y_range[0] <= cy <= y_range[1], (
                    f"Rect center y={cy:.1f} outside expected range {y_range}. "
                    f"Full rect=({r.x0:.1f},{r.y0:.1f},{r.x1:.1f},{r.y1:.1f})"
                )
        else:
            assert len(rects) == 0, (
                f"Expected no highlight for value={case['value']!r}, got {len(rects)}"
            )

    def test_rotated_pdf_no_derotation_drift(self):
        """Ensure OCR rects on rotated PDFs stay within page bounds."""
        pdf_path = _need_pdf("报价单")
        doc = fitz.open(str(pdf_path))
        pg = doc[0]

        if pg.rotation == 0:
            doc.close()
            pytest.skip("PDF is not rotated, test not applicable")

        page_w, page_h = pg.rect.width, pg.rect.height
        ocr_items = _run_ocr(pg)
        doc.close()

        for rect, text in ocr_items:
            assert rect.x0 >= -5 and rect.y0 >= -5, (
                f"OCR rect out of bounds (negative): {rect} text={text!r}"
            )
            assert rect.x1 <= page_w + 5 and rect.y1 <= page_h + 5, (
                f"OCR rect out of bounds (exceeds page {page_w}x{page_h}): "
                f"{rect} text={text!r}"
            )


# ===========================================================================
# 3. Search text tests on image-based PDF
# ===========================================================================
class TestSearchText:
    """Test _search_text fallback strategies on image-based PDFs."""

    def test_image_pdf_returns_empty(self):
        """Image-based PDF has no extractable text, _search_text returns []."""
        pdf_path = _need_pdf("报价单")
        doc = fitz.open(str(pdf_path))
        pg = doc[0]
        # Should return empty since PDF is image-based
        rects = _search_text(pg, "KFC Y25 2月疯狂星期四social项目")
        doc.close()
        assert rects == [], "Image-based PDF should return no native text matches"


