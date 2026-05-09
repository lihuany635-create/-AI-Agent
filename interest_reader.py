"""
interest_reader.py — 立AI 興趣資料夾系統
功能：
  1. 掃描 interest/ 資料夾，讀取各種格式的檔案
  2. 用 AI 整理摘要，存進知識庫
  3. 發現有趣問題時，主動找使用者聊
  4. 支援：txt, md, pdf, 圖片, docx, url 網址
"""

import json
import logging
import pathlib
import threading
import time
from datetime import datetime

import requests

logger = logging.getLogger("interest_reader")

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
BASE_DIR     = pathlib.Path(__file__).parent
INTEREST_DIR = BASE_DIR / "interest"          # 你丟資料的地方
STATE_FILE   = BASE_DIR / "workshop_data" / "memory" / "interest_state.json"
INTEREST_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

OLLAMA_URL      = "http://localhost:11434"
KNOWLEDGE_URL   = "http://localhost:7861"
CHECK_INTERVAL  = 60   # 每分鐘掃一次資料夾
READ_INTERVAL   = 180  # 每 3 分鐘讀一篇

SUPPORT_EXTS = {".txt", ".md", ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".url"}

# ── 狀態管理 ──────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"read_files": [], "pending": [], "last_read": ""}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"read_files": [], "pending": [], "last_read": ""}

def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 檔案內容讀取 ──────────────────────────────────────────────────────────────

def _read_txt(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:6000]

def _read_md(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")[:6000]

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH   = r"C:\poppler\poppler-26.02.0\Library\bin"

def _read_pdf(path: pathlib.Path) -> str:
    import os

    # 第一層：pypdf 抽文字（文字版 PDF）
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        pages  = [p.extract_text() or "" for p in reader.pages]
        text   = "\n\n".join(pages).strip()
        if len(text) > 50:
            return text[:6000]
    except Exception:
        pass

    # 第二層：pdf2image + tesseract OCR（掃描版）
    try:
        import subprocess, tempfile
        from pdf2image import convert_from_path
        images = convert_from_path(str(path), dpi=150, first_page=1, last_page=10,
                                   poppler_path=POPPLER_PATH)
        _env = {**os.environ, "PATH": os.environ.get("PATH","") + ";C:\\Program Files\\Tesseract-OCR"}
        texts = []
        for img in images:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_name = tmp.name
            img.save(tmp_name, "PNG")
            try:
                r = subprocess.run(
                    [TESSERACT_PATH, tmp_name, "stdout", "-l", "chi_tra+eng", "--psm", "3"],
                    capture_output=True, timeout=60, env=_env,
                    encoding="utf-8", errors="replace"
                )
                if r.stdout and r.stdout.strip():
                    texts.append(r.stdout.strip())
            finally:
                try: os.unlink(tmp_name)
                except Exception: pass
        if texts:
            return "\n\n".join(texts)[:6000]
    except Exception as e:
        logger.warning(f"OCR 失敗：{e}")

    # 第三層：llava 視覺模型
    try:
        import base64, io
        from pdf2image import convert_from_path
        images = convert_from_path(str(path), dpi=100, first_page=1, last_page=3,
                                   poppler_path=POPPLER_PATH)
        descriptions = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_data = base64.b64encode(buf.getvalue()).decode()
            r = requests.post(f"{OLLAMA_URL}/api/generate", json={
                "model": "llava:7b",
                "prompt": "請完整描述這張圖片的所有文字內容，用繁體中文回答。",
                "images": [img_data],
                "stream": False,
            }, timeout=180)
            desc = r.json().get("response", "").strip()
            if desc:
                descriptions.append(desc)
        if descriptions:
            return "\n\n".join(descriptions)[:6000]
    except Exception as e:
        logger.warning(f"視覺模型失敗：{e}")

    return "PDF 內容無法提取（嘗試了 pypdf、tesseract、llava）"

def _read_image(path: pathlib.Path) -> str:
    try:
        import base64
        img_data = base64.b64encode(path.read_bytes()).decode()
        r = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": "llava:7b",
            "prompt": "請完整描述這張圖片的所有文字內容和視覺資訊，用繁體中文回答。",
            "images": [img_data],
            "stream": False,
        }, timeout=120)
        return r.json().get("response", "").strip()[:4000]
    except Exception as e:
        return f"圖片讀取失敗：{e}"

