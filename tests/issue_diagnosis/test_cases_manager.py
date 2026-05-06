"""
issue-diagnosis cases.md 读写逻辑单元测试

覆盖场景：
1. 解析 cases.md，正确读取字段
2. 命中高可信 case（answer_confidence >= 0.8）→ 档位 1
3. 命中低可信 case（answer_confidence < 0.8）→ 档位 2
4. 未命中（match_confidence < 0.6）→ 档位 3
5. rejected case 不参与匹配
6. 显式确认 → answer_confidence +0.1，confirmed_count +1，last_confirmed 更新
7. answer_confidence 上限 0.95
8. 显式否定 → answer_confidence -0.2
9. answer_confidence 降至 0.1 以下 → 状态变 rejected
10. 创建新 case，字段完整性校验
11. 隐式纠正 → 创建新 case，answer_confidence=0.3，不修改旧 case

Run: python -m pytest tests/issue_diagnosis/test_cases_manager.py -v
"""

import re
import textwrap
from copy import deepcopy
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# cases.md 解析与操作的纯函数（模拟 agent 执行的逻辑）
# ---------------------------------------------------------------------------

CASE_PATTERN = re.compile(
    r"## (Case #\d+)\n(.*?)(?=\n## Case #|\Z)", re.DOTALL
)
FIELD_PATTERN = re.compile(r"^- ([\w_]+): (.+)$", re.MULTILINE)


def parse_cases(content: str) -> list[dict]:
    """从 cases.md 内容解析所有 case。"""
    cases = []
    for m in CASE_PATTERN.finditer(content):
        case_id = m.group(1)
        body = m.group(2)
        fields = dict(FIELD_PATTERN.findall(body))
        cases.append({
            "id": case_id,
            "match_confidence": float(fields.get("match_confidence", 0)),
            "answer_confidence": float(fields.get("answer_confidence", 0)),
            "confirmed_count": int(fields.get("confirmed_count", 0)),
            "last_confirmed": fields.get("last_confirmed", "null").strip(),
            "状态": fields.get("状态", "pending_review").strip(),
        })
    return cases


def decide_tier(case: dict) -> int:
    """根据 match_confidence 和 answer_confidence 决定档位（1/2/3）。"""
    mc = case["match_confidence"]
    ac = case["answer_confidence"]
    if mc < 0.6:
        return 3
    if ac >= 0.8:
        return 1
    return 2


def apply_confirmation(case: dict, today: str) -> dict:
    """用户显式确认 → answer_confidence +0.1（上限 0.95），confirmed_count +1。"""
    updated = deepcopy(case)
    updated["answer_confidence"] = min(round(updated["answer_confidence"] + 0.1, 2), 0.95)
    updated["confirmed_count"] += 1
    updated["last_confirmed"] = today
    return updated


def apply_negation(case: dict) -> dict:
    """用户显式否定 → answer_confidence -0.2，降至 0.1 以下则标记 rejected。"""
    updated = deepcopy(case)
    updated["answer_confidence"] = round(updated["answer_confidence"] - 0.2, 2)
    if updated["answer_confidence"] < 0.1:
        updated["状态"] = "rejected"
    return updated


def build_new_case(
    case_id: str,
    trigger: str,
    initial_diagnosis: str,
    feedback_type: str,
    feedback_text: str,
    correct_path: str,
    applicable_condition: str,
    match_confidence: float,
    answer_confidence: float,
    created_date: str,
) -> dict:
    """构建新 case 字典，校验必填字段。"""
    assert 0.6 <= match_confidence <= 0.9, "match_confidence 应在 0.6-0.9"
    assert answer_confidence in (0.9, 0.8, 0.5, 0.3), \
        "answer_confidence 应为 0.9/0.8/0.5/0.3 之一"
    return {
        "id": case_id,
        "触发场景": trigger,
        "初次诊断": initial_diagnosis,
        "用户反馈": f"[{feedback_type}] {feedback_text}",
        "正确路径": correct_path,
        "适用条件": applicable_condition,
        "match_confidence": match_confidence,
        "answer_confidence": answer_confidence,
        "confirmed_count": 0,
        "last_confirmed": "null",
        "状态": "pending_review",
        "创建时间": created_date,
    }


