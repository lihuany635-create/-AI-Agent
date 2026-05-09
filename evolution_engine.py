"""
evolution_engine.py — 立AI 自我進化引擎
功能：
  1. 缺口感知   — 監聽任務失敗，判斷是否為「能力缺口」
  2. 委託工坊   — 確認缺口後，自動向 workshop_ui 下單生產新器官
  3. 技能掃描   — 任務前掃描現有器官，找出可複用的技能段落

整合點：
  - workshop_ui.py / _execute_task     → detect_gap + commission_organ（失敗路徑）
  - workshop_ui.py / _execute_task     → scan_and_inject（生成程式碼前）
  - floating_ball.py / knowledge_ui.py → scan_and_inject（回應前）
"""

import json
import logging
import pathlib
import time
import threading
from typing import Optional

import requests

logger = logging.getLogger("evolution_engine")

# ── 路徑 ──────────────────────────────────────────────────────────────────────
_BASE_DIR     = pathlib.Path(__file__).parent
ASSEMBLED_DIR = _BASE_DIR / "workshop_data" / "assembled"
SKILLS_DIR    = _BASE_DIR / "workshop_data" / "skills"

# ── 服務端點 ──────────────────────────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434"
WORKSHOP_URL = "http://localhost:7862"

# 依序嘗試：大模型判斷更準，小模型當備援
_JUDGE_MODELS = ["gpt-oss:20b", "qwen2.5:14b", "qwen2.5:7b", "gemma3:4b"]

# ── 防遞迴冷卻 ────────────────────────────────────────────────────────────────
GAP_COOLDOWN_SECS = 1800          # 同一缺口類型 30 分鐘只下單一次
_gap_cooldown: dict[str, float] = {}
_cooldown_lock = threading.Lock()

# ── 常數 ──────────────────────────────────────────────────────────────────────
MAX_COMMISSION_DEPTH = 1          # 新器官本身失敗時不再遞迴委託


# ═══════════════════════════════════════════════════════════════════════════════
# 內部工具
# ═══════════════════════════════════════════════════════════════════════════════

def _pick_model() -> str:
    """從候選清單中選第一個 Ollama 已載入的模型。"""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        available = {m["name"] for m in r.json().get("models", [])}
        for m in _JUDGE_MODELS:
            stem = m.split(":")[0]
            for a in available:
                if a == m or a.startswith(stem):
                    return a
    except Exception:
        pass
    return _JUDGE_MODELS[-1]


def _ollama_once(system: str, prompt: str, temperature: float = 0.2,
                 timeout: Optional[int] = 60) -> str:
    """Non-streaming Ollama 呼叫，回傳完整字串。"""
    model = _pick_model()
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 600},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()


def _parse_json_safe(raw: str) -> Optional[dict]:
    """從可能夾雜說明文字的字串中抽取 JSON。"""
    import re
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _scan_skills_index() -> list[dict]:
    """
    讀取 skills/ 下所有 .json 描述，回傳 list[dict]。
    找不到就改掃 assembled/ 做輕量 AST 分析。
    """
    skills = []

    # 優先：skills/*.json（AI 生成的完整描述）
    if SKILLS_DIR.exists():
        for f in SKILLS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skills.append(data)
            except Exception:
                pass

    # 備援：assembled/*.py AST 分析
    if not skills and ASSEMBLED_DIR.exists():
        import ast
        for py in ASSEMBLED_DIR.glob("*.py"):
            try:
                src = py.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(src)
                doc = ast.get_docstring(tree) or ""
                funcs = [
                    n.name for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_")
                ]
                skills.append({
                    "name":        py.stem.replace("_", " "),
                    "filename":    py.name,
                    "description": doc.splitlines()[0] if doc else "",
                    "functions":   [{"name": fn} for fn in funcs],
                    "when_to_use": "",
                })
            except Exception:
                pass

    return skills


# ═══════════════════════════════════════════════════════════════════════════════
# ① 缺口感知
# ═══════════════════════════════════════════════════════════════════════════════

