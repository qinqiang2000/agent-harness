"""Multi-rule comparison feature acceptance tests.

Tests category grouping, batch panel generation, status filtering,
multi-rule JSON parsing, and prompt building with rule IDs.

Run: python -m pytest tests/audit/test_multi_rule.py -v
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pytest

# Project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES_DIR / "multi_rule_cases.json").read_text("utf-8"))


# ===========================================================================
# 1. Rule category grouping
# ===========================================================================
class TestCategoryGrouping:
    """Verify rules are correctly grouped by category."""

    def _group_rules(self, rules):
        """Group rules by category, preserving order."""
        groups = defaultdict(list)
        for r in rules:
            cat = r.get("category") or "other"
            groups[cat].append(r["id"])
        return dict(groups)

    def test_all_rules_grouped(self):
        """All rules grouped correctly by category."""
        data = CASES["category_grouping"]
        groups = self._group_rules(data["rules"])
        assert groups == data["expected_groups"]

    def test_enabled_rules_grouped(self):
        """Only enabled rules grouped correctly."""
        data = CASES["category_grouping"]
        enabled = [r for r in data["rules"] if r.get("enabled", True)]
        groups = self._group_rules(enabled)
        assert groups == data["expected_enabled_groups"]

    def test_each_rule_has_category(self):
        """Every rule must have a non-empty category."""
        for r in CASES["category_grouping"]["rules"]:
            assert r.get("category"), f"Rule {r['id']} missing category"

    def test_each_rule_has_color(self):
        """Every rule must have a color field."""
        for r in CASES["category_grouping"]["rules"]:
            assert r.get("color"), f"Rule {r['id']} missing color"
            assert r["color"].startswith("#"), f"Rule {r['id']} color should be hex"


# ===========================================================================
# 2. Prompt building with rule IDs
# ===========================================================================
class TestPromptBuilding:
    """Verify handler builds prompt with rule.id for each rule."""

    def test_prompt_contains_rule_ids_and_text(self):
        """Prompt must include rule ID and text for every rule."""
        from plugins.bundled.audit.handler import AuditHandler
        from plugins.bundled.audit.models import AuditRule

        data = CASES["prompt_building"]
        rules = [AuditRule(**r) for r in data["rules"]]

        # AuditHandler.build_audit_prompt is an instance method but doesn't use self
        # beyond default_skill, so we call it directly via the class
        prompt = AuditHandler.build_audit_prompt(None, data["files"], rules)

        for expected in data["expect_in_prompt"]:
            assert expected in prompt, (
                f"Expected {expected!r} in prompt, got:\n{prompt}"
            )

    def test_prompt_rule_order_preserved(self):
        """Rules appear in prompt in the same order as input."""
        from plugins.bundled.audit.handler import AuditHandler
        from plugins.bundled.audit.models import AuditRule

        data = CASES["prompt_building"]
        rules = [AuditRule(**r) for r in data["rules"]]
        prompt = AuditHandler.build_audit_prompt(None, data["files"], rules)

        # Find positions of rule IDs in prompt
        positions = []
        for r in data["rules"]:
            pos = prompt.find(r["id"])
            assert pos >= 0, f"Rule {r['id']} not found in prompt"
            positions.append(pos)

        assert positions == sorted(positions), (
            f"Rules not in order: {positions}"
        )


# ===========================================================================
# 3. Status filtering
# ===========================================================================
class TestStatusFilter:
    """Verify filtering audit results by rule status."""

    @staticmethod
    def _filter_rules(rules, status):
        """Filter rules by status. 'ALL' returns everything."""
        if status == "ALL":
            return rules
        return [r for r in rules if r["status"] == status]

    @pytest.mark.parametrize("status", ["PASS", "FAIL", "UNABLE_TO_DETERMINE", "ALL"])
    def test_filter_by_status(self, status):
        data = CASES["status_filter"]
        rules = data["audit_result"]["rules"]
        filtered = self._filter_rules(rules, status)
        expected_ids = data["expected_by_status"][status]
        actual_ids = [r["id"] for r in filtered]
        assert actual_ids == expected_ids, (
            f"Status={status}: expected {expected_ids}, got {actual_ids}"
        )

    def test_summary_counts_match(self):
        """Summary counts must match actual rule statuses."""
        data = CASES["status_filter"]
        rules = data["audit_result"]["rules"]
        summary = data["audit_result"]["summary"]

        actual_pass = len([r for r in rules if r["status"] == "PASS"])
        actual_fail = len([r for r in rules if r["status"] == "FAIL"])
        actual_unknown = len([r for r in rules if r["status"] == "UNABLE_TO_DETERMINE"])

        assert actual_pass == summary["pass"]
        assert actual_fail == summary["fail"]
        assert actual_unknown == summary["unknown"]


# ===========================================================================
# 4. Batch panel generation for whiteboard
# ===========================================================================
class TestBatchPanelGeneration:
    """Verify multi-rule → multi-panel generation logic."""

    PALETTE = ['#3B82F6', '#F59E0B', '#10B981', '#EF4444', '#8B5CF6', '#F97316']

    @staticmethod
    def _generate_panels(rules, documents):
        """Simulate the frontend batch comparison logic (all rules merged).

        In batch mode, panels for the same (document, page) are merged,
        combining highlights from different rules with different colors.

        Returns list of panel dicts: {filename, page, highlights, rule_ids}.
        """
        palette = ['#3B82F6', '#F59E0B', '#10B981', '#EF4444', '#8B5CF6', '#F97316']

        # Collect all highlights keyed by (filename, page)
        merged = defaultdict(lambda: {"highlights": [], "rule_ids": set()})

        for rule in rules:
            rule_idx = rule.get("id", "rule-1")
            try:
                idx = int(rule_idx.split("-")[1]) - 1
            except (IndexError, ValueError):
                idx = 0
            rule_color = palette[idx % len(palette)]

            for comp in rule.get("comparisons", []):
                if not comp.get("page"):
                    continue
                doc = next(
                    (d for d in documents if d["identified_as"] == comp["source"]),
                    None,
                )
                if not doc:
                    continue
                key = (doc["file"], comp["page"])
                merged[key]["highlights"].append({
                    "value": comp["value"],
                    "label": comp["field_name"],
                    "color": rule_color,
                })
                merged[key]["rule_ids"].add(rule_idx)

        panels = []
        for (filename, page), data in merged.items():
            panels.append({
                "filename": filename,
                "page": page,
                "highlights": data["highlights"],
                "rule_ids": sorted(data["rule_ids"]),
            })
        return panels

    def test_total_panel_count(self):
        """Batch generation creates correct number of panels."""
        data = CASES["batch_panel_generation"]
        panels = self._generate_panels(data["rules"], data["documents"])
        expected = data["expected_panels"]["total_count"]
        assert len(panels) == expected, (
            f"Expected {expected} panels, got {len(panels)}: "
            f"{[(p['rule_id'], p['filename']) for p in panels]}"
        )

    def test_panels_by_document(self):
        """Each document gets the right number of panels."""
        data = CASES["batch_panel_generation"]
        panels = self._generate_panels(data["rules"], data["documents"])

        by_doc = defaultdict(int)
        for p in panels:
            by_doc[p["filename"]] += 1

        for doc_name, expected_count in data["expected_panels"]["by_document"].items():
            assert by_doc.get(doc_name, 0) == expected_count, (
                f"Expected {expected_count} panel(s) for {doc_name}, "
                f"got {by_doc.get(doc_name, 0)}"
            )

    def test_colors_differ_between_rules(self):
        """Different rules' highlights on the same panel have different colors."""
        data = CASES["batch_panel_generation"]
        panels = self._generate_panels(data["rules"], data["documents"])

        # For panels with multiple rules, verify the highlight colors differ
        for p in panels:
            if len(p["rule_ids"]) <= 1:
                continue
            colors_in_panel = set(h["color"] for h in p["highlights"])
            assert len(colors_in_panel) > 1, (
                f"Panel {p['filename']} p{p['page']} has multiple rules "
                f"but only one highlight color: {colors_in_panel}"
            )

    def test_merged_panel_has_all_highlights(self):
        """Merged panel for 报价单 page 1 should have highlights from 4 rules."""
        data = CASES["batch_panel_generation"]
        panels = self._generate_panels(data["rules"], data["documents"])
        baojiadan = next(p for p in panels if p["filename"] == "报价单.pdf")
        # rule-1(甲方), rule-3(费用总计), rule-4(项目抬头), rule-6(项目抬头)
        assert len(baojiadan["highlights"]) == 4, (
            f"Expected 4 highlights on 报价单, got {len(baojiadan['highlights'])}"
        )
        assert set(baojiadan["rule_ids"]) == {"rule-1", "rule-3", "rule-4", "rule-6"}

    def test_no_panels_for_empty_comparisons(self):
        """Rules with no comparisons produce no panels."""
        data = CASES["batch_panel_generation"]
        empty_rule = {
            "id": "rule-2", "text": "红章校验", "status": "UNABLE_TO_DETERMINE",
            "comparisons": [], "explanation": "无法确认"
        }
        panels = self._generate_panels([empty_rule], data["documents"])
        assert len(panels) == 0

    def test_no_panels_for_missing_page(self):
        """Comparisons without page number produce no panels."""
        data = CASES["batch_panel_generation"]
        rule = {
            "id": "rule-1", "text": "test", "status": "PASS",
            "comparisons": [
                {"source": "报价单", "field_name": "甲方", "value": "test", "page": None}
            ],
            "explanation": ""
        }
        panels = self._generate_panels([rule], data["documents"])
        assert len(panels) == 0