def should_ask_confirmation(
    hit_case: bool = False,
    has_speculation: bool = False,
    faq_only: bool = False,
    no_log: bool = False,
) -> bool:
    """Step 6 确认请求触发条件。"""
    return hit_case or has_speculation or faq_only or no_log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CASES_MD = textwrap.dedent("""\
    # Issue-Diagnosis 历史经验库

    <!-- Cases will be appended below by the agent -->

    ## Case #002
    - 触发场景: 星瀚系统报错"没有开启软证书模式"
    - 初次诊断: （本条为用户主动录入的经验，无初次诊断）
    - 用户反馈: [显式] 用户直接提供正确根因
    - 正确路径: 检查收票通道配置，改为"下数电"或"乐企"通道
    - 适用条件: 报错含"没有开启软证书模式"，系统为星瀚
    - match_confidence: 0.8
    - answer_confidence: 0.9
    - confirmed_count: 0
    - last_confirmed: null
    - 状态: pending_review
    - 创建时间: 2026-04-10

    ## Case #001
    - 触发场景: 登录报错"数电账号里维护的电子税局身份有误"，errcode=0702034
    - 初次诊断: 税局侧身份校验问题
    - 用户反馈: [显式] 不对，是 Redis 缓存了错误 roleCode
    - 正确路径: 清除 Redis 中 NEW_ERA_LOGIN_SUCCESS_ROLE_CODE 缓存
    - 适用条件: 报错含"电子税局身份有误"或 errcode=0702034
    - match_confidence: 0.8
    - answer_confidence: 0.8
    - confirmed_count: 0
    - last_confirmed: null
    - 状态: pending_review
    - 创建时间: 2026-04-10

    ## Case #003
    - 触发场景: 开票接口返回参数校验失败
    - 初次诊断: 字段格式错误
    - 用户反馈: [隐式] 实际是枚举值传错了
    - 正确路径: 检查 invoiceType 枚举值
    - 适用条件: 报错含"参数校验失败"且涉及开票
    - match_confidence: 0.7
    - answer_confidence: 0.3
    - confirmed_count: 0
    - last_confirmed: null
    - 状态: pending_review
    - 创建时间: 2026-04-10

    ## Case #004
    - 触发场景: 查验接口超时
    - 初次诊断: 网络问题
    - 用户反馈: [显式] 不对
    - 正确路径: 税局接口限流
    - 适用条件: 查验超时
    - match_confidence: 0.7
    - answer_confidence: 0.5
    - confirmed_count: 0
    - last_confirmed: null
    - 状态: rejected
    - 创建时间: 2026-04-10
""")


@pytest.fixture
def cases() -> list[dict]:
    return parse_cases(SAMPLE_CASES_MD)


@pytest.fixture
def case_high(cases) -> dict:
    return next(c for c in cases if c["id"] == "Case #002")


@pytest.fixture
def case_mid(cases) -> dict:
    return next(c for c in cases if c["id"] == "Case #001")


@pytest.fixture
def case_low(cases) -> dict:
    return next(c for c in cases if c["id"] == "Case #003")


@pytest.fixture
def case_rejected(cases) -> dict:
    return next(c for c in cases if c["id"] == "Case #004")


# ---------------------------------------------------------------------------
# 1. 解析测试
# ---------------------------------------------------------------------------

class TestParseCases:
    def test_parse_count(self, cases):
        assert len(cases) == 4

    def test_parse_fields_high_confidence(self, case_high):
        assert case_high["match_confidence"] == 0.8
        assert case_high["answer_confidence"] == 0.9
        assert case_high["confirmed_count"] == 0
        assert case_high["last_confirmed"] == "null"
        assert case_high["状态"] == "pending_review"

    def test_parse_fields_mid_confidence(self, case_mid):
        assert case_mid["answer_confidence"] == 0.8

    def test_parse_rejected_status(self, case_rejected):
        assert case_rejected["状态"] == "rejected"


# ---------------------------------------------------------------------------
# 2. 档位决策测试
# ---------------------------------------------------------------------------