def detect_gap(
    task_title: str,
    error_msg: str,
    existing_skills: Optional[list[dict]] = None,
    depth: int = 0,
) -> Optional[dict]:
    """
    判斷任務失敗是否代表「能力缺口」（缺少某個器官）。

    參數：
      task_title      — 失敗任務的標題
      error_msg       — 執行錯誤訊息
      existing_skills — 現有器官列表（None 則自動掃描）
      depth           — 遞迴深度，超過 MAX_COMMISSION_DEPTH 直接回傳 None

    回傳：
      {"need": "技能名稱", "reason": "...", "spec": "詳細需求描述"}
      或 None（不是能力缺口 / 已有對應器官 / 冷卻中）
    """
    # 深度保護
    if depth > MAX_COMMISSION_DEPTH:
        logger.info("[EvolutionEngine] 超過最大委託深度，跳過缺口感知")
        return None

    if existing_skills is None:
        existing_skills = _scan_skills_index()

    skill_summary = "\n".join(
        f"- {s.get('name','')}: {s.get('description','')}"
        for s in existing_skills
    ) or "（目前沒有任何器官）"

    system = """你是 AI 系統的能力診斷師。
任務：判斷一個 Python 任務的失敗是否因為「缺少某種可複用的功能模組（器官）」。

輸出嚴格 JSON（不要其他文字）：
{
  "is_gap": true/false,
  "need": "缺少的功能模組名稱（英文，snake_case，例如：screen_capture）",
  "reason": "為什麼判斷是能力缺口（繁體中文，30字以內）",
  "spec": "這個功能模組需要做什麼（繁體中文，100字以內，包含輸入輸出）"
}

「能力缺口」的判斷標準：
- 錯誤是「找不到模組」、「函式不存在」、「沒有這個功能」
- 失敗原因不是語法錯誤、網路逾時、檔案路徑問題等暫時性錯誤
- 現有器官清單中沒有能解決問題的器官

「不是能力缺口」的情況：
- SyntaxError、IndentationError（程式碼本身有問題）
- FileNotFoundError、ConnectionError（環境或資源問題）
- timeout（執行太慢）
- 現有器官已經有類似功能"""

    prompt = f"""任務：{task_title}

錯誤訊息：
{error_msg[:500]}

現有器官清單：
{skill_summary}

請判斷這是否是「能力缺口」："""

    try:
        raw = _ollama_once(system, prompt, temperature=0.1)
        result = _parse_json_safe(raw)
        if not result:
            logger.warning(f"[EvolutionEngine] detect_gap 解析失敗：{raw[:200]}")
            return None

        if not result.get("is_gap"):
            logger.info(f"[EvolutionEngine] 判斷為暫時性錯誤，非能力缺口")
            return None

        need = result.get("need", "").strip()
        if not need:
            return None

        # 冷卻檢查
        with _cooldown_lock:
            last_time = _gap_cooldown.get(need, 0)
            now = time.time()
            if now - last_time < GAP_COOLDOWN_SECS:
                remaining = int((GAP_COOLDOWN_SECS - (now - last_time)) / 60)
                logger.info(
                    f"[EvolutionEngine] 缺口「{need}」冷卻中，還需 {remaining} 分鐘"
                )
                return None
            # 尚未冷卻 → 先不記錄，等 commission_organ 確認後再記錄

        logger.info(
            f"[EvolutionEngine] 偵測到能力缺口：{need}｜原因：{result.get('reason','')}"
        )
        return {
            "need":   need,
            "reason": result.get("reason", ""),
            "spec":   result.get("spec", ""),
            "depth":  depth,
        }

    except Exception as e:
        logger.error(f"[EvolutionEngine] detect_gap 例外：{e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ② 委託工坊
# ═══════════════════════════════════════════════════════════════════════════════

def commission_organ(gap: dict) -> Optional[str]:
    """
    向 workshop_ui 下單生產缺少的器官。

    參數：
      gap — detect_gap 回傳的 dict
            {"need": str, "reason": str, "spec": str, "depth": int}

    回傳：
      project_id（成功）或 None（失敗）
    """
    need  = gap.get("need", "")
    spec  = gap.get("spec", "")
    depth = gap.get("depth", 0)

    if not need or not spec:
        logger.warning("[EvolutionEngine] commission_organ：gap 資料不完整")
        return None

    # 記錄冷卻時間（下單後才鎖）
    with _cooldown_lock:
        _gap_cooldown[need] = time.time()

    # 組裝需求描述，傳給工坊
    requirement = (
        f"製作一個 Python 模組：{need}\n\n"
        f"功能需求：{spec}\n\n"
        f"【自動進化委託，請確保模組有清楚的 docstring 和公開函式介面】"
    )

    project_name = f"[自動進化] {need.replace('_', ' ')}"

    logger.info(f"[EvolutionEngine] 委託工坊生產：{project_name}")

    # 確認工坊在跑，沒在跑就自動啟動
    try:
        import socket as _sock
        with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as _s:
            workshop_offline = _s.connect_ex(('localhost', 7862)) != 0
        if workshop_offline:
            import subprocess, sys, pathlib, time
            workshop_path = pathlib.Path(__file__).parent / "workshop_ui.py"
            if workshop_path.exists():
                logger.info("[EvolutionEngine] 工坊未啟動，自動啟動中...")
                _popen_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    _popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                subprocess.Popen([sys.executable, str(workshop_path)], **_popen_kwargs)
                for _ in range(40):
                    time.sleep(1)
                    with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as _s:
                        if _s.connect_ex(('localhost', 7862)) == 0:
                            logger.info("[EvolutionEngine] 工坊已就緒")
                            break
    except Exception as _we:
        logger.warning(f"[EvolutionEngine] 工坊啟動檢查失敗：{_we}")

    try:
        # 呼叫 workshop_ui 的 /api/auto_create 端點
        r = requests.post(
            f"{WORKSHOP_URL}/api/auto_create",
            json={
                "name":        project_name,
                "requirement": requirement,
                # 完成後 callback 到進化引擎（可選）
                "callback_url": f"{WORKSHOP_URL}/api/evolution_callback",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        pid  = data.get("project_id")
        if pid:
            logger.info(
                f"[EvolutionEngine] 工坊已接單，project_id={pid[:8]}，"
                f"器官：{need}"
            )
            return pid
        else:
            logger.warning(f"[EvolutionEngine] 工坊回應異常：{data}")
            return None

    except requests.exceptions.ConnectionError:
        logger.warning("[EvolutionEngine] 工坊 (port 7862) 未啟動，跳過委託")
        return None
    except Exception as e:
        logger.error(f"[EvolutionEngine] commission_organ 例外：{e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ③ 技能掃描串接
# ═══════════════════════════════════════════════════════════════════════════════

def scan_and_inject(task_title: str, task_desc: str = "") -> str:
    """
    掃描現有器官，找出與當前任務相關的技能，
    回傳可直接放進 system prompt 的「可用技能」段落。

    若沒有相關技能，回傳空字串。

    流程：
      1. 關鍵字比對（快速篩選）
      2. Ollama 二次確認相關性（只對通過第一層的器官）
    """
    skills = _scan_skills_index()
    if not skills:
        return ""

    query = (task_title + " " + task_desc).lower()

    # ── 第一層：關鍵字比對 ────────────────────────────────────────────────────
    candidates = []
    for s in skills:
        score = 0
        name  = s.get("name", "").lower()
        desc  = s.get("description", "").lower()
        when  = s.get("when_to_use", "").lower()
        funcs = " ".join(
            f.get("name", "") + " " + f.get("description", "")
            for f in s.get("functions", [])
        ).lower()

        # 每個 query 詞匹配一分
        for word in query.split():
            if len(word) < 2:
                continue
            if word in name:
                score += 3   # 名稱命中權重最高
            if word in desc:
                score += 2
            if word in when:
                score += 2
            if word in funcs:
                score += 1

        if score > 0:
            candidates.append((score, s))

    if not candidates:
        return ""

    # 取前 5 名
    candidates.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in candidates[:5]]

    # ── 第二層：Ollama 相關性確認 ─────────────────────────────────────────────
    if len(top) > 1:
        top = _filter_by_llm(task_title, task_desc, top)

    if not top:
        return ""

    # ── 組裝注入段落 ──────────────────────────────────────────────────────────
    lines = ["【可用器官 — 優先 import 這些，不要重新實作】"]
    for s in top:
        filename = s.get("filename", "")
        name     = s.get("name", filename)
        desc     = s.get("description", "")
        funcs    = s.get("functions", [])

        lines.append(f"\n# {filename}  ← {desc}")
        for f in funcs[:6]:
            fn_name = f.get("name", "")
            fn_desc = f.get("description", "")
            if fn_name and not fn_name.startswith("_"):
                sig = f"  def {fn_name}(...)  # {fn_desc}" if fn_desc else f"  def {fn_name}(...)"
                lines.append(sig)

        # 使用範例
        example = s.get("example", "")
        if example and not example.startswith("python "):
            lines.append(f"  # 範例：{example}")

    return "\n".join(lines)


def _filter_by_llm(task_title: str, task_desc: str, candidates: list[dict]) -> list[dict]:
    """
    用 Ollama 二次確認候選器官的相關性，回傳真正相關的子集。
    失敗時回傳原候選清單（寬鬆降級）。
    """
    candidate_text = "\n".join(
        f"{i+1}. {s.get('name','')}: {s.get('description','')} "
        f"| 使用時機：{s.get('when_to_use','無')}"
        for i, s in enumerate(candidates)
    )

    system = """你是程式碼助手。判斷哪些現有器官對當前任務有幫助。

輸出嚴格 JSON（不要其他文字）：
{"relevant": [1, 3]}

只列出「真正有幫助」的器官編號，沒有相關的輸出空陣列：{"relevant": []}"""

    prompt = f"""當前任務：{task_title}
任務說明：{task_desc[:200]}

候選器官：
{candidate_text}

哪些器官對這個任務有幫助？（輸出編號陣列）："""

    try:
        raw    = _ollama_once(system, prompt, temperature=0.1, timeout=30)
        result = _parse_json_safe(raw)
        if not result:
            return candidates   # 解析失敗 → 保留全部

        relevant_idx = result.get("relevant", [])
        if not relevant_idx:
            return []

        filtered = []
        for idx in relevant_idx:
            if isinstance(idx, int) and 1 <= idx <= len(candidates):
                filtered.append(candidates[idx - 1])
        return filtered if filtered else candidates

    except Exception as e:
        logger.warning(f"[EvolutionEngine] LLM 篩選失敗，保留全部候選：{e}")
        return candidates


# ═══════════════════════════════════════════════════════════════════════════════
# 便利函式：並行觸發（給 workshop_ui 的失敗路徑呼叫）
# ═══════════════════════════════════════════════════════════════════════════════

def handle_task_failure(
    task_title: str,
    error_msg: str,
    existing_skills: Optional[list[dict]] = None,
    depth: int = 0,
) -> Optional[str]:
    """
    任務修復失敗後的統一進入點。
    在背景執行 detect_gap → commission_organ，不阻塞主執行緒。
    回傳 project_id（已下單）或 None。

    在 workshop_ui._execute_task 的 attempt >= 3 路徑呼叫：
        import threading
        from evolution_engine import handle_task_failure
        threading.Thread(
            target=handle_task_failure,
            args=(task['title'], error_msg),
            daemon=True
        ).start()
    """
    gap = detect_gap(task_title, error_msg, existing_skills, depth=depth)
    if gap is None:
        return None
    return commission_organ(gap)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 測試
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== Evolution Engine 診斷模式 ===\n")

    # 測試 scan_and_inject
    print("① 技能掃描測試")
    skills = _scan_skills_index()
    print(f"   找到 {len(skills)} 個器官")
    if skills:
        ctx = scan_and_inject("截圖工具", "擷取螢幕畫面")
        print(f"   scan_and_inject 結果（{len(ctx)} 字）：\n{ctx[:300] or '（無相關技能）'}")

    print("\n② detect_gap 測試")
    gap = detect_gap(
        task_title="截圖並儲存到指定路徑",
        error_msg="ModuleNotFoundError: No module named 'screen_capture'",
    )
    if gap:
        print(f"   偵測到缺口：{gap['need']}")
        print(f"   原因：{gap['reason']}")
        print(f"   規格：{gap['spec']}")
        print("\n   ⚠ 跳過 commission_organ（測試模式不實際下單）")
    else:
        print("   未偵測到能力缺口（可能是暫時性錯誤）")
