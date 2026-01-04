"""
发票云客服 Skill 测试问题集

基于 .claude/skills/customer-service/SKILL.md 设计的测试用例
用于验证 agent 客服问答的准确度

测试维度：
1. 产品识别准确性
2. 目录定位准确性
3. 规则遵循（标准话术、来源引用）
4. 边界情况处理
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TestCategory(Enum):
    """测试类别"""
    PRODUCT_RECOGNITION = "产品识别"
    DIRECTORY_LOCATION = "目录定位"
    RULE_COMPLIANCE = "规则遵循"
    EDGE_CASES = "边界情况"
    AUXILIARY_SYSTEMS = "辅助系统"
    MULTI_SYSTEM = "多系统协作"


class ExpectedBehavior(Enum):
    """预期行为类型"""
    SEARCH_DIR = "搜索指定目录"
    ASK_PRODUCT = "询问产品版本"
    STANDARD_REPLY = "返回标准话术"
    CITE_SOURCE = "引用来源"
    DISTINGUISH_PRODUCT = "区分产品"
    WARN_RISK = "风险提醒"
    EXPAND_SEARCH = "扩展搜索"


@dataclass
class TestCase:
    """测试用例"""
    id: str
    name: str
    category: TestCategory
    query: str
    expected_behaviors: list[str]
    expected_product: Optional[str] = None
    expected_module: Optional[str] = None
    expected_directory: Optional[str] = None
    expected_output_contains: list[str] = field(default_factory=list)
    expected_output_not_contains: list[str] = field(default_factory=list)
    notes: Optional[str] = None


# ============================================================
# 测试问题集
# ============================================================

TEST_CASES: list[TestCase] = [
    # ============================================================
    # 一、产品识别测试（验证能否正确识别产品线）
    # ============================================================

    # 1.1 明确产品 - 直接命名
    TestCase(
        id="PROD-001",
        name="明确产品 - 标准版开票配置",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="标准版发票云开票如何配置数电票？",
        expected_behaviors=[
            "识别产品线：标准版发票云",
            "识别功能模块：开票",
            "搜索标准版配置或FAQ目录",
            "不混淆其他产品（星瀚、星空）"
        ],
        expected_product="标准版发票云",
        expected_module="开票",
        expected_directory="产品与交付知识/06-构建阶段/产品初始化配置/标准版发票云/"
    ),

    TestCase(
        id="PROD-002",
        name="明确产品 - 星瀚旗舰版收票",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="星瀚旗舰版发票云的收票勾选怎么操作？",
        expected_behaviors=[
            "识别产品线：星瀚旗舰版发票云",
            "识别功能模块：收票",
            "搜索星瀚旗舰版相关目录",
            "不使用标准版或星空旗舰版的答案"
        ],
        expected_product="星瀚旗舰版发票云",
        expected_module="收票"
    ),

    TestCase(
        id="PROD-003",
        name="明确产品 - 星空旗舰版开票",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="星空旗舰版发票云开票报错怎么处理？",
        expected_behaviors=[
            "识别产品线：星空旗舰版发票云",
            "识别为问题排查类型",
            "搜索 11-常见问题/星空旗舰版/"
        ],
        expected_product="星空旗舰版发票云",
        expected_module="开票",
        expected_directory="产品与交付知识/11-常见问题/星空旗舰版/"
    ),

    # 1.2 同义词识别
    TestCase(
        id="PROD-004",
        name="同义词 - aws发票云",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="aws发票云影像功能怎么使用？",
        expected_behaviors=[
            "识别 aws发票云 = 标准版发票云",
            "识别功能模块：影像",
            "搜索标准版影像相关文档"
        ],
        expected_product="标准版发票云",
        expected_module="影像",
        notes="aws发票云 是标准版的同义词"
    ),

    TestCase(
        id="PROD-005",
        name="同义词 - 星瀚",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="星瀚的基础配置在哪里？",
        expected_behaviors=[
            "识别 星瀚 = 星瀚旗舰版发票云",
            "搜索星瀚相关配置目录"
        ],
        expected_product="星瀚旗舰版发票云",
        notes="简称'星瀚'应识别为星瀚旗舰版"
    ),

    TestCase(
        id="PROD-006",
        name="同义词 - 海外发票/国际版",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="国际版发票怎么开？",
        expected_behaviors=[
            "识别 国际版 = 海外发票",
            "搜索海外发票相关文档",
            "注意海外发票目录可能不完整"
        ],
        expected_product="海外发票",
        notes="海外发票/国际版 FAQ目录尚未建立"
    ),

    # 1.3 产品混淆风险
    TestCase(
        id="PROD-007",
        name="混淆风险 - 星空企业版 vs 星空旗舰版",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="星空企业版开票怎么配置？",
        expected_behaviors=[
            "识别可能混淆：星空企业版 与 星空旗舰版 不同",
            "主动提醒用户确认产品版本",
            "注意：星空企业版 使用的是标准版发票云，而非星空旗舰版"
        ],
        expected_output_not_contains=["星空旗舰版"],
        notes="星空企业版使用标准版发票云，不是星空旗舰版"
    ),

    # 1.4 缺少产品信息
    TestCase(
        id="PROD-008",
        name="缺少产品 - 如何开票",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="如何开票？",
        expected_behaviors=[
            "识别问题不完整（缺少产品线）",
            "使用询问模板询问用户产品版本",
            "不应直接猜测或搜索所有产品"
        ],
        expected_output_contains=["请问您使用的是哪个产品"],
        notes="应触发产品询问流程"
    ),

    TestCase(
        id="PROD-009",
        name="缺少产品 - 收票勾选流程",
        category=TestCategory.PRODUCT_RECOGNITION,
        query="收票勾选流程是什么？",
        expected_behaviors=[
            "识别问题不完整（缺少产品线）",
            "询问用户具体产品版本",
            "提供选项：标准版、星瀚旗舰版、星空旗舰版等"
        ]
    ),

    # ============================================================
    # 二、目录定位测试（验证能否根据问题语义选择正确目录）
    # ============================================================

    # 2.1 配置类问题
    TestCase(
        id="DIR-001",
        name="配置类 - 产品初始化配置",
        category=TestCategory.DIRECTORY_LOCATION,
        query="星瀚旗舰版发票云初始化配置步骤是什么？",
        expected_behaviors=[
            "识别为配置类问题",
            "优先搜索 06-构建阶段/产品初始化配置/星瀚发票云（旗舰版）/"
        ],
        expected_directory="产品与交付知识/06-构建阶段/产品初始化配置/星瀚发票云（旗舰版）/"
    ),

    # 2.2 问题排查类
    TestCase(
        id="DIR-002",
        name="排查类 - 开票报错",
        category=TestCategory.DIRECTORY_LOCATION,
        query="标准版开票报错'税号不存在'怎么办？",
        expected_behaviors=[
            "识别为问题排查类",
            "优先搜索 11-常见问题/标准版发票云问题/",
            "或搜索 一问一答/标准版/开票.md"
        ],
        expected_directory="产品与交付知识/11-常见问题/标准版发票云问题/"
    ),

    TestCase(
        id="DIR-003",
        name="排查类 - 收票异常",
        category=TestCategory.DIRECTORY_LOCATION,
        query="星空旗舰版收票失败，提示'发票不存在'",
        expected_behaviors=[
            "识别为问题排查类",
            "搜索 11-常见问题/星空旗舰版/收票管理FAQ.md"
        ],
        expected_directory="产品与交付知识/11-常见问题/星空旗舰版/"
    ),

    # 2.3 版本更新类
    TestCase(
        id="DIR-004",
        name="版本类 - 新功能说明",
        category=TestCategory.DIRECTORY_LOCATION,
        query="星瀚发票云 V8.0.2 有什么新功能？",
        expected_behaviors=[
            "识别为版本发布问题",
            "搜索 01-交付赋能/产品知识/产品发版说明/星瀚发票云/V8.0/"
        ],
        expected_directory="产品与交付知识/01-交付赋能/产品知识/产品发版说明/星瀚发票云/V8.0/"
    ),

    TestCase(
        id="DIR-005",
        name="版本类 - 迭代升级",
        category=TestCategory.DIRECTORY_LOCATION,
        query="星空旗舰版发票云最近有什么更新？",
        expected_behaviors=[
            "识别为版本发布问题",
            "搜索产品发版说明/星空旗舰版发票云/"
        ],
        expected_directory="产品与交付知识/01-交付赋能/产品知识/产品发版说明/星空旗舰版发票云/"
    ),

    # 2.4 操作步骤类
    TestCase(
        id="DIR-006",
        name="操作类 - 功能操作指南",
        category=TestCategory.DIRECTORY_LOCATION,
        query="标准版发票云如何操作红冲？",
        expected_behaviors=[
            "识别为操作步骤类问题",
            "搜索功能说明手册或操作手册",
            "或搜索一问一答"
        ],
        expected_directory="产品与交付知识/01-交付赋能/产品知识/功能说明手册_操作手册/"
    ),

    # 2.5 快速问答类
    TestCase(
        id="DIR-007",
        name="快速问答 - 简单问题",
        category=TestCategory.DIRECTORY_LOCATION,
        query="星瀚开票时发票类型有哪些？",
        expected_behaviors=[
            "识别为快速查询类型",
            "可搜索 一问一答/星瀚旗舰版/开票.md",
            "或 11-常见问题/星瀚旗舰版/"
        ]
    ),

    # ============================================================
    # 三、辅助系统测试
    # ============================================================

    TestCase(
        id="AUX-001",
        name="辅助系统 - 乐企配置",
        category=TestCategory.AUXILIARY_SYSTEMS,
        query="乐企通道如何配置？",
        expected_behaviors=[
            "识别为辅助系统问题（乐企）",
            "搜索 11-常见问题/乐企问题/",
            "不需要询问产品线（乐企是独立系统）"
        ],
        expected_directory="产品与交付知识/11-常见问题/乐企问题/"
    ),

    TestCase(
        id="AUX-002",
        name="辅助系统 - 乐企自用 vs 联用",
        category=TestCategory.AUXILIARY_SYSTEMS,
        query="乐企自用通道和联用通道有什么区别？",
        expected_behaviors=[
            "识别为乐企相关问题",
            "搜索乐企自用FAQ和联用FAQ",
            "区分两种通道的差异"
        ]
    ),

    TestCase(
        id="AUX-003",
        name="辅助系统 - 订单系统（EOP同义词）",
        category=TestCategory.AUXILIARY_SYSTEMS,
        query="EOP系统怎么查看订单状态？",
        expected_behaviors=[
            "识别 EOP = 发票云订单系统",
            "搜索 11-常见问题/发票云订单问题/",
            "正确处理同义词"
        ],
        expected_directory="产品与交付知识/11-常见问题/发票云订单问题/",
        notes="EOP/运营系统 都是发票云订单系统的同义词"
    ),

    TestCase(
        id="AUX-004",
        name="辅助系统 - 运营系统（同义词）",
        category=TestCategory.AUXILIARY_SYSTEMS,
        query="运营系统里如何激活权益？",
        expected_behaviors=[
            "识别 运营系统 = 发票云订单系统",
            "搜索 发票云订单问题/激活与权益FAQ.md"
        ]
    ),

    TestCase(
        id="AUX-005",
        name="辅助系统 - RPA通道",
        category=TestCategory.AUXILIARY_SYSTEMS,
        query="RPA通道配置失败怎么办？",
        expected_behaviors=[
            "识别 RPA通道 = 电子税局通道管理",
            "搜索税局通道相关文档",
            "注意：RPA通道FAQ目录可能不存在"
        ],
        notes="RPA通道FAQ目录标注为'—'，需动态搜索"
    ),

    # ============================================================
    # 四、外部系统对接测试（动态发现策略）
    # ============================================================

    TestCase(
        id="EXT-001",
        name="外部系统 - EAS对接",
        category=TestCategory.MULTI_SYSTEM,
        query="EAS如何对接标准版发票云开票？",
        expected_behaviors=[
            "使用动态发现策略搜索对接目录",
            "搜索 find -name '*EAS*对接*'",
            "找到后使用该目录文档"
        ],
        notes="外部系统对接关系不做硬编码"
    ),

    TestCase(
        id="EXT-002",
        name="外部系统 - 星空企业版对接",
        category=TestCategory.MULTI_SYSTEM,
        query="星空企业版如何对接发票云收票？",
        expected_behaviors=[
            "识别：星空企业版 使用标准版发票云",
            "搜索标准版发票云问题/星空企业版收票管理FAQ.md"
        ]
    ),

    # ============================================================
    # 五、规则遵循测试
    # ============================================================

    # 5.1 标准话术测试
    TestCase(
        id="RULE-001",
        name="标准话术 - 不存在的外部系统",
        category=TestCategory.RULE_COMPLIANCE,
        query="发票云怎么对接火星系统？",
        expected_behaviors=[
            "搜索知识库",
            "未找到相关信息",
            "返回标准话术：'抱歉，在发票云知识库没找到本答案，请联系发票云人工客服做支持。'",
            "不添加任何补充内容（如'不过...'、'但是...'）"
        ],
        expected_output_contains=["抱歉，在发票云知识库没找到本答案"],
        expected_output_not_contains=["不过", "但是", "您也可以", "虽然没找到"]
    ),

    TestCase(
        id="RULE-002",
        name="标准话术 - 完全不相关的问题",
        category=TestCategory.RULE_COMPLIANCE,
        query="太阳系统怎么集成发票云？",
        expected_behaviors=[
            "识别为不存在的系统",
            "搜索无结果",
            "只返回标准话术，立即结束"
        ],
        expected_output_contains=["抱歉，在发票云知识库没找到本答案"],
        expected_output_not_contains=["不过", "但是", "您也可以"]
    ),

    TestCase(
        id="RULE-003",
        name="标准话术 - 搜索无结果",
        category=TestCategory.RULE_COMPLIANCE,
        query="发票云支持区块链开票吗？",
        expected_behaviors=[
            "搜索知识库",
            "如无结果，返回标准话术",
            "不编造或推测答案"
        ]
    ),

    # 5.2 来源引用测试
    TestCase(
        id="RULE-004",
        name="来源引用 - 正确格式",
        category=TestCategory.RULE_COMPLIANCE,
        query="星瀚旗舰版基础配置FAQ",
        expected_behaviors=[
            "搜索并找到文档",
            "提取 YAML frontmatter 的 title 和 url",
            "按格式引用：[title](url)"
        ],
        expected_output_contains=["根据", "http"],
        notes="检查是否正确引用来源链接"
    ),

    # 5.3 产品区分测试
    TestCase(
        id="RULE-005",
        name="产品区分 - 不混合答案",
        category=TestCategory.RULE_COMPLIANCE,
        query="星空旗舰版开票配置FAQ",
        expected_behaviors=[
            "只返回星空旗舰版的内容",
            "明确标注产品归属",
            "不混合星瀚或标准版的内容"
        ],
        expected_output_contains=["星空旗舰版"],
        expected_output_not_contains=["星瀚旗舰版", "标准版"]
    ),

    # ============================================================
    # 六、边界情况测试
    # ============================================================

    TestCase(
        id="EDGE-001",
        name="边界 - 多产品同时提及",
        category=TestCategory.EDGE_CASES,
        query="标准版和星瀚旗舰版的开票有什么区别？",
        expected_behaviors=[
            "识别为比较类问题",
            "分别搜索两个产品的相关文档",
            "输出时明确区分不同产品的内容"
        ]
    ),

    TestCase(
        id="EDGE-002",
        name="边界 - 跨系统协作",
        category=TestCategory.EDGE_CASES,
        query="乐企通道开票失败，发票云显示什么错误码？",
        expected_behaviors=[
            "识别涉及多系统：乐企 + 发票云",
            "明确各系统职责",
            "综合搜索相关文档"
        ]
    ),

    TestCase(
        id="EDGE-003",
        name="边界 - 私有化部署",
        category=TestCategory.EDGE_CASES,
        query="星瀚发票云私有化部署如何运维？",
        expected_behaviors=[
            "识别为私有化运维问题",
            "搜索 06-构建阶段/私有化运维部署/星瀚发票云（私有化）/",
            "或 11-常见问题/私有化运维/"
        ],
        expected_directory="产品与交付知识/06-构建阶段/私有化运维部署/星瀚发票云（私有化）/"
    ),

    TestCase(
        id="EDGE-004",
        name="边界 - 领域知识",
        category=TestCategory.EDGE_CASES,
        query="什么是数电票？",
        expected_behaviors=[
            "识别为发票领域知识问题",
            "搜索 01-交付赋能/发票领域知识/",
            "不需要特定产品线"
        ]
    ),

    TestCase(
        id="EDGE-005",
        name="边界 - API集成问题",
        category=TestCategory.DIRECTORY_LOCATION,
        query="开票接口的API文档在哪里？",
        expected_behaviors=[
            "识别为API相关问题",
            "优先搜索 API文档/ 目录",
            "如无结果，搜索FAQ中接口对接内容"
        ],
        expected_directory="API文档/"
    ),

    TestCase(
        id="EDGE-006",
        name="边界 - 接口对接FAQ",
        category=TestCategory.DIRECTORY_LOCATION,
        query="星瀚旗舰版接口对接报错 401",
        expected_behaviors=[
            "识别为接口对接问题",
            "搜索 11-常见问题/星瀚旗舰版/接口对接FAQ.md"
        ]
    ),

    # ============================================================
    # 七、综合场景测试
    # ============================================================

    TestCase(
        id="COMP-001",
        name="综合 - 完整工作流",
        category=TestCategory.EDGE_CASES,
        query="我想在星瀚旗舰版发票云中配置收票勾选功能，需要哪些步骤？",
        expected_behaviors=[
            "识别产品：星瀚旗舰版",
            "识别功能：收票",
            "识别意图：配置步骤",
            "搜索配置目录或FAQ",
            "输出包含具体操作步骤"
        ]
    ),

    TestCase(
        id="COMP-002",
        name="综合 - 报错排查完整流程",
        category=TestCategory.EDGE_CASES,
        query="标准版开票时报错'税控服务器连接失败'，如何排查？",
        expected_behaviors=[
            "识别产品：标准版",
            "识别为问题排查",
            "搜索标准版FAQ",
            "提供排查步骤",
            "如有风险提醒相关注意事项"
        ]
    ),

    TestCase(
        id="COMP-003",
        name="综合 - 需要扩展搜索",
        category=TestCategory.EDGE_CASES,
        query="星空旗舰版收票勾选后如何同步到ERP？",
        expected_behaviors=[
            "首先搜索收票相关目录",
            "如需扩展，搜索对接相关文档",
            "综合多个来源回答"
        ]
    ),
]


# ============================================================
# 按类别分组的测试用例
# ============================================================

def get_test_cases_by_category(category: TestCategory) -> list[TestCase]:
    """按类别获取测试用例"""
    return [tc for tc in TEST_CASES if tc.category == category]


def get_all_test_ids() -> list[str]:
    """获取所有测试ID"""
    return [tc.id for tc in TEST_CASES]


def get_test_case_by_id(test_id: str) -> Optional[TestCase]:
    """按ID获取测试用例"""
    for tc in TEST_CASES:
        if tc.id == test_id:
            return tc
    return None


# ============================================================
# 测试统计信息
# ============================================================

def print_test_summary():
    """打印测试用例统计"""
    print(f"\n{'='*60}")
    print("发票云客服 Skill 测试问题集统计")
    print(f"{'='*60}")
    print(f"总测试用例数: {len(TEST_CASES)}")
    print(f"\n按类别分布:")

    for category in TestCategory:
        cases = get_test_cases_by_category(category)
        print(f"  {category.value}: {len(cases)} 个")

    print(f"\n测试用例列表:")
    for tc in TEST_CASES:
        print(f"  [{tc.id}] {tc.name}")


if __name__ == "__main__":
    print_test_summary()