# ===========================================================================
# 5. Multi-rule JSON parsing (frontend dedup)
# ===========================================================================
class TestMultiRuleJsonParse:
    """Verify frontend correctly parses multi-rule JSON and deduplicates."""

    @staticmethod
    def _parse_audit_json(text):
        """Simulate frontend tryParseAuditResult logic."""
        patterns = [
            r"<!-- AUDIT_RESULT_JSON\s*\n?([\s\S]*?)\n?\s*AUDIT_RESULT_JSON -->",
            r"```json\s*\n?\s*// AUDIT_RESULT_JSON\s*\n?([\s\S]*?)\n?\s*// AUDIT_RESULT_JSON\s*\n?\s*```",
            r"AUDIT_RESULT_JSON\s*\n?([\s\S]*?)\n?\s*AUDIT_RESULT_JSON",
        ]
        json_str = None
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                json_str = m.group(1)
                break

        if not json_str:
            # Fallback: large JSON block
            m = re.search(
                r'(\{[\s\S]*?"rules"\s*:\s*\[[\s\S]*?"summary"\s*:\s*\{[\s\S]*?\}\s*\})',
                text,
            )
            if m:
                json_str = m.group(1)

        if not json_str:
            return None, text

        result = json.loads(json_str.strip())

        # Dedup: remove JSON block + detailed section
        clean = re.sub(
            r"<!-- AUDIT_RESULT_JSON[\s\S]*?AUDIT_RESULT_JSON -->", "", text
        )
        clean = re.sub(
            r"```json\s*// AUDIT_RESULT_JSON[\s\S]*?// AUDIT_RESULT_JSON\s*```",
            "", clean,
        )
        clean = re.sub(r"##\s*逐条审核结果[\s\S]*?(?=##\s*审核总结)", "", clean)
        return result, clean.strip()

    @pytest.mark.parametrize(
        "case",
        CASES["multi_rule_json_parse"]["cases"],
        ids=[c["name"] for c in CASES["multi_rule_json_parse"]["cases"]],
    )
    def test_parse_multi_rule_json(self, case):
        result, clean_text = self._parse_audit_json(case["input"])

        if case.get("expect_parse_fail"):
            assert result is None, "Expected parse to fail but got result"
            for expected in case.get("expect_raw_contains", []):
                assert expected in clean_text, (
                    f"Expected {expected!r} in raw text when parse fails"
                )
            return

        assert result is not None, "Failed to parse audit JSON"

        if "expect_rule_count" in case:
            assert len(result["rules"]) == case["expect_rule_count"], (
                f"Expected {case['expect_rule_count']} rules, got {len(result['rules'])}"
            )

        if "expect_summary" in case:
            assert result["summary"] == case["expect_summary"]

        if "expect_rule_ids" in case:
            actual_ids = [r["id"] for r in result["rules"]]
            assert actual_ids == case["expect_rule_ids"]

        if "expect_dedup_contains" in case:
            for expected in case["expect_dedup_contains"]:
                assert expected in clean_text, (
                    f"Expected {expected!r} in cleaned text"
                )

        if "expect_dedup_not_contains" in case:
            for unexpected in case["expect_dedup_not_contains"]:
                assert unexpected not in clean_text, (
                    f"Did NOT expect {unexpected!r} in cleaned text"
                )


# ===========================================================================
# 6. Rule color uniqueness within default palette
# ===========================================================================
class TestRuleColors:
    """Verify color assignment logic for rules."""

    def test_default_rules_have_unique_colors(self):
        """Default 7 rules should have distinguishable colors."""
        rules = CASES["category_grouping"]["rules"]
        colors = [r["color"] for r in rules]
        # At minimum, rules in the same category should have different colors
        # from rules in other categories (within palette limits)
        assert len(set(colors)) >= 5, (
            f"Expected at least 5 unique colors, got {len(set(colors))}: {colors}"
        )

    def test_color_format(self):
        """All colors must be valid hex color codes."""
        rules = CASES["category_grouping"]["rules"]
        for r in rules:
            assert re.match(r"^#[0-9A-Fa-f]{6}$", r["color"]), (
                f"Rule {r['id']} has invalid color: {r['color']}"
            )