class TestDecideTier:
    def test_tier1_answer_confidence_09(self, case_high):
        """match>=0.6 且 answer=0.9 → 档位 1。"""
        assert decide_tier(case_high) == 1

    def test_tier1_answer_confidence_08(self, case_mid):
        """match>=0.6 且 answer=0.8 → 档位 1。"""
        assert decide_tier(case_mid) == 1

    def test_tier2_answer_confidence_03(self, case_low):
        """match>=0.6 且 answer=0.3 → 档位 2。"""
        assert decide_tier(case_low) == 2

    def test_tier2_answer_confidence_05(self):
        """match>=0.6 且 answer=0.5 → 档位 2。"""
        case = {"match_confidence": 0.7, "answer_confidence": 0.5}
        assert decide_tier(case) == 2

    def test_tier3_low_match_confidence(self):
        """match_confidence=0.5 → 档位 3。"""
        case = {"match_confidence": 0.5, "answer_confidence": 0.9}
        assert decide_tier(case) == 3

    def test_tier3_zero_match(self):
        case = {"match_confidence": 0.0, "answer_confidence": 0.8}
        assert decide_tier(case) == 3

    def test_rejected_excluded_from_active_cases(self, cases):
        """rejected case 在匹配前被过滤，不进入档位决策。"""
        active = [c for c in cases if c["状态"] != "rejected"]
        assert all(c["id"] != "Case #004" for c in active)
        assert len(active) == 3


# ---------------------------------------------------------------------------
# 3. 显式确认测试
# ---------------------------------------------------------------------------

class TestApplyConfirmation:
    def test_confidence_09_capped_at_095(self, case_high):
        """0.9 + 0.1 超过上限，应截断为 0.95。"""
        updated = apply_confirmation(case_high, "2026-04-20")
        assert updated["answer_confidence"] == 0.95

    def test_confidence_08_increases_to_09(self, case_mid):
        """0.8 + 0.1 = 0.9。"""
        updated = apply_confirmation(case_mid, "2026-04-20")
        assert updated["answer_confidence"] == 0.9

    def test_confirmed_count_increments(self, case_high):
        updated = apply_confirmation(case_high, "2026-04-20")
        assert updated["confirmed_count"] == 1

    def test_last_confirmed_updated(self, case_high):
        updated = apply_confirmation(case_high, "2026-04-20")
        assert updated["last_confirmed"] == "2026-04-20"

    def test_multiple_confirmations_capped(self, case_high):
        """多次确认不超过 0.95。"""
        c = case_high
        for _ in range(5):
            c = apply_confirmation(c, "2026-04-20")
        assert c["answer_confidence"] <= 0.95

    def test_original_not_mutated(self, case_high):
        """原 case 不被修改（immutable 操作）。"""
        original_ac = case_high["answer_confidence"]
        apply_confirmation(case_high, "2026-04-20")
        assert case_high["answer_confidence"] == original_ac

    def test_no_write_when_no_case_hit(self):
        """未命中 case 时不触发写入。"""
        active_cases: list[dict] = []
        matched = [c for c in active_cases if c.get("match_confidence", 0) >= 0.6]
        assert matched == []


# ---------------------------------------------------------------------------
# 4. 显式否定测试
# ---------------------------------------------------------------------------

class TestApplyNegation:
    def test_confidence_09_decreases_to_07(self, case_high):
        """0.9 - 0.2 = 0.7。"""
        updated = apply_negation(case_high)
        assert updated["answer_confidence"] == pytest.approx(0.7)

    def test_status_unchanged_above_threshold(self, case_high):
        updated = apply_negation(case_high)
        assert updated["状态"] == "pending_review"

    def test_status_becomes_rejected_below_01(self):
        """0.2 - 0.2 = 0.0 < 0.1 → rejected。"""
        case = {"answer_confidence": 0.2, "状态": "pending_review"}
        updated = apply_negation(case)
        assert updated["状态"] == "rejected"

    def test_exactly_01_not_rejected(self):
        """0.3 - 0.2 = 0.1，恰好等于 0.1，不标记 rejected。"""
        case = {"answer_confidence": 0.3, "状态": "pending_review"}
        updated = apply_negation(case)
        assert updated["answer_confidence"] == pytest.approx(0.1)
        assert updated["状态"] == "pending_review"

    def test_original_not_mutated(self, case_high):
        original_ac = case_high["answer_confidence"]
        apply_negation(case_high)
        assert case_high["answer_confidence"] == original_ac


# ---------------------------------------------------------------------------
# 5. 新 case 创建测试
# ---------------------------------------------------------------------------

