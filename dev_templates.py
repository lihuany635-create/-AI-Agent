"""
dev_templates.py — 自主開發流程模板
每個模板：
  1. 定義結構化欄位
  2. from_claude_response() 從 Claude 自由回答解析填入
  3. to_prompt() 序列化成下一個 Claude 呼叫的 context
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json
import re
import datetime


# ── 模板 A：規格討論模板 ─────────────────────────────────────────────────────

@dataclass
class SpecTemplate:
    """
    第一輪 Claude 規格討論的輸出模板。
    立AI把 Claude 的自由格式回答解析成這個結構，
    作為第二輪（分組/步驟規劃）的輸入。
    """
    request:     str = ""           # 原始需求
    files:       List[str] = field(default_factory=list)   # 提到的 .py 檔名
    functions:   List[str] = field(default_factory=list)   # 提到的函式名
    deps:        List[str] = field(default_factory=list)   # 依賴套件
    groups_json: str = ""           # Claude 給的原始分組 JSON
    raw_spec:    str = ""           # Claude 的完整回答

    @classmethod
    def from_claude_response(cls, request: str, raw: str) -> "SpecTemplate":
        t = cls(request=request, raw_spec=raw)
        # 抽取 .py 檔名
        t.files = list(dict.fromkeys(re.findall(r'[a-zA-Z0-9_\-]+\.py', raw)))
        # 抽取函式名（def xxx 或 xxx()）
        t.functions = list(dict.fromkeys(
            re.findall(r'(?:def\s+)?([a-z_][a-zA-Z0-9_]+)\(\)', raw)
        ))[:20]
        # 抽取套件（import xxx）
        t.deps = list(dict.fromkeys(re.findall(r'(?:import|使用)\s+([a-zA-Z][a-zA-Z0-9_]+)', raw)))[:10]
        # 抽取分組 JSON
        gi = raw.rfind('{"groups"')
        if gi != -1:
            depth = 0
            for i, ch in enumerate(raw[gi:], gi):
                if ch == '{': depth += 1
                elif ch == '}': depth -= 1
                if depth == 0:
                    t.groups_json = raw[gi:i+1]
                    break
        return t

    def to_prompt(self) -> str:
        """序列化成下一個 Claude 呼叫的 context"""
        lines = [
            f"## 專案規格（已整理）",
            f"需求：{self.request}",
            f"檔案清單：{', '.join(self.files) if self.files else '待定'}",
            f"主要函式：{', '.join(self.functions[:8]) if self.functions else '待定'}",
            f"依賴套件：{', '.join(self.deps) if self.deps else '無'}",
        ]
        if self.groups_json:
            lines.append(f"分組規劃：{self.groups_json}")
        return "\n".join(lines)


# ── 模板 B：分組模板 ──────────────────────────────────────────────────────────

@dataclass
class GroupTemplate:
    """分組規劃模板，從 SpecTemplate 的 groups_json 解析"""
    key:   str = ""
    label: str = ""
    icon:  str = "📦"
    desc:  str = ""
    files: List[str] = field(default_factory=list)
    steps: List[int] = field(default_factory=list)  # 對應步驟索引


@dataclass
class PlanTemplate:
    """
    整個開發計畫模板，包含所有分組和步驟。
    作為每個步驟執行時的 context。
    """
    request:   str = ""
    groups:    List[GroupTemplate] = field(default_factory=list)
    steps:     List[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec='seconds'))

    @classmethod
    def from_spec_and_steps(cls, spec: SpecTemplate, steps: list, groups: list) -> "PlanTemplate":
        t = cls(request=spec.request)
        t.steps = steps
        for g in groups:
            gt = GroupTemplate(
                key=g.get("key", ""),
                label=g.get("label", ""),
                icon=g.get("icon", "📦"),
                desc=g.get("desc", ""),
                files=g.get("files", []),
            )
            t.groups.append(gt)
        return t

    def to_prompt(self, current_step_idx: int = 0) -> str:
        lines = [
            f"## 開發計畫",
            f"需求：{self.request}",
            f"總步驟：{len(self.steps)} 個",
            f"當前步驟：{current_step_idx + 1}/{len(self.steps)}",
            "",
            "已完成步驟：",
        ]
        for i, s in enumerate(self.steps[:current_step_idx]):
            lines.append(f"  ✓ {i+1}. [{s.get('action','create')}] {s.get('file','')} — {s.get('title','')}")
        if current_step_idx < len(self.steps):
            s = self.steps[current_step_idx]
            lines += [
                "",
                f"當前步驟：{current_step_idx+1}. [{s.get('action','create')}] {s.get('file','')}",
                f"目標：{s.get('desc','')}",
            ]
        return "\n".join(lines)


# ── 模板 C：生成請求模板 ─────────────────────────────────────────────────────

@dataclass
class GenRequestTemplate:
    """
    向 Claude 請求生成程式碼時的輸入模板。
    把計畫 context + 設計建議 + 需求整合成清晰的 prompt。
    """
    filename:     str = ""
    action:       str = "create"   # create / modify
    goal:         str = ""
    plan_context: str = ""         # PlanTemplate.to_prompt()
    guidance:     str = ""         # Claude 設計建議
    original_code:str = ""         # 修改時的原始碼摘要

    def to_prompt(self) -> str:
        lines = [self.plan_context, ""]
        if self.guidance:
            lines += ["## Claude 設計建議", self.guidance, ""]
        action_zh = "修改" if self.action == "modify" else "新增"
        lines += [
            f"## 生成任務",
            f"請{action_zh} {self.filename}",
            f"需求：{self.goal}",
        ]
        if self.original_code:
            lines += ["", f"現有程式碼摘要：\n{self.original_code[:400]}"]
        lines += [
            "",
            "規則：只輸出純 Python 程式碼，不要任何 markdown 標記或解釋。",
        ]
        return "\n".join(lines)


# ── 模板 D：測試結果模板 ─────────────────────────────────────────────────────

@dataclass
class TestResultTemplate:
    """測試結果模板，作為修正循環的輸入"""
    filename:      str = ""
    syntax_ok:     bool = True
    import_ok:     bool = True
    func_test_ok:  bool = True
    unittest_ok:   bool = True
    error_msg:     str = ""
    error_type:    str = ""   # SyntaxError / ImportError / RuntimeError / ...
    code_excerpt:  str = ""   # 問題程式碼片段

    @classmethod
    def from_test_output(cls, filename: str, code: str, test_ok: bool, output: str) -> "TestResultTemplate":
        t = cls(filename=filename, code_excerpt=code[:300])
        t.func_test_ok = test_ok
        t.error_msg = output
        # 判斷錯誤類型
        if "SyntaxError" in output:
            t.syntax_ok = False
            t.error_type = "SyntaxError"
        elif "ImportError" in output or "ModuleNotFoundError" in output:
            t.import_ok = False
            t.error_type = "ImportError"
        elif "RuntimeError" in output or "TypeError" in output or "AttributeError" in output:
            t.error_type = "RuntimeError"
        elif output:
            t.error_type = "UnknownError"
        return t

    def to_prompt(self) -> str:
        status = "✅ 通過" if self.func_test_ok else "❌ 失敗"
        lines = [
            f"## 測試結果",
            f"檔案：{self.filename}",
            f"功能測試：{status}",
        ]
        if not self.func_test_ok:
            lines += [
                f"錯誤類型：{self.error_type}",
                f"錯誤訊息：{self.error_msg[:300]}",
                f"問題程式碼片段：\n{self.code_excerpt}",
            ]
        return "\n".join(lines)


# ── 模板 E：修正請求模板 ─────────────────────────────────────────────────────

@dataclass
class FixRequestTemplate:
    """
    修正循環的輸入模板。
    把測試結果 + Claude 建議 + 當前程式碼整合成修正 prompt。
    """
    filename:    str = ""
    attempt:     int = 1
    test_result: Optional[TestResultTemplate] = None
    suggestion:  str = ""          # Claude 上一輪給的修正建議
    current_code:str = ""

    def to_prompt(self) -> str:
        lines = [
            f"## 修正任務（第 {self.attempt} 次）",
            f"檔案：{self.filename}",
            "",
        ]
        if self.test_result:
            lines += [self.test_result.to_prompt(), ""]
        if self.suggestion:
            lines += [f"## 上一輪修正建議", self.suggestion, ""]
        lines += [
            f"## 當前程式碼（需要修正）",
            f"{self.current_code[:800]}",
            "",
            "請修正上述錯誤，只輸出修正後的完整 Python 程式碼。",
        ]
        return "\n".join(lines)


# ── 模板 F：步驟完成記錄模板 ────────────────────────────────────────────────

@dataclass
class StepResultTemplate:
    """每個步驟完成後的記錄，作為學習總結和下一步的 context"""
    step_idx:     int = 0
    total_steps:  int = 0
    filename:     str = ""
    action:       str = "create"
    title:        str = ""
    lines:        int = 0
    test_ok:      bool = True
    unittest_info:str = ""
    fix_attempts: int = 0
    backup_path:  str = ""
    timestamp:    str = field(default_factory=lambda: datetime.datetime.now().strftime("%H:%M:%S"))

    def to_prompt(self) -> str:
        action_zh = "修改" if self.action == "modify" else "新增"
        test_str  = "✅ 通過" if self.test_ok else "⚠️ 略過"
        lines = [
            f"## 步驟 {self.step_idx+1}/{self.total_steps} 完成記錄",
            f"動作：{action_zh} {self.filename}（{self.lines} 行）",
            f"標題：{self.title}",
            f"測試：{test_str}",
        ]
        if self.fix_attempts > 0:
            lines.append(f"修正次數：{self.fix_attempts}")
        if self.unittest_info:
            lines.append(f"unittest：{self.unittest_info}")
        return "\n".join(lines)


# ── 模板 G：專案完成總結模板 ─────────────────────────────────────────────────

@dataclass
class ProjectSummaryTemplate:
    """整個專案完成後的總結，存入知識庫並推送"""
    request:      str = ""
    total_steps:  int = 0
    completed:    List[StepResultTemplate] = field(default_factory=list)
    packages:     List[str] = field(default_factory=list)
    timestamp:    str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec='seconds'))

    def to_prompt(self) -> str:
        lines = [
            f"## 專案完成總結",
            f"需求：{self.request}",
            f"完成步驟：{len(self.completed)}/{self.total_steps}",
            f"時間：{self.timestamp}",
            "",
            "完成清單：",
        ]
        for s in self.completed:
            action_zh = "修改" if s.action == "modify" else "新增"
            lines.append(f"  ✓ {s.step_idx+1}. {action_zh} {s.filename}（{s.lines} 行）")
        if self.packages:
            lines += ["", f"使用套件：{', '.join(self.packages)}"]
        return "\n".join(lines)

    def to_knowledge_entry(self) -> str:
        """存入 claude_knowledge 的格式"""
        return (
            f"[專案記錄] {self.request}\n"
            f"完成 {len(self.completed)} 個步驟：" +
            "、".join(s.filename for s in self.completed)
        )


# ── 統一管理 ─────────────────────────────────────────────────────────────────

class DevPipeline:
    """
    開發流程管道：管理所有模板的狀態和傳遞。
    self_dev_engine 透過這個類別存取當前流程狀態。
    """
    def __init__(self):
        self.spec:    Optional[SpecTemplate]    = None
        self.plan:    Optional[PlanTemplate]    = None
        self.results: List[StepResultTemplate] = []
        self.current_test: Optional[TestResultTemplate] = None

    def reset(self):
        self.__init__()

    def get_step_context(self, step_idx: int) -> str:
        """取得當前步驟的完整 context prompt"""
        parts = []
        if self.plan:
            parts.append(self.plan.to_prompt(step_idx))
        if self.results:
            parts.append("\n已完成步驟記錄：")
            for r in self.results[-3:]:  # 只取最近 3 個避免過長
                parts.append(r.to_prompt())
        return "\n\n".join(parts)

    def get_fix_context(self, filename: str, code: str, error: str, suggestion: str, attempt: int) -> str:
        """取得修正循環的 context prompt"""
        test_result = TestResultTemplate.from_test_output(filename, code, False, error)
        fix_req = FixRequestTemplate(
            filename=filename,
            attempt=attempt,
            test_result=test_result,
            suggestion=suggestion,
            current_code=code,
        )
        return fix_req.to_prompt()


# 模組層級單例
_pipeline: Optional[DevPipeline] = None

def get_pipeline() -> DevPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DevPipeline()
    return _pipeline
