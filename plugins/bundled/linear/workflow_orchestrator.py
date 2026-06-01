"""Linear product-workflow 编排器 — Python 侧逐步调用各 skill。"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from api.constants import AGENT_CWD
from api.models.requests import QueryRequest
from api.services.agent_service import AgentService

logger = logging.getLogger(__name__)

# ── 路由决策矩阵 ──────────────────────────────────────────────────────────────
# key: (lane, category)  category: "rule"|"ux"|"tech"|"new"|"extend"|"config"|"perf"|"exp"|None
# value: 步骤列表，"②lite" 表示 lite 模式，"③cond" 表示条件执行
_ROUTE_MAP: Dict[Tuple[str, Optional[str]], List[str]] = {
    # Fast Lane
    ("fast", "rule"): ["①", "②lite", "③cond", "⑤"],
    ("fast", "ux"): ["①", "⑤lite"],
    ("fast", "tech"): ["①", "⑤lite"],
    ("fast", None): ["①", "⑤lite"],
    # Standard Lane
    ("standard", "new"): ["①", "②", "③", "⑤"],
    ("standard", "extend"): ["①", "②", "③", "⑤"],
    ("standard", "config"): ["①", "②", "⑤"],
    ("standard", "rule"): ["①", "②lite", "③cond", "⑤"],
    ("standard", "ux"): ["①", "⑤lite"],
    ("standard", "tech"): ["①", "⑤lite"],
    ("standard", "perf"): ["①", "⑤lite"],
    ("standard", "exp"): ["①", "④", "⑤lite"],
    # Deep Lane
    ("deep", "new"): ["①", "②", "③", "④", "⑤"],
    ("deep", "extend"): ["①", "②", "③", "④", "⑤"],
    ("deep", "config"): ["①", "②", "③", "⑤"],
    ("deep", "rule"): ["①", "②lite", "③cond", "⑤"],
    ("deep", "ux"): ["①", "⑤lite"],
    ("deep", "tech"): ["①", "⑤lite"],
    ("deep", "perf"): ["①", "⑤lite"],
    ("deep", "exp"): ["①", "④", "⑤lite"],
}

# 需求分类关键词 → category key
_CATEGORY_KEYWORDS = {
    "rule": ["规则类", "rule", "校验", "规则"],
    "ux": ["体验类", "ux", "体验", "UI", "页面", "样式", "交互", "文案"],
    "tech": ["技术类", "tech", "超时", "崩溃", "性能", "500"],
    "new": ["新增业务能力", "新增"],
    "extend": ["扩展现有能力", "扩展"],
    "config": ["配置变更", "配置"],
    "perf": ["性能优化", "性能"],
    "exp": ["体验优化"],
}


# ── 数据结构 ──────────────────────────────────────────────────────────────────


@dataclass
class SkillInvokeResult:
    success: bool
    final_output: str = ""
    error: str = ""


@dataclass
class StepResult:
    success: bool
    exit_status: str = ""  # DONE / DONE_WITH_GAPS / NEEDS_HUMAN / BLOCKED
    output_files: List[Path] = field(default_factory=list)
    header: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class OrchestratorResult:
    success: bool
    lane: str = ""
    steps_executed: List[str] = field(default_factory=list)
    prd_files: List[Path] = field(default_factory=list)
    error: str = ""
    split_required: bool = False  # 大需求需要拆子 Issue，父流程在此结束


# ── 编排器 ────────────────────────────────────────────────────────────────────


class WorkflowOrchestrator:
    """逐步调用 product-workflow 的 5 个 skill，每步完成后回调进度通知。"""

    def __init__(
        self,
        agent_service: AgentService,
        output_dir: Path,
        cancel_event: asyncio.Event,
        on_step_start: Optional[Callable[[str], Any]] = None,
        on_step_done: Optional[Callable[[str, StepResult], Any]] = None,
        on_tool_use: Optional[Callable[[str, str], Any]] = None,
        on_thought: Optional[Callable[[str], Any]] = None,
        wait_for_human: Optional[Callable[[str], Any]] = None,
    ):
        self.agent_service = agent_service
        self.output_dir = output_dir
        self.cancel_event = cancel_event
        # 回调：步骤开始/完成、工具调用、思考过程
        self.on_step_start = on_step_start
        self.on_step_done = on_step_done
        self.on_tool_use = on_tool_use
        self.on_thought = on_thought
        # 等待人工介入的协程（由 handler 注入）
        self.wait_for_human = wait_for_human

        # 运行时状态
        self._issue_id: Optional[str] = None
        self._feature_id: Optional[str] = None  # 子 Issue 当前特性 ID
        self._route: List[str] = []
        self._step1_header: Dict[str, Any] = {}

    # ── 主入口 ────────────────────────────────────────────────────────────────

    async def run(
        self,
        prompt: str,
        issue_id: Optional[str] = None,
        start_from_step: int = 1,
        parent_context_dir: Optional[Path] = None,
        feature_id: Optional[str] = None,
    ) -> OrchestratorResult:
        self._issue_id = issue_id
        self._feature_id = feature_id  # 子 Issue 当前特性 ID，供 ④⑤ step 使用
        steps_executed: List[str] = []
        prd_files: List[Path] = []

        if start_from_step <= 1:
            # ① 需求分析（必经）
            await self._notify_step_start("① 需求分析")
            step1 = await self._run_step1(prompt)
            steps_executed.append("①")
            await self._notify_step_done("① 需求分析", step1)

            if not step1.success:
                return OrchestratorResult(
                    success=False, steps_executed=steps_executed, error=step1.error
                )

            if self.cancel_event.is_set():
                return OrchestratorResult(
                    success=False, steps_executed=steps_executed, error="已取消"
                )

            # 根据 ① 产物决定路由
            self._route = self._determine_route(step1.header)
            logger.info(
                f"[Orchestrator] route={self._route}, lane={step1.header.get('lane')}"
            )

            # ② 本体映射（条件执行）
            if "②" in self._route or "②lite" in self._route:
                lite = "②lite" in self._route
                label = "② 本体映射（lite）" if lite else "② 本体映射"
                await self._notify_step_start(label)
                step2 = await self._run_step2(lite=lite)
                steps_executed.append("②lite" if lite else "②")
                await self._notify_step_done(label, step2)

                if not step2.success:
                    return OrchestratorResult(
                        success=False, steps_executed=steps_executed, error=step2.error
                    )

                if self.cancel_event.is_set():
                    return OrchestratorResult(
                        success=False, steps_executed=steps_executed, error="已取消"
                    )

                # 大需求检测：② 完成后提前返回，由 handler 拆子 Issue
                if self._is_large_req():
                    logger.info(
                        f"[Orchestrator] Large req detected, split_required. "
                        f"lane={self._step1_header.get('lane')}, route={self._route}"
                    )
                    return OrchestratorResult(
                        success=True,
                        lane=self._step1_header.get("lane", ""),
                        steps_executed=steps_executed,
                        split_required=True,
                    )

                # ③ 本体更新 Gate（条件执行）
                need_step3 = self._need_step3(step2)
                if need_step3:
                    await self._notify_step_start("③ 本体检查")
                    step3 = await self._run_step3()
                    steps_executed.append("③")
                    await self._notify_step_done("③ 本体检查", step3)

                    if not step3.success:
                        return OrchestratorResult(
                            success=False,
                            steps_executed=steps_executed,
                            error=step3.error,
                        )

                    if self.cancel_event.is_set():
                        return OrchestratorResult(
                            success=False, steps_executed=steps_executed, error="已取消"
                        )

        else:
            # 子 Issue 流程：从父 Issue 产物恢复上下文
            if parent_context_dir:
                self._step1_header = self._read_yaml_header_from(
                    parent_context_dir, "*_需求分析报告.md"
                )
                # 将父 Issue 的 ② 产物复制到子 Issue 输出目录，供 ③ skill 使用
                self._copy_parent_step2_artifacts(parent_context_dir, feature_id)
            # 子 Issue 固定跑 ③④⑤（由 handler 根据特性决定是否需要 ④）
            self._route = ["③", "④", "⑤"]

            # ③ 本体检查
            if start_from_step <= 3:
                await self._notify_step_start("③ 本体检查")
                step3 = await self._run_step3()
                steps_executed.append("③")
                await self._notify_step_done("③ 本体检查", step3)

                if not step3.success:
                    return OrchestratorResult(
                        success=False, steps_executed=steps_executed, error=step3.error
                    )

                if self.cancel_event.is_set():
                    return OrchestratorResult(
                        success=False, steps_executed=steps_executed, error="已取消"
                    )

        # ④ 页面设计（条件执行）
        if "④" in self._route:
            await self._notify_step_start("④ 页面设计")
            step4 = await self._run_step4()
            steps_executed.append("④")
            await self._notify_step_done("④ 页面设计", step4)

            if not step4.success:
                return OrchestratorResult(
                    success=False, steps_executed=steps_executed, error=step4.error
                )

            if self.cancel_event.is_set():
                return OrchestratorResult(
                    success=False, steps_executed=steps_executed, error="已取消"
                )

        # ⑤ PRD 生成（必经）
        await self._notify_step_start("⑤ 生成 PRD")
        step5 = await self._run_step5()
        steps_executed.append("⑤")
        await self._notify_step_done("⑤ 生成 PRD", step5)

        if not step5.success:
            return OrchestratorResult(
                success=False, steps_executed=steps_executed, error=step5.error
            )

        prd_files = list(self.output_dir.glob("*_产品规格说明书_v*.md"))
        if not prd_files:
            prd_files = list(self.output_dir.glob("*_用户故事设计规格说明书_v*.md"))

        return OrchestratorResult(
            success=True,
            lane=self._step1_header.get("lane", ""),
            steps_executed=steps_executed,
            prd_files=prd_files,
        )

    # ── 各步骤 ────────────────────────────────────────────────────────────────

    async def _run_step1(self, prompt: str) -> StepResult:
        rel_dir = self._rel_output_dir()
        skill_prompt = f"{prompt} {rel_dir} --skip-confirm"
        result = await self._invoke_skill("requirement-analysis", skill_prompt)
        if not result.success:
            return StepResult(success=False, error=result.error)

        header = self._read_yaml_header("*_需求分析报告.md")
        self._step1_header = header
        exit_status = header.get("skill-exit-status", "")
        if exit_status == "BLOCKED":
            return StepResult(
                success=False,
                exit_status=exit_status,
                header=header,
                error=header.get("skill-exit-detail", "需求分析被阻断"),
            )

        files = list(self.output_dir.glob("*_需求分析报告.md"))
        return StepResult(
            success=True, exit_status=exit_status, output_files=files, header=header
        )

    async def _run_step2(self, lite: bool = False) -> StepResult:
        # 找到 ① 产物路径
        report_files = list(self.output_dir.glob("*_需求分析报告.md"))
        if not report_files:
            return StepResult(success=False, error="找不到需求分析报告，无法执行 ②")

        rel_report = report_files[0].relative_to(AGENT_CWD)
        rel_dir = self._rel_output_dir()
        skill_prompt = f"{rel_report} {rel_dir} --skip-confirm"
        if lite:
            skill_prompt += " --lite"

        result = await self._invoke_skill("ontology-context", skill_prompt)
        if not result.success:
            return StepResult(success=False, error=result.error)

        # lite 模式产物：*_本体映射摘要.md；完整模式：*_特性清单.md
        if lite:
            header = self._read_yaml_header("*_本体映射摘要.md")
            files = list(self.output_dir.glob("*_本体映射摘要.md"))
        else:
            header = self._read_yaml_header("*_特性清单.md")
            files = list(self.output_dir.glob("*_特性清单.md")) + list(
                self.output_dir.glob("*_本体映射报告.md")
            )

        exit_status = header.get("skill-exit-status", "")
        if exit_status == "BLOCKED":
            return StepResult(
                success=False,
                exit_status=exit_status,
                header=header,
                error=header.get("skill-exit-detail", "本体映射被阻断"),
            )

        return StepResult(
            success=True, exit_status=exit_status, output_files=files, header=header
        )

    async def _run_step3(self) -> StepResult:
        rel_dir = self._rel_output_dir()
        # 自动化场景：先尝试不加 --force-pass，遇到 NEEDS_HUMAN 再等待用户
        skill_prompt = f"{rel_dir}"
        result = await self._invoke_skill("ontology-update", skill_prompt)
        if not result.success:
            return StepResult(success=False, error=result.error)

        header = self._read_yaml_header("*_本体检查报告.md")
        exit_status = header.get("skill-exit-status", "")
        files = list(self.output_dir.glob("*_本体检查报告.md"))

        if exit_status == "NEEDS_HUMAN":
            # 通知用户，等待 prompted 回复
            coverage_rate = header.get("coverage-rate", "?")
            coverage_tier = header.get("coverage-tier", "?")
            gaps = header.get("gaps-remaining", "?")
            msg = (
                f"③ 本体检查完成。覆盖度：{coverage_rate}%（{coverage_tier}），"
                f"仍缺失 {gaps} 项。\n\n"
                "请选择：\n"
                "  [a] 人工补齐后回复「继续」重新检查\n"
                "  [b] 继续生成 PRD（PRD 中标注待补充）\n"
                "  [c] 终止工作流"
            )
            user_reply = await self._ask_human(msg)
            if user_reply is None or user_reply.strip().lower() in (
                "c",
                "终止",
                "取消",
            ):
                return StepResult(
                    success=False,
                    exit_status="BLOCKED",
                    header=header,
                    error="用户选择终止工作流",
                )
            if user_reply.strip().lower() in ("a", "重新检查", "继续检查"):
                # 重新执行 ③
                return await self._run_step3()
            # [b] 或其他：强制放行
            result2 = await self._invoke_skill(
                "ontology-update", f"{rel_dir} --force-pass"
            )
            if not result2.success:
                return StepResult(success=False, error=result2.error)
            header = self._read_yaml_header("*_本体检查报告.md")
            exit_status = header.get("skill-exit-status", "DONE_PARTIAL")

        if exit_status == "BLOCKED":
            return StepResult(
                success=False,
                exit_status=exit_status,
                header=header,
                error=header.get("skill-exit-detail", "本体检查被阻断"),
            )

        return StepResult(
            success=True, exit_status=exit_status, output_files=files, header=header
        )

    async def _run_step4(self) -> StepResult:
        issue_id = self._issue_id or self.output_dir.name
        rel_dir = self._rel_output_dir()
        skill_prompt = f"{issue_id} {rel_dir}"
        if self._feature_id:
            skill_prompt += f" --feature={self._feature_id}"
        result = await self._invoke_skill("prototype-design", skill_prompt)
        if not result.success:
            return StepResult(success=False, error=result.error)

        files = list(self.output_dir.glob("*_页面设计说明.md"))
        header = self._read_yaml_header("*_页面设计说明.md") if files else {}
        exit_status = header.get("skill-exit-status", "DONE")
        return StepResult(
            success=True, exit_status=exit_status, output_files=files, header=header
        )

    async def _run_step5(self) -> StepResult:
        rel_dir = self._rel_output_dir()
        feature_suffix = f" --feature={self._feature_id}" if self._feature_id else ""
        feature_id = self._feature_id or self._issue_id or self.output_dir.name

        # PRD-A（有映射报告）走分段生成，避免单次推理过长触发 504
        mapping_files = list(self.output_dir.glob("*_本体映射报告.md"))
        use_split = bool(mapping_files)

        if use_split:
            # 第一段：生成第一章（特性概述）+ 第二章（用户故事）+ 第三章（校验规则说明）
            part1_file = f"{feature_id}_prd_part1.md"
            part1_prompt = (
                f"{rel_dir} --context={rel_dir} --skip-confirm{feature_suffix}\n\n"
                f"【严格分段生成指令 - 第一段，必须严格遵守】\n"
                f"⚠️ 本次调用是三段式 PRD 生成的第一段，任务边界严格限定如下：\n"
                f"1. 读取上游产物（需求分析报告、特性清单、本体映射报告）\n"
                f"2. 只生成第一章（特性概述）、第二章（用户故事）、第三章（校验规则说明）的 Markdown 内容\n"
                f"3. 将上述内容写入临时文件：{rel_dir}/{part1_file}\n"
                f"4. ⛔ 写完文件后立即停止，输出'第一段已写入 {part1_file}'，然后结束\n"
                f"5. ⛔ 禁止继续生成第四章及之后的内容\n"
                f"6. ⛔ 禁止生成最终 PRD 文件\n"
                f"7. ⛔ 禁止执行质量自检\n"
                f"临时文件不需要 frontmatter 和版本记录，只需要章节内容。"
            )
            result1 = await self._invoke_skill("generate-prd", part1_prompt)
            if not result1.success:
                return StepResult(
                    success=False, error=f"PRD 第一段生成失败: {result1.error}"
                )

            if self.cancel_event.is_set():
                return StepResult(success=False, error="已取消")

            # 第二段：生成第四章（接口/页面规格）+ 第五章（地区差异）+ 第六章（附录）
            part2_file = f"{feature_id}_prd_part2.md"
            part2_prompt = (
                f"{rel_dir} --context={rel_dir} --skip-confirm{feature_suffix}\n\n"
                f"【严格分段生成指令 - 第二段，必须严格遵守】\n"
                f"⚠️ 本次调用是三段式 PRD 生成的第二段，任务边界严格限定如下：\n"
                f"1. 读取上游产物（本体映射报告、本体检查报告、页面设计文件）\n"
                f"2. 只生成第四章（根据 interaction_type：接口规格/页面交互规格/批处理规格/事件规格）、"
                f"第五章（地区差异说明）、第六章（附录：产品本体对应实现关系）的 Markdown 内容\n"
                f"3. 将上述内容写入临时文件：{rel_dir}/{part2_file}\n"
                f"4. ⛔ 写完文件后立即停止，输出'第二段已写入 {part2_file}'，然后结束\n"
                f"5. ⛔ 禁止生成第一至三章内容\n"
                f"6. ⛔ 禁止生成最终 PRD 文件\n"
                f"7. ⛔ 禁止执行质量自检\n"
                f"临时文件不需要 frontmatter 和版本记录，只需要章节内容。"
            )
            result2 = await self._invoke_skill("generate-prd", part2_prompt)
            if not result2.success:
                return StepResult(
                    success=False, error=f"PRD 第二段生成失败: {result2.error}"
                )

            if self.cancel_event.is_set():
                return StepResult(success=False, error="已取消")

            # 第三段：Python 直接合并临时文件，完全绕过 Agent 避免 504
            part1_path = self.output_dir / part1_file
            part2_path = self.output_dir / part2_file
            try:
                part1_content = part1_path.read_text(encoding="utf-8")
                part2_content = part2_path.read_text(encoding="utf-8")
            except Exception as e:
                return StepResult(success=False, error=f"读取临时文件失败: {e}")

            import datetime

            today = datetime.date.today().strftime("%Y-%m-%d")
            frontmatter = (
                f"---\n"
                f"skill-exit-status: DONE\n"
                f"skill-exit-detail: PRD 分段生成完成\n"
                f"generated-by: workflow-orchestrator\n"
                f"feature-id: {feature_id}\n"
                f"date: {today}\n"
                f"---\n\n"
            )
            version_record = (
                f"## 版本记录\n\n"
                f"| 版本 | 日期 | 更新摘要 |\n"
                f"| ---- | ---------- | ------ |\n"
                f"| v1.0 | {today} | 初版 |\n\n"
                f"---\n\n"
            )
            merged_content = (
                frontmatter
                + version_record
                + part1_content
                + "\n\n---\n\n"
                + part2_content
            )

            # 从 part1 第一行提取标题作为文件名依据（格式：# {特性ID} · {特性名称}）
            prd_filename = f"{feature_id}_产品规格说明书_v1.0.md"
            final_prd_path = self.output_dir / prd_filename
            try:
                final_prd_path.write_text(merged_content, encoding="utf-8")
                part1_path.unlink(missing_ok=True)
                part2_path.unlink(missing_ok=True)
                logger.info(f"[Orchestrator] PRD 合并完成（Python）: {prd_filename}")
            except Exception as e:
                return StepResult(success=False, error=f"写入最终 PRD 失败: {e}")

            if self.cancel_event.is_set():
                return StepResult(success=False, error="已取消")
        else:
            # PRD-B（无映射报告）内容较少，直接一次生成
            skill_prompt = (
                f"{rel_dir} --context={rel_dir} --skip-confirm{feature_suffix}"
            )
            result = await self._invoke_skill("generate-prd", skill_prompt)
            if not result.success:
                return StepResult(success=False, error=result.error)

        files = list(self.output_dir.glob("*_产品规格说明书_v*.md"))
        if not files:
            # 兼容旧命名
            files = list(self.output_dir.glob("*_用户故事设计规格说明书_v*.md"))
        header = self._read_yaml_header("*_产品规格说明书_v*.md") if files else {}
        if not header:
            header = self._read_yaml_header("*_用户故事设计规格说明书_v*.md")
        exit_status = header.get("skill-exit-status", "DONE")

        if exit_status == "BLOCKED":
            return StepResult(
                success=False,
                exit_status=exit_status,
                header=header,
                error=header.get("skill-exit-detail", "PRD 生成被阻断"),
            )

        return StepResult(
            success=True, exit_status=exit_status, output_files=files, header=header
        )

    # ── 核心工具方法 ──────────────────────────────────────────────────────────

    # skill 名称 → 实际目录路径映射（避免 Agent 因数字前缀 Glob 失败而全局搜索）
    _SKILL_PATH_MAP = {
        "requirement-analysis": ".claude/skills/01-requirement-analysis/SKILL.md",
        "ontology-context": ".claude/skills/02-ontology-context/SKILL.md",
        "ontology-update": ".claude/skills/03-ontology-update/SKILL.md",
        "prototype-design": ".claude/skills/04-prototype-design/SKILL.md",
        "generate-prd": ".claude/skills/05-generate-prd/SKILL.md",
    }

    async def _invoke_skill(self, skill_name: str, prompt: str) -> SkillInvokeResult:
        """调用单个 skill，消费 SSE 事件流，返回最终结果。"""
        # 在 prompt 前注入强制约束，确保 Agent 严格遵守 SKILL.md 的产物命名规范
        enforced_prompt = (
            f"严格按照 SKILL.md 中 produces 声明的文件命名规范输出产物文件，"
            f"禁止使用任何其他文件名。\n\n"
            f"{prompt}"
        )
        # skill 路径提示通过 metadata 传入，避免混入 user_prompt 干扰参数解析
        skill_path = self._SKILL_PATH_MAP.get(skill_name, "")
        metadata: dict = {}
        if skill_path:
            metadata["skill_file_hint"] = (
                f"Skill 文件路径：{skill_path}，直接 Read 该文件，不要 Glob 搜索。"
            )
        request = QueryRequest(
            prompt=enforced_prompt,
            skill=skill_name,
            language="中文",
            metadata=metadata if metadata else None,
            # 不传 session_id，每步独立会话
        )

        final_output = ""
        try:
            async for event in self.agent_service.process_query(request):
                if self.cancel_event.is_set():
                    return SkillInvokeResult(success=False, error="已取消")

                event_type = event.get("type") or event.get("event", "")
                data = event.get("data", {})
                if isinstance(data, str):
                    import json

                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}

                if event_type == "tool_use":
                    tool_name = data.get("tool") or data.get("name", "")
                    tool_input = str(data.get("input", ""))[:100]
                    if self.on_tool_use:
                        try:
                            await self.on_tool_use(tool_name, tool_input)
                        except Exception:
                            pass

                elif event_type == "assistant_message":
                    text = data.get("text") or data.get("content", "")
                    if text and len(text) > 10 and self.on_thought:
                        try:
                            await self.on_thought(text[:500])
                        except Exception:
                            pass

                elif event_type == "result":
                    final_output = data.get("result", "")
                    is_error = data.get("is_error", False)
                    if is_error:
                        return SkillInvokeResult(
                            success=False, error=final_output or "skill 执行出错"
                        )

                elif event_type == "error":
                    error_msg = data.get("message", "未知错误")
                    logger.error(
                        f"[Orchestrator] skill={skill_name} error: {error_msg}"
                    )
                    return SkillInvokeResult(success=False, error=error_msg)

        except Exception as e:
            logger.error(
                f"[Orchestrator] skill={skill_name} exception: {e}", exc_info=True
            )
            return SkillInvokeResult(success=False, error=str(e))

        return SkillInvokeResult(success=True, final_output=final_output)

    def _read_yaml_header(self, pattern: str) -> Dict[str, Any]:
        """读取产物文件的 YAML frontmatter，返回 dict。"""
        files = list(self.output_dir.glob(pattern))
        if not files:
            return {}
        # 取最新的文件
        target = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[0]
        try:
            content = target.read_text(encoding="utf-8")
            # 提取 --- ... --- 之间的 YAML
            match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if match:
                return yaml.safe_load(match.group(1)) or {}
        except Exception as e:
            logger.warning(
                f"[Orchestrator] Failed to read YAML header from {target}: {e}"
            )
        return {}

    def _determine_route(self, header: Dict[str, Any]) -> List[str]:
        """根据 ① 产物 header 决定后续调用链。"""
        lane = (header.get("lane") or "standard").lower()
        category = self._extract_category(header)
        route = _ROUTE_MAP.get((lane, category)) or _ROUTE_MAP.get((lane, None))
        if route is None:
            # 兜底：standard 完整链路
            route = ["①", "②", "③", "⑤"]
        logger.info(f"[Orchestrator] lane={lane}, category={category}, route={route}")
        return route

    def _extract_category(self, header: Dict[str, Any]) -> Optional[str]:
        """从 header 中提取需求分类 key。"""
        # bug-subtype 优先
        bug_subtype = header.get("bug-subtype", "")
        if bug_subtype in ("rule", "ux", "tech"):
            return bug_subtype

        # 从需求分类字段推断
        category_text = str(header.get("需求分类", "") or header.get("category", ""))
        for key, keywords in _CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in category_text:
                    return key
        return None

    def _need_step3(self, step2_result: StepResult) -> bool:
        """判断是否需要执行 ③。"""
        if "③" not in self._route and "③cond" not in self._route:
            return False
        exit_status = step2_result.exit_status
        bug_result = step2_result.header.get("bug-ontology-result", "")
        # lite 模式：HIT 跳过，PARTIAL/MISS 执行
        if bug_result:
            return bug_result in ("PARTIAL", "MISS")
        # 完整模式：DONE_WITH_GAPS 执行
        return exit_status == "DONE_WITH_GAPS"

    def _is_large_req(self) -> bool:
        """判断是否大需求（需要拆子 Issue）。

        条件：route 包含完整 ② 且满足以下任一：
        - lane=deep（无论 category）
        - lane=standard 且 category in new/extend
        """
        if "②" not in self._route:
            return False
        lane = (self._step1_header.get("lane") or "standard").lower()
        if lane == "deep":
            return True
        category = self._extract_category(self._step1_header)
        return lane == "standard" and category in ("new", "extend")

    def _read_yaml_header_from(self, directory: Path, pattern: str) -> Dict[str, Any]:
        """从指定目录读取产物文件的 YAML frontmatter。"""
        files = list(directory.glob(pattern))
        if not files:
            return {}
        target = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[0]
        try:
            content = target.read_text(encoding="utf-8")
            match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if match:
                return yaml.safe_load(match.group(1)) or {}
        except Exception as e:
            logger.warning(
                f"[Orchestrator] Failed to read YAML header from {target}: {e}"
            )
        return {}

    def _copy_parent_step2_artifacts(
        self, parent_context_dir: Path, feature_id: Optional[str] = None
    ) -> None:
        """将父 Issue 产物目录中的 ② 产物复制到子 Issue 输出目录，供 ③④⑤ skill 使用。

        复制：
        - *_需求分析报告.md（全量，⑤ skill 需要作为背景）
        - *_特性清单.md（全量，③④⑤ skill 需要作为背景）
        - {feature_id}_本体映射报告.md（只复制当前特性的）
        """
        import shutil

        copied = 0
        # 需求分析报告和特性清单全量复制（作为背景上下文）
        for pattern in ["*_需求分析报告.md", "*_特性清单.md"]:
            for src in parent_context_dir.glob(pattern):
                dst = self.output_dir / src.name
                if not dst.exists():
                    shutil.copy2(str(src), str(dst))
                    copied += 1

        # 本体映射报告只复制当前 feature_id 对应的文件
        if feature_id:
            for src in parent_context_dir.glob(f"{feature_id}_本体映射报告.md"):
                dst = self.output_dir / src.name
                if not dst.exists():
                    shutil.copy2(str(src), str(dst))
                    copied += 1
        else:
            # 没有 feature_id 时退回全量复制（兼容旧逻辑）
            for src in parent_context_dir.glob("*_本体映射报告.md"):
                dst = self.output_dir / src.name
                if not dst.exists():
                    shutil.copy2(str(src), str(dst))
                    copied += 1

        if copied:
            logger.info(
                f"[Orchestrator] Copied {copied} step2 artifacts from "
                f"{parent_context_dir.name} to {self.output_dir.name}"
                + (f" (feature_id={feature_id})" if feature_id else "")
            )

    def _rel_output_dir(self) -> Path:
        """返回相对于 AGENT_CWD 的输出目录路径。"""
        return self.output_dir.relative_to(AGENT_CWD)

    async def _ask_human(self, message: str) -> Optional[str]:
        """等待人工介入，返回用户回复。wait_for_human 由 handler 注入。"""
        if self.wait_for_human is None:
            logger.warning("[Orchestrator] wait_for_human not set, auto-continuing")
            return "b"
        try:
            return await self.wait_for_human(message)
        except Exception as e:
            logger.error(f"[Orchestrator] wait_for_human failed: {e}")
            return None

    # ── 回调通知 ──────────────────────────────────────────────────────────────

    async def _notify_step_start(self, label: str) -> None:
        if self.on_step_start:
            try:
                result = self.on_step_start(label)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    async def _notify_step_done(self, label: str, result: StepResult) -> None:
        if self.on_step_done:
            try:
                r = self.on_step_done(label, result)
                if asyncio.iscoroutine(r):
                    await r
            except Exception:
                pass