class TestBuildNewCase:
    def test_explicit_correction_full_path(self):
        """显式纠正+完整路径 → answer_confidence=0.8。"""
        case = build_new_case(
            case_id="Case #005",
            trigger="开票接口报错 INVOICE_TYPE_INVALID",
            initial_diagnosis="参数格式错误",
            feedback_type="显式",
            feedback_text="不对，是 invoiceType 枚举值传了中文",
            correct_path="invoiceType 应传数字枚举值，如 01/02/03",
            applicable_condition="报错含 INVOICE_TYPE_INVALID",
            match_confidence=0.8,
            answer_confidence=0.8,
            created_date="2026-04-20",
        )
        assert case["answer_confidence"] == 0.8
        assert case["confirmed_count"] == 0
        assert case["last_confirmed"] == "null"
        assert case["状态"] == "pending_review"

    def test_implicit_correction_low_confidence(self):
        """隐式纠正 → answer_confidence=0.3。"""
        case = build_new_case(
            case_id="Case #006",
            trigger="收票查验失败",
            initial_diagnosis="网络超时",
            feedback_type="隐式",
            feedback_text="实际上 OCR 是成功的，问题在下游合规校验",
            correct_path="合规校验服务异常",
            applicable_condition="查验失败且 OCR 成功",
            match_confidence=0.7,
            answer_confidence=0.3,
            created_date="2026-04-20",
        )
        assert case["answer_confidence"] == 0.3

    def test_user_provided_answer_high_confidence(self):
        """用户主动录入 → answer_confidence=0.9。"""
        case = build_new_case(
            case_id="Case #007",
            trigger="星瀚报错软证书未开启",
            initial_diagnosis="（本条为用户主动录入的经验，无初次诊断）",
            feedback_type="显式",
            feedback_text="用户直接提供正确根因",
            correct_path="改为下数电通道",
            applicable_condition="报错含软证书",
            match_confidence=0.8,
            answer_confidence=0.9,
            created_date="2026-04-20",
        )
        assert case["answer_confidence"] == 0.9

    def test_invalid_match_confidence_raises(self):
        """match_confidence < 0.6 应抛出 AssertionError。"""
        with pytest.raises(AssertionError):
            build_new_case(
                case_id="Case #008",
                trigger="test",
                initial_diagnosis="test",
                feedback_type="显式",
                feedback_text="test",
                correct_path="test",
                applicable_condition="test",
                match_confidence=0.5,
                answer_confidence=0.8,
                created_date="2026-04-20",
            )

    def test_invalid_answer_confidence_raises(self):
        """answer_confidence 不在允许值列表应抛出 AssertionError。"""
        with pytest.raises(AssertionError):
            build_new_case(
                case_id="Case #009",
                trigger="test",
                initial_diagnosis="test",
                feedback_type="显式",
                feedback_text="test",
                correct_path="test",
                applicable_condition="test",
                match_confidence=0.7,
                answer_confidence=0.6,
                created_date="2026-04-20",
            )

    def test_implicit_correction_does_not_modify_old_case(self, case_high):
        """隐式纠正只创建新 case，不修改旧 case。"""
        original = deepcopy(case_high)
        # 隐式纠正：只创建新 case，不调用 apply_negation
        new_case = build_new_case(
            case_id="Case #010",
            trigger="星瀚软证书问题变体",
            initial_diagnosis="通道配置错误",
            feedback_type="隐式",
            feedback_text="实际上是证书过期，不是通道配置",
            correct_path="更新证书",
            applicable_condition="报错含软证书且证书过期",
            match_confidence=0.7,
            answer_confidence=0.3,
            created_date="2026-04-20",
        )
        assert case_high["answer_confidence"] == original["answer_confidence"]
        assert new_case["answer_confidence"] == 0.3


# ---------------------------------------------------------------------------
# 6. Step 6 确认请求触发条件测试
# ---------------------------------------------------------------------------

class TestConfirmationRequestTrigger:
    def test_trigger_when_case_hit(self):
        assert should_ask_confirmation(hit_case=True) is True

    def test_trigger_when_speculation(self):
        assert should_ask_confirmation(has_speculation=True) is True

    def test_trigger_when_faq_only(self):
        assert should_ask_confirmation(faq_only=True) is True

    def test_trigger_when_no_log(self):
        assert should_ask_confirmation(no_log=True) is True

    def test_no_trigger_with_full_evidence(self):
        """有完整证据链（日志+源码）时不追加确认请求。"""
        assert should_ask_confirmation() is False

    def test_multiple_conditions_still_triggers(self):
        assert should_ask_confirmation(hit_case=True, has_speculation=True) is True