def _read_docx(path: pathlib.Path) -> str:
    try:
        import zipfile, re
        with zipfile.ZipFile(str(path)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", xml)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000]
    except Exception as e:
        return f"DOCX 讀取失敗：{e}"

def _read_url(path: pathlib.Path) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        # 找第一個 http 開頭的網址
        import re
        urls = re.findall(r"https?://\S+", content)
        if not urls:
            return content[:3000]
        url = urls[0]
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        # 簡單抽取文字
        html = r.text
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return f"來源：{url}\n\n{text[:5000]}"
    except Exception as e:
        return f"網址讀取失敗：{e}"

def read_file(path: pathlib.Path) -> str:
    ext = path.suffix.lower()
    if ext in (".txt",):     return _read_txt(path)
    if ext in (".md",):      return _read_md(path)
    if ext in (".pdf",):     return _read_pdf(path)
    if ext in (".jpg", ".jpeg", ".png", ".webp"): return _read_image(path)
    if ext in (".docx",):    return _read_docx(path)
    if ext in (".url",):     return _read_url(path)
    return ""

# ── AI 閱讀與整理 ─────────────────────────────────────────────────────────────

def _pick_model() -> str:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        for prefer in ["gpt-oss:20b", "qwen2.5:14b", "qwen2.5:7b", "gemma3:4b"]:
            stem = prefer.split(":")[0]
            for m in models:
                if m.startswith(stem):
                    return m
    except Exception:
        pass
    return "gemma3:4b"

def analyze_file(filename: str, content: str) -> dict:
    """用 AI 分析檔案內容，產出摘要和可能的問題。"""
    model = _pick_model()
    prompt = f"""你是立AI，正在閱讀使用者放在興趣資料夾的資料。
請分析以下內容，輸出嚴格 JSON：

{{
  "title": "這份資料的標題或主題（一句話）",
  "summary": "內容摘要（100字以內，繁體中文）",
  "interesting_points": ["值得注意的重點1", "值得注意的重點2"],
  "question": "你想和使用者聊的問題（一句話，可以是你的疑問或想深入討論的點，沒有就給空字串）",
  "tags": ["標籤1", "標籤2", "標籤3"]
}}

檔名：{filename}
內容：
{content[:3000]}"""

    try:
        # 優先用小模型分析，避免逾時
        analyze_model = model
        try:
            r2 = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            all_models = [m["name"] for m in r2.json().get("models", [])]
            for fast in ["gemma3:4b", "qwen2.5:1.5b", "deepseek-r1:1.5b"]:
                stem = fast.split(":")[0]
                for m in all_models:
                    if m.startswith(stem):
                        analyze_model = m
                        break
                if analyze_model != model:
                    break
        except Exception:
            pass

        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": analyze_model,
            "messages": [
                {"role": "system", "content": "只輸出 JSON，第一個字必須是 {"},
                {"role": "user",   "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 500},
        }, timeout=300)
        raw = r.json().get("message", {}).get("content", "").strip()
        import re
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1:
            raise ValueError("no JSON")
        return json.loads(raw[start:end])
    except Exception as e:
        logger.warning(f"AI 分析失敗：{e}")
        return {
            "title":              filename,
            "summary":            content[:200],
            "interesting_points": [],
            "question":           "",
            "tags":               ["興趣資料夾"],
        }

def _save_to_knowledge(analysis: dict, filename: str):
    """把分析結果存進知識庫，失敗時存本地備用。"""
    payload = {
        "title":     f"[興趣] {analysis.get('title', filename)}",
        "content":   analysis.get("summary", ""),
        "tags":      analysis.get("tags", []) + ["興趣資料夾", "立AI閱讀"],
        "importance": 6,
    }
    try:
        r = requests.post(f"{KNOWLEDGE_URL}/api/add/text", json=payload, timeout=10)
        if r.status_code == 200:
            logger.info(f"[InterestReader] 已存入知識庫：{filename}")
            return
    except Exception:
        pass
    # knowledge_ui 未就緒，存本地
    backup = STATE_FILE.parent / "pending_knowledge.json"
    try:
        pending = json.loads(backup.read_text(encoding="utf-8")) if backup.exists() else []
        pending.append(payload)
        backup.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[InterestReader] 暫存本地：{filename}")
    except Exception as e:
        logger.warning(f"[InterestReader] 本地暫存失敗：{e}")

def _notify_question(filename: str, question: str, summary: str):
    """發現有趣問題時，通知立AI 找使用者聊。失敗則重試。"""
    payload = {"filename": filename, "question": question, "summary": summary}
    for _ in range(3):
        try:
            r = requests.post(f"{KNOWLEDGE_URL}/api/interest_question", json=payload, timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(10)
    # 存到待通知佇列
    backup = STATE_FILE.parent / "pending_questions.json"
    try:
        pending = json.loads(backup.read_text(encoding="utf-8")) if backup.exists() else []
        pending.append(payload)
        backup.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# ── 掃描與閱讀主迴圈 ─────────────────────────────────────────────────────────

def scan_new_files(state: dict) -> list[pathlib.Path]:
    """掃描 interest/ 資料夾，找出還沒讀過的檔案。"""
    read_set = set(state.get("read_files", []))
    new_files = []
    for path in sorted(INTEREST_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORT_EXTS:
            continue
        rel = str(path.relative_to(INTEREST_DIR))
        if rel not in read_set:
            new_files.append(path)
    return new_files

def read_one(path: pathlib.Path, state: dict):
    """讀一個檔案，分析後存知識庫，有問題就通知立AI。"""
    filename = path.name
    logger.info(f"[InterestReader] 開始閱讀：{filename}")
    
    content = read_file(path)
    if not content or len(content) < 10:
        logger.warning(f"[InterestReader] 內容為空，跳過：{filename}")
        return

    analysis = analyze_file(filename, content)
    _save_to_knowledge(analysis, filename)

    # 有問題就通知立AI
    question = analysis.get("question", "")
    if question:
        _notify_question(filename, question, analysis.get("summary", ""))
        logger.info(f"[InterestReader] 發現問題，通知立AI：{question[:60]}")

    # 標記已讀
    rel = str(path.relative_to(INTEREST_DIR))
    state.setdefault("read_files", []).append(rel)
    state["last_read"] = datetime.now().isoformat()
    _save_state(state)

# ── 背景執行緒 ────────────────────────────────────────────────────────────────

_running  = False
_paused   = False  # True 時暫停閱讀，優先處理使用者

def pause():
    """使用者有需要時暫停自主閱讀。"""
    global _paused
    _paused = True
    logger.info("[InterestReader] 暫停閱讀，等待使用者")

def resume():
    """使用者事情處理完後繼續閱讀。"""
    global _paused
    _paused = False
    logger.info("[InterestReader] 繼續閱讀")

def start_background():
    """啟動背景閱讀執行緒。"""
    global _running
    if _running:
        return
    _running = True
    threading.Thread(target=_reader_loop, daemon=True).start()
    logger.info("[InterestReader] 背景閱讀已啟動")

def _reader_loop():
    """主閱讀迴圈：定期掃描並閱讀新檔案。"""
    global _running, _paused
    last_check = 0
    pending    = []

    while _running:
        now = time.time()

        # 使用者有需要時暫停
        if _paused:
            time.sleep(5)
            continue

        # 定期掃描新檔案
        if now - last_check > CHECK_INTERVAL:
            state    = _load_state()
            new      = scan_new_files(state)
            pending  = new + [p for p in pending if p not in new]
            last_check = now
            if new:
                logger.info(f"[InterestReader] 發現 {len(new)} 個新檔案")

        # 讀一個檔案
        if pending and not _paused:
            path  = pending.pop(0)
            state = _load_state()
            try:
                read_one(path, state)
            except Exception as e:
                logger.error(f"[InterestReader] 讀取失敗：{path.name}：{e}")
            time.sleep(READ_INTERVAL)
        else:
            time.sleep(10)

def stop():
    global _running
    _running = False

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(_sys.stderr, "reconfigure"):
        _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print(f"📚 興趣資料夾：{INTEREST_DIR}")
    print(f"   支援格式：{', '.join(SUPPORT_EXTS)}")
    
    state     = _load_state()
    new_files = scan_new_files(state)
    print(f"   未讀檔案：{len(new_files)} 個")
    
    if new_files:
        print("\n開始閱讀...")
        for path in new_files[:3]:
            read_one(path, state)
    else:
        print("   沒有新檔案，把東西丟進 interest/ 資料夾試試！")
