# knowledge_ui.py — 知識庫網頁介面
# 依賴：pip install flask
# 使用：python knowledge_ui.py
# 瀏覽器打開：http://localhost:7861

from flask import Flask, request, jsonify, render_template_string
from flask_socketio import SocketIO, emit
import pathlib, json, os, sqlite3, datetime, logging, traceback, base64, time as _time
import requests as req
from knowledge_store import get_store

# ── Logger ────────────────────────────────────────────────────────────────────
# ── 器官技能系統 ──────────────────────────────────────────────────────────────
try:
    from organ_skill_system import get_registry, refresh_registry, select_organ, execute_organ
    _SKILL_SYSTEM = True
except ImportError:
    _SKILL_SYSTEM = False
    def get_registry(): return None
    def refresh_registry(): pass
    def select_organ(q, r): return None
    def execute_organ(s, a=None): return {"success":False,"output":"","error":"技能系統未安裝"}
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("knowledge_ui")

# ── 程式碼規範庫 DB ───────────────────────────────────────────────────────────

_CODE_DB = pathlib.Path("knowledge_data/code_rules.db")
_CODE_DB.parent.mkdir(parents=True, exist_ok=True)

# ── 自學紀錄資料夾 ────────────────────────────────────────────────────────────
_LEARN_DIR = pathlib.Path("knowledge_data/learn_sessions")
_LEARN_DIR.mkdir(parents=True, exist_ok=True)

def _extract_tags_from_text(text: str, max_tags: int = 15) -> list[str]:
    """
    從文字中萃取關鍵標籤：
    - 以中文詞、英文單字、數字串為候選
    - 去掉常見停用詞
    - 依出現頻率排序，取前 max_tags 個
    """
    import re, collections
    # 停用詞
    STOPWORDS = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
        "一", "一個", "上", "也", "很", "到", "說", "要", "去", "你",
        "會", "著", "沒有", "看", "好", "自己", "這", "那", "但", "因為",
        "所以", "如果", "可以", "這個", "這樣", "什麼", "以及", "或者",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "can", "could", "should", "may", "might", "shall", "to", "of",
        "in", "on", "at", "for", "with", "by", "from", "as", "it",
        "its", "this", "that", "and", "or", "but", "not", "if", "so",
    }
    # 取中文詞（2字以上）和英文單字（3字以上）
    zh_words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
    en_words = re.findall(r'[A-Za-z]{3,}', text.lower())
    candidates = zh_words + en_words
    # 過濾停用詞
    filtered = [w for w in candidates if w not in STOPWORDS]
    # 頻率統計，取前 max_tags
    counter = collections.Counter(filtered)
    return [w for w, _ in counter.most_common(max_tags)]


def _save_learn_session(source_type: str, source_text: str,
                         report: str, model: str, focus: str = "") -> str:
    """
    把這次自學的原始資料 + 報告存成 JSON 檔。
    自動萃取標籤以加速後續搜尋。
    回傳 session_id。
    """
    now = datetime.datetime.now()
    session_id = now.strftime("%Y%m%d_%H%M%S")
    # 從 input + report + focus 萃取標籤
    combined = f"{focus} {source_text} {report}"
    tags = _extract_tags_from_text(combined, max_tags=15)
    data = {
        "session_id":  session_id,
        "timestamp":   now.isoformat(timespec="seconds"),
        "model":       model,
        "source_type": source_type,   # text / file / kb
        "focus":       focus,
        "tags":        tags,          # 自動萃取的關鍵標籤
        "input":       source_text,   # 原始輸入（文字）
        "report":      report,        # 立AI 的學習報告
    }
    path = _LEARN_DIR / f"{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[Learn] 紀錄已存：{path}，標籤：{tags[:5]}")
    return session_id

def _code_conn():
    conn = sqlite3.connect(_CODE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _code_init():
    with _code_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS code_rules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                priority    INTEGER DEFAULT 2,
                tags        TEXT DEFAULT '[]',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)

_code_init()

CODE_CATEGORIES = [
    {"id": "coding",    "label": "程式碼規則",   "icon": "📐", "desc": "編碼、命名、縮排、格式"},
    {"id": "arch",      "label": "架構方向",      "icon": "🏗",  "desc": "專案結構與設計原則"},
    {"id": "module",    "label": "模組規則",      "icon": "🔗",  "desc": "模組間的溝通與依賴規定"},
    {"id": "bug",       "label": "已知Bug與解法", "icon": "🐛",  "desc": "已知問題與修復方式"},
    {"id": "ai_rules",  "label": "AI行為準則",   "icon": "🤖",  "desc": "gpt-oss 等 AI 必須遵守的規定"},
]

PRIORITY_LABELS = {1: "🔴 必須遵守", 2: "🟡 建議", 3: "🟢 參考"}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'knowledge-li-ai-2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".avi", ".mkv"}

def _broadcast(event: str, data: dict):
    """廣播事件給所有連線的設備"""
    socketio.emit(event, data)

# ── HTML ─────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🏛 圖書館</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;600;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root {
  --bg: #0e0e0f;
  --surface: #16161a;
  --border: #2a2a32;
  --accent: #e8c547;
  --accent2: #7eb8f7;
  --text: #e8e6e0;
  --muted: #6b6b78;
  --danger: #f07070;
  --radius: 10px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Noto Serif TC', serif; min-height: 100vh; }

/* Layout */
.app { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; transition: grid-template-columns .25s ease; }
.app.collapsed { grid-template-columns: 48px 1fr; }
.sidebar { background: var(--surface); border-right: 1px solid var(--border); padding: 24px 0; display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh; overflow: hidden; transition: all .25s ease; width: 260px; min-width: 260px; }
.app.collapsed .sidebar { width: 48px; min-width: 48px; padding: 12px 0; }
.app.collapsed .sidebar .logo p,
.app.collapsed .sidebar .stats-row,
.app.collapsed .sidebar .nav-section,
.app.collapsed .sidebar .nav-item span:not(.badge),
.app.collapsed .sidebar .tag-cloud,
.app.collapsed .sidebar .badge { display: none; }
.app.collapsed .sidebar .nav-item { padding: 10px; justify-content: center; font-size: 1rem; }
.app.collapsed .sidebar .logo h1 { font-size: .7rem; letter-spacing: 0; }
.app.collapsed .sidebar .logo { padding: 0 8px 12px; text-align: center; }
.main { padding: 32px; overflow-y: auto; }

/* 收合按鈕 */
.sidebar-toggle { position: absolute; top: 16px; right: -14px; width: 28px; height: 28px; background: var(--surface); border: 1px solid var(--border); border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: .8rem; color: var(--muted); z-index: 10; transition: all .2s; box-shadow: 0 2px 8px rgba(0,0,0,.3); }
.sidebar-toggle:hover { color: var(--accent); border-color: var(--accent); }
.app.collapsed .sidebar-toggle { right: -14px; transform: rotate(180deg); }
.sidebar-inner { position: relative; display: flex; flex-direction: column; height: 100%; }

/* Sidebar */
.logo { padding: 0 20px 24px; border-bottom: 1px solid var(--border); }
.logo h1 { font-size: 1.1rem; font-weight: 900; color: var(--accent); letter-spacing: .05em; }
.logo p { font-size: .72rem; color: var(--muted); margin-top: 3px; font-family: 'JetBrains Mono', monospace; }
.sync-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--muted); margin-left: 6px; vertical-align: middle; transition: background .3s; }
.sync-dot.online { background: #4caf82; box-shadow: 0 0 6px #4caf82; }
.sync-dot.syncing { background: var(--accent); animation: spin .6s linear infinite; }
.sync-badge { font-size: .65rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; margin-left: 4px; vertical-align: middle; }
.toast { position: fixed; bottom: 90px; left: 50%; transform: translateX(-50%); background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 8px 18px; font-size: .8rem; color: var(--text); z-index: 300; opacity: 0; transition: opacity .3s; pointer-events: none; }
.toast.show { opacity: 1; }
/* 群組輪播 */
#group-modal { position: fixed; inset: 0; background: rgba(0,0,0,.95); z-index: 600; display: none; flex-direction: column; align-items: center; justify-content: center; }
#group-modal.open { display: flex; }
#group-carousel { position: relative; width: 90vw; max-width: 900px; display: flex; align-items: center; justify-content: center; }
#group-carousel img { max-width: 100%; max-height: 80vh; border-radius: 8px; object-fit: contain; box-shadow: 0 8px 60px rgba(0,0,0,.8); user-select: none; }
.carousel-btn { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,.1); border: none; color: #fff; font-size: 1.8rem; padding: 10px 16px; border-radius: 8px; cursor: pointer; z-index: 10; transition: background .15s; }
.carousel-btn:hover { background: rgba(232,197,71,.3); }
.carousel-btn.prev { left: -60px; }
.carousel-btn.next { right: -60px; }
#group-counter { color: rgba(255,255,255,.6); font-size: .85rem; margin-top: 14px; font-family: "JetBrains Mono", monospace; }
#group-title { color: #fff; font-size: 1rem; font-weight: 700; margin-bottom: 16px; }
#group-close { position: absolute; top: 20px; right: 28px; color: #fff; font-size: 2rem; cursor: pointer; background: none; border: none; opacity: .7; }
#group-close:hover { opacity: 1; }
#group-dots { display: flex; gap: 6px; margin-top: 12px; flex-wrap: wrap; justify-content: center; max-width: 400px; }
.g-dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,.3); cursor: pointer; transition: background .15s; }
.g-dot.active { background: var(--accent); }

/* Lightbox */
#lightbox { position: fixed; inset: 0; background: rgba(0,0,0,.92); z-index: 500; display: none; align-items: center; justify-content: center; cursor: zoom-out; }
#lightbox.open { display: flex; }
#lightbox img { max-width: 92vw; max-height: 92vh; border-radius: 8px; box-shadow: 0 8px 60px rgba(0,0,0,.8); object-fit: contain; }
#lightbox-close { position: absolute; top: 20px; right: 28px; color: #fff; font-size: 2rem; cursor: pointer; opacity: .7; background: none; border: none; line-height: 1; }
#lightbox-close:hover { opacity: 1; }

.stats-row { display: flex; gap: 8px; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.stat-chip { flex: 1; background: var(--bg); border-radius: 6px; padding: 8px; text-align: center; }
.stat-chip .n { font-size: 1.2rem; font-weight: 900; color: var(--accent); font-family: 'JetBrains Mono', monospace; }
.stat-chip .l { font-size: .62rem; color: var(--muted); margin-top: 2px; }

.nav-section { padding: 12px 20px 4px; font-size: .68rem; color: var(--muted); letter-spacing: .1em; text-transform: uppercase; }
.nav-item { padding: 8px 20px; cursor: pointer; font-size: .85rem; display: flex; justify-content: space-between; align-items: center; transition: background .15s; border-left: 3px solid transparent; }
.nav-item:hover { background: rgba(232,197,71,.05); }
.nav-item.active { background: rgba(232,197,71,.08); border-left-color: var(--accent); color: var(--accent); }
.nav-item .badge { background: var(--border); color: var(--muted); border-radius: 10px; padding: 1px 7px; font-size: .7rem; font-family: 'JetBrains Mono', monospace; }

.tag-cloud { padding: 8px 20px; display: flex; flex-wrap: wrap; gap: 6px; }
.tag-pill { background: var(--bg); border: 1px solid var(--border); border-radius: 20px; padding: 3px 10px; font-size: .72rem; cursor: pointer; transition: all .15s; color: var(--muted); }
.tag-pill:hover, .tag-pill.active { background: rgba(126,184,247,.1); border-color: var(--accent2); color: var(--accent2); }

/* Toolbar */
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.search-tags-bar { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; min-height: 0; }
.search-tag-chip { background: var(--bg); border: 1px solid var(--border); border-radius: 20px; padding: 4px 12px; font-size: .75rem; cursor: pointer; color: var(--muted); transition: all .15s; display: flex; align-items: center; gap: 5px; }
.search-tag-chip:hover { border-color: var(--accent); color: var(--accent); }
.search-tag-chip.active { background: rgba(232,197,71,.12); border-color: var(--accent); color: var(--accent); }
.search-tag-chip .rm { font-size: .85rem; opacity: .6; }
.search-tag-chip .rm:hover { opacity: 1; }
.search-tags-input-wrap { position: relative; }
.search-tags-input { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 4px 14px; font-size: .78rem; color: var(--text); outline: none; width: 160px; font-family: "Noto Serif TC", serif; transition: border .2s; }
.search-tags-input:focus { border-color: var(--accent); }
.search-tag-dropdown { position: absolute; top: 110%; left: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; min-width: 180px; max-height: 200px; overflow-y: auto; z-index: 50; display: none; box-shadow: 0 4px 20px rgba(0,0,0,.4); }
.search-tag-dropdown.open { display: block; }
.search-tag-opt { padding: 8px 14px; font-size: .82rem; cursor: pointer; color: var(--muted); }
.search-tag-opt:hover { background: rgba(232,197,71,.08); color: var(--accent); }
.search-box { flex: 1; min-width: 200px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 16px; color: var(--text); font-size: .9rem; font-family: 'Noto Serif TC', serif; transition: border .2s; }
.search-box:focus { outline: none; border-color: var(--accent); }
.sort-select { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 12px; color: var(--text); font-size: .85rem; cursor: pointer; }
.btn { border: none; border-radius: var(--radius); padding: 10px 18px; font-size: .85rem; cursor: pointer; font-family: 'Noto Serif TC', serif; transition: all .15s; font-weight: 600; }
.btn-primary { background: var(--accent); color: #0e0e0f; }
.btn-primary:hover { background: #f0d060; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
.btn-danger { background: transparent; border: 1px solid var(--danger); color: var(--danger); padding: 6px 12px; font-size: .78rem; }
.btn-danger:hover { background: rgba(240,112,112,.1); }

/* Cards */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; cursor: pointer; transition: all .2s; position: relative; }
.card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,.4); }
.card-type { font-size: .68rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
.card-type .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.card-type .dot.img { background: #7eb8f7; }
.card-type .dot.vid { background: #f07070; }
.card h3 { font-size: .95rem; font-weight: 600; margin-bottom: 6px; line-height: 1.4; }
.card .summary { font-size: .78rem; color: var(--muted); margin-bottom: 10px; line-height: 1.5; }
.card .thumb { width: 100%; height: 120px; object-fit: cover; border-radius: 6px; margin-bottom: 10px; background: var(--bg); }
.card-footer { display: flex; justify-content: space-between; align-items: center; }
.card-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.card-tag { background: var(--bg); border-radius: 4px; padding: 2px 7px; font-size: .68rem; color: var(--muted); }
.stars { color: var(--accent); font-size: .78rem; letter-spacing: -1px; }
.cat-badge { font-size: .68rem; color: var(--accent2); background: rgba(126,184,247,.1); border-radius: 4px; padding: 2px 7px; }

/* Empty */
.empty { text-align: center; padding: 80px 20px; color: var(--muted); }
.empty .icon { font-size: 3rem; margin-bottom: 16px; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 100; display: none; align-items: center; justify-content: center; padding: 20px; }
.modal-overlay.open { display: flex; }
.modal { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; width: 100%; max-width: 640px; max-height: 90vh; overflow-y: auto; }
.modal-header { padding: 20px 24px 0; display: flex; justify-content: space-between; align-items: center; }
.modal-header h2 { font-size: 1rem; font-weight: 900; }
.modal-close { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 1.4rem; line-height: 1; }
.modal-body { padding: 20px 24px 24px; }
.form-group { margin-bottom: 16px; }
.form-label { display: block; font-size: .78rem; color: var(--muted); margin-bottom: 6px; letter-spacing: .05em; }
.form-input, .form-textarea, .form-select { width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: .88rem; font-family: 'Noto Serif TC', serif; transition: border .2s; }
.form-textarea { min-height: 120px; resize: vertical; }
.form-input:focus, .form-textarea:focus, .form-select:focus { outline: none; border-color: var(--accent); }
.tabs { display: flex; gap: 4px; background: var(--bg); border-radius: 8px; padding: 4px; margin-bottom: 20px; }
.tab { flex: 1; padding: 8px; text-align: center; border-radius: 6px; cursor: pointer; font-size: .82rem; color: var(--muted); transition: all .15s; border: none; background: none; font-family: 'Noto Serif TC', serif; }
.tab.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,.3); }
.drop-zone { border: 2px dashed var(--border); border-radius: 10px; padding: 40px 20px; text-align: center; color: var(--muted); cursor: pointer; transition: all .2s; }
.drop-zone:hover, .drop-zone.dragover { border-color: var(--accent); color: var(--accent); background: rgba(232,197,71,.04); }
.drop-zone input { display: none; }
/* 圖片子模式切換 */
.img-mode-tabs { display: flex; gap: 6px; margin-bottom: 14px; }
.img-mode-btn { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg); color: var(--muted); font-size: .82rem; cursor: pointer; font-family: "Noto Serif TC", serif; transition: all .15s; text-align: center; }
.img-mode-btn:hover { border-color: var(--accent); color: var(--accent); }
.img-mode-btn.active { background: rgba(232,197,71,.1); border-color: var(--accent); color: var(--accent); font-weight: 600; }

/* 富文字編輯器 */
.editor-toolbar { display: flex; flex-wrap: wrap; gap: 2px; padding: 8px; background: var(--bg); border: 1px solid var(--border); border-bottom: none; border-radius: 8px 8px 0 0; }
.editor-btn { background: none; border: none; color: var(--muted); cursor: pointer; padding: 5px 8px; border-radius: 5px; font-size: .85rem; font-family: "Noto Serif TC", serif; transition: all .15s; line-height: 1; }
.editor-btn:hover { background: rgba(232,197,71,.1); color: var(--accent); }
.editor-btn.active { background: rgba(232,197,71,.15); color: var(--accent); }
.editor-sep { width: 1px; background: var(--border); margin: 2px 4px; }
.editor-body { min-height: 260px; max-height: 420px; overflow-y: auto; padding: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 0 0 8px 8px; color: var(--text); font-size: .9rem; line-height: 1.8; outline: none; font-family: "Noto Serif TC", serif; }
.editor-body:focus { border-color: var(--accent); }
.editor-body h1 { font-size: 1.4rem; font-weight: 900; margin: 8px 0 4px; color: var(--accent); }
.editor-body h2 { font-size: 1.15rem; font-weight: 700; margin: 6px 0 4px; }
.editor-body h3 { font-size: 1rem; font-weight: 600; margin: 4px 0; color: var(--accent2); }
.editor-body ul, .editor-body ol { padding-left: 20px; margin: 4px 0; }
.editor-body li { margin: 2px 0; }
.editor-body blockquote { border-left: 3px solid var(--accent); padding-left: 12px; color: var(--muted); margin: 6px 0; }
.editor-body code { background: rgba(255,255,255,.06); border-radius: 4px; padding: 1px 6px; font-family: "JetBrains Mono", monospace; font-size: .82rem; }
.editor-body img { max-width: 100%; border-radius: 6px; margin: 6px 0; cursor: pointer; }
.editor-body hr { border: none; border-top: 1px solid var(--border); margin: 12px 0; }
.editor-font-select { background: var(--bg); border: 1px solid var(--border); border-radius: 5px; color: var(--text); font-size: .78rem; padding: 3px 6px; cursor: pointer; }
.editor-font-select:focus { outline: none; }
.imp-row { display: flex; gap: 8px; }
.imp-btn { flex: 1; padding: 8px; text-align: center; border-radius: 6px; cursor: pointer; border: 1px solid var(--border); background: var(--bg); color: var(--muted); font-size: .82rem; transition: all .15s; }
.imp-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(232,197,71,.08); }
.loading { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; margin-left: 8px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 標籤選擇器 */
.tag-input-wrap { position: relative; }
.tag-chips { display: flex; flex-wrap: wrap; gap: 5px; padding: 6px 8px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; min-height: 38px; cursor: text; transition: border .2s; }
.tag-chips:focus-within { border-color: var(--accent); }
.tag-chip-item { background: rgba(232,197,71,.15); color: var(--accent); border-radius: 5px; padding: 2px 8px; font-size: .78rem; display: flex; align-items: center; gap: 4px; }
.tag-chip-item .rm { cursor: pointer; opacity: .6; font-size: .9rem; line-height: 1; }
.tag-chip-item .rm:hover { opacity: 1; }
.tag-text-input { border: none; background: transparent; color: var(--text); font-size: .85rem; outline: none; min-width: 80px; flex: 1; font-family: "Noto Serif TC", serif; padding: 2px 4px; }
.tag-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-top: 4px; max-height: 180px; overflow-y: auto; z-index: 50; display: none; box-shadow: 0 4px 20px rgba(0,0,0,.4); }
.tag-dropdown.open { display: block; }
.tag-option { padding: 8px 12px; font-size: .83rem; cursor: pointer; transition: background .12s; }
.tag-option:hover, .tag-option.highlighted { background: rgba(232,197,71,.08); color: var(--accent); }
.tag-option .new-badge { font-size: .68rem; color: var(--muted); margin-left: 6px; }

/* Detail view */
.detail-img { width: 100%; border-radius: 8px; margin-bottom: 16px; }
.detail-content { font-size: .9rem; line-height: 1.8; white-space: pre-wrap; }
.ocr-block { background: var(--bg); border-radius: 8px; padding: 14px; font-size: .8rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; white-space: pre-wrap; max-height: 200px; overflow-y: auto; margin-top: 12px; }
.detail-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }

/* ── 立AI 聊天泡泡 ── */
#chat-bubble { position: fixed; bottom: 28px; right: 28px; z-index: 200; }
#chat-toggle { width: 56px; height: 56px; border-radius: 50%; background: var(--accent); border: none; cursor: pointer; font-size: 1.4rem; box-shadow: 0 4px 20px rgba(232,197,71,.4); transition: transform .2s; display: flex; align-items: center; justify-content: center; }
#chat-toggle:hover { transform: scale(1.1); }
#chat-panel { position: absolute; bottom: 68px; right: 0; width: 360px; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; box-shadow: 0 8px 40px rgba(0,0,0,.6); display: none; flex-direction: column; overflow: hidden; }
#chat-panel.open { display: flex; }
#chat-header { padding: 14px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; background: var(--bg); }
#chat-header .name { font-weight: 900; font-size: .9rem; color: var(--accent); }
#chat-header .hint { font-size: .7rem; color: var(--muted); }
#chat-close { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 1.1rem; }
#chat-messages { height: 320px; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.msg { max-width: 85%; padding: 10px 14px; border-radius: 12px; font-size: .84rem; line-height: 1.6; }
.msg.user { align-self: flex-end; background: var(--accent); color: #0e0e0f; border-bottom-right-radius: 4px; }
.msg.ai { align-self: flex-start; background: var(--bg); color: var(--text); border-bottom-left-radius: 4px; border: 1px solid var(--border); }
.msg.ai .src { font-size: .68rem; color: var(--muted); margin-bottom: 4px; font-family: 'JetBrains Mono', monospace; }
.msg.thinking { color: var(--muted); font-style: italic; animation: pulse 1.2s infinite; }
@keyframes pulse { 0%,100%{opacity:.5} 50%{opacity:1} }
#chat-input-row { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--border); background: var(--bg); }
#chat-input { flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; color: var(--text); font-size: .85rem; font-family: 'Noto Serif TC', serif; resize: none; height: 38px; }
#chat-input:focus { outline: none; border-color: var(--accent); }
#chat-send { background: var(--accent); border: none; border-radius: 8px; padding: 8px 14px; color: #0e0e0f; cursor: pointer; font-size: .85rem; font-weight: 700; transition: background .15s; }
#chat-send:hover { background: #f0d060; }
#chat-send:disabled { opacity: .5; cursor: not-allowed; }
.msg-save-bar { display:flex; gap:6px; margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,.08); }
.msg-save-btn { border:none; border-radius:6px; padding:4px 10px; font-size:.72rem; cursor:pointer; font-family:'Noto Serif TC',serif; font-weight:600; transition:all .15s; }
.msg-save-yes { background:rgba(134,239,172,.2); color:#86efac; }
.msg-save-yes:hover { background:rgba(134,239,172,.35); }
.msg-save-no  { background:rgba(255,255,255,.06); color:var(--muted); }
.msg-save-no:hover  { background:rgba(255,255,255,.12); color:var(--text); }
.msg-save-done { font-size:.72rem; color:var(--muted); padding:4px 0; }
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-inner">
    <button class="sidebar-toggle" onclick="toggleSidebar()" title="收合側邊欄">◀</button>
    <div class="logo">
      <h1 id="main-title">🏛 圖書館 <span class="sync-dot" id="sync-dot"></span></h1>
      <p>立の知識庫 <span class="sync-badge" id="sync-badge">離線</span></p>
      <div style="display:flex;gap:6px;margin-top:8px;">
        <button id="btn-library" onclick="switchMode('library')"
          style="flex:1;padding:5px 0;border-radius:8px;border:none;cursor:pointer;font-size:.78rem;font-weight:700;background:#2563eb;color:#fff;transition:all .2s;">
          🏛 圖書館
        </button>
        <button id="btn-codedb" onclick="switchMode('codedb')"
          style="flex:1;padding:5px 0;border-radius:8px;border:1px solid #2a2d3a;cursor:pointer;font-size:.78rem;font-weight:700;background:#1a1d27;color:#888;transition:all .2s;">
          📐 程式碼
        </button>
      </div>
    </div>
    <div class="stats-row" id="stats-row">
      <div class="stat-chip"><div class="n">-</div><div class="l">全部</div></div>
      <div class="stat-chip"><div class="n">-</div><div class="l">圖片</div></div>
      <div class="stat-chip"><div class="n">-</div><div class="l">影片</div></div>
    </div>
    <div class="nav-section">分類</div>
    <div id="cat-list">
      <div class="nav-item active" data-cat="" onclick="filterCat(this,'')">全部</div>
    </div>
    <div class="nav-section">標籤</div>
    <div class="tag-cloud" id="tag-cloud"></div>
    <div class="nav-section" style="margin-top:8px">工具</div>
    <div class="nav-item" onclick="openCodeRules()" style="color:var(--accent2)">📐 程式碼規範庫</div>
    <div class="nav-item" onclick="openLearnSessions()" style="color:#86efac">📂 自學紀錄</div>
    </div><!-- /sidebar-inner -->
  </aside>

  <!-- Main -->
  <main class="main">
    <div class="toolbar">
      <input class="search-box" id="search-input" placeholder="搜尋標題、內容、OCR文字..." oninput="debounceSearch()">
      <select class="sort-select" id="sort-select" onchange="doSearch()">
        <option value="importance">重要性排序</option>
        <option value="time">時間排序</option>
      </select>
      <button class="btn btn-primary" onclick="openAddModal()">＋ 新增</button>
      <button class="btn" onclick="openLearnModal()" style="background:#1e3a5f;color:#93c5fd;border:none;border-radius:8px;padding:8px 18px;cursor:pointer;" title="讓立AI自動學習選取的資料">🧠 自學</button>
    </div>
    <div class="search-tags-bar" id="search-tags-bar">
      <div class="search-tags-input-wrap">
        <input class="search-tags-input" id="search-tag-input" placeholder="＋ 篩選標籤..."
          oninput="searchTagChanged()" onfocus="searchTagChanged()" onblur="searchTagBlur()" onkeydown="searchTagKey(event)">
        <div class="search-tag-dropdown" id="search-tag-dropdown"></div>
      </div>
    </div>
    <div class="cards" id="cards-container">
      <div class="empty"><div class="icon">🗂</div><div>尚無知識，點「新增」開始記錄</div></div>
    </div>
  </main>
</div>

<!-- Add Modal -->
<div class="modal-overlay" id="add-modal">
  <div class="modal">
    <div class="modal-header">
      <h2>新增知識</h2>
      <button class="modal-close" onclick="closeModal('add-modal')">✕</button>
    </div>
    <div class="modal-body">
      <div class="tabs">
        <button class="tab active" onclick="switchTab('text')">📝 文字</button>
        <button class="tab" onclick="switchTab('note')">📄 筆記</button>
        <button class="tab" onclick="switchTab('image')">🖼 圖片</button>
        <button class="tab" onclick="switchTab('video')">🎬 影片</button>
        <button class="tab" onclick="switchTab('pdf')">📑 PDF</button>
      </div>

      <!-- Text tab -->
      <div id="tab-text">
        <div class="form-group">
          <label class="form-label">標題</label>
          <input class="form-input" id="txt-title" placeholder="輸入標題...">
        </div>
        <div class="form-group">
          <label class="form-label">內容</label>
          <textarea class="form-textarea" id="txt-content" placeholder="輸入知識內容..."></textarea>
        </div>
        <div class="form-group">
          <label class="form-label">標籤</label>
          <div class="tag-input-wrap" id="txt-tag-wrap">
            <div class="tag-chips" id="txt-tag-chips" onclick="focusTagInput('txt')">
              <input class="tag-text-input" id="txt-tag-input" placeholder="輸入或選擇標籤..." autocomplete="off"
                oninput="tagInputChanged('txt')" onkeydown="tagInputKey(event,'txt')" onfocus="tagInputChanged('txt')" onblur="tagBlur('txt')">
            </div>
            <div class="tag-dropdown" id="txt-tag-dropdown"></div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">重要性</label>
          <div class="imp-row" id="txt-imp">
            <div class="imp-btn" onclick="setImp(this,1)">1</div>
            <div class="imp-btn" onclick="setImp(this,3)">3</div>
            <div class="imp-btn active" onclick="setImp(this,5)">5</div>
            <div class="imp-btn" onclick="setImp(this,7)">7</div>
            <div class="imp-btn" onclick="setImp(this,9)">9</div>
          </div>
        </div>
        <button class="btn btn-primary" onclick="submitText()" id="txt-submit-btn">
          儲存（AI 自動分類）
        </button>
      </div>

      <!-- Note tab -->
      <div id="tab-note" style="display:none">
        <div class="form-group">
          <label class="form-label">標題</label>
          <input class="form-input" id="note-title" placeholder="筆記標題...">
        </div>
        <!-- 工具列 -->
        <div class="editor-toolbar">
          <select class="editor-font-select" onchange="execCmd('fontSize',this.value)">
            <option value="3">內文</option>
            <option value="5">大</option>
            <option value="6">特大</option>
            <option value="2">小</option>
          </select>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="execCmd('bold')" title="粗體"><b>B</b></button>
          <button class="editor-btn" onclick="execCmd('italic')" title="斜體"><i>I</i></button>
          <button class="editor-btn" onclick="execCmd('underline')" title="底線"><u>U</u></button>
          <button class="editor-btn" onclick="execCmd('strikeThrough')" title="刪除線"><s>S</s></button>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="insertHtml('<h1><br></h1>')" title="標題1">H1</button>
          <button class="editor-btn" onclick="insertHtml('<h2><br></h2>')" title="標題2">H2</button>
          <button class="editor-btn" onclick="insertHtml('<h3><br></h3>')" title="標題3">H3</button>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="execCmd('insertUnorderedList')" title="項目清單">• 清單</button>
          <button class="editor-btn" onclick="execCmd('insertOrderedList')" title="編號清單">1. 清單</button>
          <button class="editor-btn" onclick="insertHtml('<blockquote><br></blockquote>')" title="引用">❝</button>
          <button class="editor-btn" onclick="insertHtml('<hr>')" title="分隔線">—</button>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="execCmd('justifyLeft')" title="靠左">⬅</button>
          <button class="editor-btn" onclick="execCmd('justifyCenter')" title="置中">↔</button>
          <button class="editor-btn" onclick="execCmd('justifyRight')" title="靠右">➡</button>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="insertEditorImage()" title="插入圖片">🖼</button>
          <button class="editor-btn" onclick="execCmd('removeFormat')" title="清除格式">✕格式</button>
          <input type="file" id="editor-img-input" accept="image/*" style="display:none" onchange="handleEditorImage(this)">
        </div>
        <div class="editor-body" id="note-editor" contenteditable="true" placeholder="開始輸入筆記內容..."></div>
        <div class="form-group" style="margin-top:12px">
          <label class="form-label">標籤</label>
          <div class="tag-input-wrap" id="note-tag-wrap">
            <div class="tag-chips" id="note-tag-chips" onclick="focusTagInput('note')">
              <input class="tag-text-input" id="note-tag-input" placeholder="輸入或選擇標籤..." autocomplete="off"
                oninput="tagInputChanged('note')" onkeydown="tagInputKey(event,'note')" onfocus="tagInputChanged('note')" onblur="tagBlur('note')">
            </div>
            <div class="tag-dropdown" id="note-tag-dropdown"></div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">重要性</label>
          <div class="imp-row" id="note-imp">
            <div class="imp-btn" onclick="setImp(this,1)">1</div>
            <div class="imp-btn" onclick="setImp(this,3)">3</div>
            <div class="imp-btn active" onclick="setImp(this,5)">5</div>
            <div class="imp-btn" onclick="setImp(this,7)">7</div>
            <div class="imp-btn" onclick="setImp(this,9)">9</div>
          </div>
        </div>
        <button class="btn btn-primary" onclick="submitNote()" id="note-submit-btn" style="margin-top:8px">
          💾 儲存筆記
        </button>
      </div>

      <!-- Image tab -->
      <div id="tab-image" style="display:none">
        <!-- 子模式切換 -->
        <div class="img-mode-tabs">
          <div class="img-mode-btn active" id="img-mode-btn-single" onclick="switchImgMode('single')">🖼 單個</div>
          <div class="img-mode-btn" id="img-mode-btn-multi" onclick="switchImgMode('multi')">🗂 多個</div>
          <div class="img-mode-btn" id="img-mode-btn-group" onclick="switchImgMode('group')">📁 群組</div>
        </div>

        <!-- 單個模式 -->
        <div id="img-mode-single">
          <div class="drop-zone" id="img-drop-single" onclick="document.getElementById('img-file-single').click()" ondragover="dragOver(event)" ondrop="dropFileSingle(event)">
            <input type="file" id="img-file-single" accept="image/*" onchange="fileSelectedSingle(this)">
            <div id="img-drop-text-single">🖼 點擊或拖曳一張圖片<br><small>JPG / PNG / GIF / WebP</small></div>
          </div>
          <div id="img-preview-single" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"></div>
        </div>

        <!-- 多個模式 -->
        <div id="img-mode-multi" style="display:none">
          <div class="drop-zone" id="img-drop-multi" onclick="document.getElementById('img-file-multi').click()" ondragover="dragOver(event)" ondrop="dropFileMulti(event)">
            <input type="file" id="img-file-multi" accept="image/*" multiple onchange="fileSelectedMulti(this)">
            <div id="img-drop-text-multi">🗂 點擊或拖曳多張圖片<br><small>可一次選多張</small></div>
          </div>
          <div id="img-preview-multi" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"></div>
        </div>

        <!-- 群組模式 -->
        <div id="img-mode-group" style="display:none">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">
            <select class="form-select" id="img-group-select" style="flex:1">
              <option value="">選擇或建立群組...</option>
            </select>
            <button class="btn btn-ghost" onclick="createNewGroup()" style="padding:8px 12px;font-size:.8rem;white-space:nowrap">＋ 新群組</button>
          </div>
          <div class="drop-zone" id="img-drop-group" onclick="document.getElementById('img-file-group').click()" ondragover="dragOver(event)" ondrop="dropFileGroup(event)">
            <input type="file" id="img-file-group" accept="image/*" multiple onchange="fileSelectedGroup(this)">
            <div id="img-drop-text-group">📁 點擊或拖曳圖片加入群組<br><small>可一次加入多張</small></div>
          </div>
          <div id="img-preview-group" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px"></div>
        </div>

        <button class="btn btn-primary" id="img-submit-btn" style="margin-top:12px;display:none">
          ⬆️ 開始上傳
        </button>
        <div id="img-progress" style="margin-top:8px;font-size:.78rem;color:var(--muted)"></div>
      </div>

      <!-- Video tab -->
      <div id="tab-video" style="display:none">
        <div class="drop-zone" id="vid-drop" onclick="document.getElementById('vid-file').click()" ondragover="dragOver(event)" ondrop="dropFile(event,'video')">
          <input type="file" id="vid-file" accept="video/*" onchange="fileSelected(this,'video')">
          <div id="vid-drop-text">🎬 點擊或拖曳影片到這裡<br><small>支援 MP4 / MOV / AVI / MKV</small></div>
        </div>
        <div class="form-group" style="margin-top:12px">
          <label class="form-label">標題（留空自動用檔名）</label>
          <input class="form-input" id="vid-title" placeholder="影片標題...">
        </div>
        <button class="btn btn-primary" onclick="submitFile('video')" id="vid-submit-btn" style="margin-top:8px">
          上傳並擷取關鍵畫面
        </button>
      </div>

      <!-- PDF tab -->
      <div id="tab-pdf" style="display:none">
        <div class="drop-zone" id="pdf-drop" ondragover="dragOver(event)" ondrop="dropFilePDF(event)" onclick="document.getElementById('pdf-file').click()">
          <input type="file" id="pdf-file" accept=".pdf" multiple onchange="fileSelectedPDF(this)">
          <div id="pdf-drop-text">📑 點擊或拖曳 PDF 到這裡<br><small>支援多檔，自動擷取文字內容</small></div>
        </div>
        <div id="pdf-preview" style="margin-top:8px;font-size:.78rem;color:var(--muted)"></div>
        <div class="form-group" style="margin-top:12px" onclick="event.stopPropagation()">
          <label class="form-label">標籤</label>
          <div class="tag-input-wrap" id="pdf-tag-wrap">
            <div class="tag-chips" id="pdf-tag-chips" onclick="event.stopPropagation();focusTagInput('pdf')">
              <input class="tag-text-input" id="pdf-tag-input" placeholder="輸入或選擇標籤..." autocomplete="off"
                oninput="tagInputChanged('pdf')" onkeydown="tagInputKey(event,'pdf')" onfocus="tagInputChanged('pdf')" onblur="tagBlur('pdf')"
                onclick="event.stopPropagation()">
            </div>
            <div class="tag-dropdown" id="pdf-tag-dropdown"></div>
          </div>
        </div>
        <button class="btn btn-primary" id="pdf-submit-btn" style="margin-top:8px;display:none">
          ⬆️ 開始上傳
        </button>
        <div id="pdf-progress" style="margin-top:8px;font-size:.78rem;color:var(--muted)"></div>
      </div>
    </div>
  </div>
</div>

<!-- 自學 Modal -->
<div class="modal-overlay" id="learn-modal">
  <div class="modal" style="max-width:700px;">
    <div class="modal-header">
      <h2>🧠 立AI 自學</h2>
      <button class="modal-close" onclick="closeModal('learn-modal')">✕</button>
    </div>
    <div class="modal-body">
      <!-- 資料來源選擇 -->
      <div style="margin-bottom:14px;">
        <div style="font-size:.78rem;color:var(--muted);margin-bottom:8px;">選擇學習來源</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:.85rem;">
            <input type="radio" name="learn-source" value="text" checked onchange="switchLearnSource(this.value)"> 輸入文字
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:.85rem;">
            <input type="radio" name="learn-source" value="file" onchange="switchLearnSource(this.value)"> 上傳檔案（PDF/圖片）
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:.85rem;">
            <input type="radio" name="learn-source" value="kb" onchange="switchLearnSource(this.value)"> 從知識庫選
          </label>
        </div>
      </div>

      <!-- 文字輸入 -->
      <div id="learn-text-area">
        <div class="form-group">
          <label class="form-label">貼上要讓立AI學習的資料</label>
          <textarea class="form-textarea" id="learn-text-input" rows="8" placeholder="貼上文章、筆記、資料..."></textarea>
        </div>
      </div>

      <!-- 檔案上傳 -->
      <div id="learn-file-area" style="display:none;">
        <div class="drop-zone" id="learn-file-drop" onclick="document.getElementById('learn-file-input').click()"
          ondragover="dragOver(event)" ondrop="dropLearnFile(event)">
          <input type="file" id="learn-file-input" accept=".pdf,.txt,.png,.jpg,.jpeg,.webp" onchange="learnFileSelected(this)">
          <div id="learn-file-text">📂 點擊或拖曳檔案<br><small>支援 PDF、圖片、TXT</small></div>
        </div>
      </div>

      <!-- 從知識庫選 -->
      <div id="learn-kb-area" style="display:none;">
        <div class="form-group">
          <label class="form-label">搜尋知識庫</label>
          <input class="form-input" id="learn-kb-search" placeholder="輸入關鍵字搜尋..." oninput="searchLearnKb()">
        </div>
        <div id="learn-kb-results" style="max-height:200px;overflow-y:auto;margin-top:8px;"></div>
        <div id="learn-kb-selected" style="margin-top:8px;font-size:.78rem;color:var(--accent)"></div>
      </div>

      <!-- 學習方向 -->
      <div class="form-group" style="margin-top:14px;">
        <label class="form-label">學習重點方向（選填）</label>
        <input class="form-input" id="learn-focus" placeholder="例如：技術細節、應用場景、注意事項...">
      </div>

      <button class="btn btn-primary" id="learn-btn" onclick="startLearn()" style="margin-top:4px;width:100%;">
        🧠 開始自學
      </button>

      <!-- 進度 -->
      <div id="learn-progress" style="margin-top:12px;display:none;">
        <div style="font-size:.82rem;color:var(--muted);margin-bottom:6px;" id="learn-status">gpt-oss:20b 思考中，請耐心等待...</div>
        <div style="background:var(--bg);border-radius:4px;height:4px;overflow:hidden;">
          <div id="learn-bar" style="height:100%;background:var(--accent2);width:0%;transition:width .3s;border-radius:4px;"></div>
        </div>
      </div>

      <!-- 結果 -->
      <div id="learn-result" style="display:none;margin-top:16px;">
        <div style="font-size:.78rem;color:var(--muted);margin-bottom:8px;">📋 學習報告</div>
        <div id="learn-result-content" style="background:var(--bg);border-radius:10px;padding:14px;font-size:.85rem;line-height:1.7;white-space:pre-wrap;max-height:300px;overflow-y:auto;"></div>
        <div style="display:flex;gap:8px;margin-top:10px;">
          <button class="btn btn-primary" onclick="saveLearnReport()" style="font-size:.82rem;display:none">💾 存入知識庫</button>
          <button class="btn btn-ghost" onclick="closeModal('learn-modal')" style="font-size:.82rem;">關閉</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Detail Modal -->
<div class="modal-overlay" id="detail-modal">
  <div class="modal">
    <div class="modal-header">
      <h2 id="detail-title">-</h2>
      <button class="modal-close" onclick="closeModal('detail-modal')">✕</button>
    </div>
    <div class="modal-body" id="detail-body"></div>
  </div>
</div>

<script>
let currentCat = '';
let activeTags = [];
let searchActiveTags = [];  // 搜尋列標籤篩選
let currentImp = 5;
let searchTimer = null;
let selectedFiles = {};

// ── Init ──────────────────────────────────────────────────────────────────
// ── 程式碼規範庫 ─────────────────────────────────────────────────────────────
let _curCodeCat = 'all';

const CODE_CAT_ICONS = {
  coding: '📐', arch: '🏗', module: '🔗', bug: '🐛', ai_rules: '🤖'
};
const PRIORITY_LABELS = {1:'🔴 必須遵守', 2:'🟡 建議', 3:'🟢 參考'};
const PRIORITY_COLORS = {1:'#f07070', 2:'#f0c040', 3:'#86efac'};

function openCodeRules() {
  document.getElementById('code-rules-modal').classList.add('open');
  loadCodeRules();
}
function closeCodeRules() {
  document.getElementById('code-rules-modal').classList.remove('open');
}

function filterCodeCat(cat, el) {
  _curCodeCat = cat;
  document.querySelectorAll('#code-rules-modal .nav-item').forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  loadCodeRules();
}

async function loadCodeRules() {
  const url = _curCodeCat === 'all' ? '/api/code_rules' : `/api/code_rules?category=${_curCodeCat}`;
  const r = await fetch(url);
  const rules = await r.json();
  const el = document.getElementById('code-rules-list');
  if (!rules.length) {
    el.innerHTML = '<div class="empty"><div class="icon">📐</div><div>這個分類還沒有規則，點「＋ 新增規則」開始建立</div></div>';
    return;
  }
  el.innerHTML = rules.map(rule => `
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:10px;cursor:pointer;" onclick="editRule(${rule.id})">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-size:.72rem;background:rgba(255,255,255,.06);border-radius:4px;padding:2px 8px;">${esc(CODE_CAT_ICONS[rule.category] || '')} ${esc(getCatLabel(rule.category))}</span>
        <span style="font-size:.72rem;color:${PRIORITY_COLORS[rule.priority] || '#888'};">${PRIORITY_LABELS[rule.priority] || ''}</span>
        <span style="font-size:.68rem;color:var(--muted);margin-left:auto;">${rule.updated_at.slice(0,10)}</span>
      </div>
      <div style="font-weight:700;font-size:.9rem;margin-bottom:4px;">${esc(rule.title)}</div>
      <div style="font-size:.8rem;color:var(--muted);line-height:1.5;white-space:pre-wrap;">${esc(rule.content.slice(0,200))}${rule.content.length>200?'...':''}</div>
    </div>
  `).join('');
}

function getCatLabel(cat) {
  const map = {coding:'程式碼規則',arch:'架構方向',module:'模組規則',bug:'已知Bug',ai_rules:'AI行為準則'};
  return map[cat] || cat;
}

function openAddRule() {
  document.getElementById('rule-edit-id').value = '';
  document.getElementById('rule-modal-title').textContent = '新增規則';
  document.getElementById('rule-title').value = '';
  document.getElementById('rule-content').value = '';
  document.getElementById('rule-category').value = _curCodeCat !== 'all' ? _curCodeCat : 'coding';
  document.getElementById('rule-priority').value = '2';
  document.getElementById('rule-delete-btn').style.display = 'none';
  document.getElementById('add-rule-modal').classList.add('open');
}

function closeAddRule() {
  document.getElementById('add-rule-modal').classList.remove('open');
}

async function editRule(id) {
  const r = await fetch('/api/code_rules/' + id);
  const rule = await r.json();
  document.getElementById('rule-edit-id').value = id;
  document.getElementById('rule-modal-title').textContent = '編輯規則';
  document.getElementById('rule-title').value = rule.title;
  document.getElementById('rule-content').value = rule.content;
  document.getElementById('rule-category').value = rule.category;
  document.getElementById('rule-priority').value = rule.priority;
  document.getElementById('rule-delete-btn').style.display = '';
  document.getElementById('add-rule-modal').classList.add('open');
}

async function saveRule() {
  const id    = document.getElementById('rule-edit-id').value;
  const title = document.getElementById('rule-title').value.trim();
  const content = document.getElementById('rule-content').value.trim();
  const cat   = document.getElementById('rule-category').value;
  const pri   = parseInt(document.getElementById('rule-priority').value);
  if (!title || !content) return alert('請填寫標題和內容');
  const url    = id ? `/api/code_rules/${id}` : '/api/code_rules';
  const method = id ? 'PUT' : 'POST';
  const r = await fetch(url, {
    method, headers: {'Content-Type':'application/json'},
    body: JSON.stringify({title, content, category: cat, priority: pri})
  });
  const d = await r.json();
  if (d.id || d.ok) {
    closeAddRule();
    loadCodeRules();
  } else { alert('儲存失敗：' + (d.error || '未知')); }
}

async function deleteRule() {
  const id = document.getElementById('rule-edit-id').value;
  if (!id || !confirm('確定刪除這條規則？')) return;
  await fetch('/api/code_rules/' + id, { method: 'DELETE' });
  closeAddRule();
  loadCodeRules();
}

// ── 模式切換（圖書館 / 程式碼規範庫）────────────────────────────────────────
let _currentMode = 'library';

function switchMode(mode) {
  _currentMode = mode;
  const btnLib  = document.getElementById('btn-library');
  const btnCode = document.getElementById('btn-codedb');
  const title   = document.getElementById('main-title');
  const mainArea = document.querySelector('.main');

  if (mode === 'library') {
    // 標題
    title.innerHTML = '🏛 圖書館 <span class="sync-dot" id="sync-dot"></span>';
    document.title = '🏛 圖書館';
    // 按鈕樣式
    btnLib.style.background  = '#2563eb';
    btnLib.style.color       = '#fff';
    btnLib.style.border      = 'none';
    btnCode.style.background = '#1a1d27';
    btnCode.style.color      = '#888';
    btnCode.style.border     = '1px solid #2a2d3a';
    // 關閉程式碼規範庫，顯示主內容
    const codeModal = document.getElementById('code-rules-modal');
    if (codeModal) codeModal.classList.remove('open');
    if (mainArea) mainArea.style.display = '';
  } else {
    // 標題
    title.innerHTML = '📐 程式碼規範庫 <span class="sync-dot" id="sync-dot"></span>';
    document.title = '📐 程式碼規範庫';
    // 按鈕樣式
    btnCode.style.background = '#2563eb';
    btnCode.style.color      = '#fff';
    btnCode.style.border     = 'none';
    btnLib.style.background  = '#1a1d27';
    btnLib.style.color       = '#888';
    btnLib.style.border      = '1px solid #2a2d3a';
    // 開啟程式碼規範庫
    openCodeRules();
  }
}

// 讓 openCodeRules 不再用全螢幕 overlay，改為內嵌模式
function openCodeRules() {
  const modal = document.getElementById('code-rules-modal');
  if (modal) modal.classList.add('open');
  loadCodeRules();
}

// ── 自學功能 ──────────────────────────────────────────────────────────────────
let _learnKbSelected = null;
let _learnFileData   = null;
let _learnReport     = '';

function openLearnModal() {
  document.getElementById('learn-modal').classList.add('open');
  document.getElementById('learn-result').style.display = 'none';
  document.getElementById('learn-progress').style.display = 'none';
  document.getElementById('learn-text-input').value = '';
  document.getElementById('learn-focus').value = '';
  _learnKbSelected = null; _learnFileData = null; _learnReport = '';
  switchLearnSource('text');
}

function switchLearnSource(val) {
  ['text','file','kb'].forEach(t => {
    document.getElementById(`learn-${t}-area`).style.display = t === val ? '' : 'none';
  });
}

function dropLearnFile(e) {
  e.preventDefault(); e.currentTarget.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) processLearnFile(file);
}

function learnFileSelected(input) {
  const file = input.files[0];
  if (file) processLearnFile(file);
}

function processLearnFile(file) {
  _learnFileData = file;
  document.getElementById('learn-file-text').textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
}

async function searchLearnKb() {
  const q = document.getElementById('learn-kb-search').value.trim();
  if (!q) return;
  const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=8`);
  const items = await r.json();
  const el = document.getElementById('learn-kb-results');
  el.innerHTML = items.map(item => `
    <div onclick="selectLearnKb(${item.id},'${esc(item.title)}')"
      style="padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px;background:var(--bg);font-size:.82rem;"
      onmouseover="this.style.background='rgba(232,197,71,.1)'" onmouseout="this.style.background='var(--bg)'">
      <b>${esc(item.title)}</b>
      <span style="color:var(--muted);margin-left:8px">${esc((item.ai_summary||item.content||'').slice(0,60))}</span>
    </div>
  `).join('');
}

function selectLearnKb(id, title) {
  _learnKbSelected = id;
  document.getElementById('learn-kb-selected').textContent = `✅ 已選：${title}`;
}

async function startLearn() {
  const source = document.querySelector('input[name="learn-source"]:checked').value;
  const focus  = document.getElementById('learn-focus').value.trim();
  const btn    = document.getElementById('learn-btn');
  const prog   = document.getElementById('learn-progress');
  const bar    = document.getElementById('learn-bar');
  const status = document.getElementById('learn-status');
  const resultBox = document.getElementById('learn-result-content');

  // 驗證輸入
  if (source === 'text') {
    if (!document.getElementById('learn-text-input').value.trim()) { alert('請輸入資料'); return; }
  } else if (source === 'file') {
    if (!_learnFileData) { alert('請選擇檔案'); return; }
  } else if (source === 'kb') {
    if (!_learnKbSelected) { alert('請從知識庫選擇一筆資料'); return; }
  }

  btn.disabled = true;
  prog.style.display = '';
  document.getElementById('learn-result').style.display = 'none';
  resultBox.textContent = '';
  _learnReport = '';

  // 準備 FormData
  const body = new FormData();
  body.append('source', source);
  body.append('focus', focus);
  if (source === 'text')  body.append('text',   document.getElementById('learn-text-input').value.trim());
  if (source === 'file')  body.append('file',   _learnFileData);
  if (source === 'kb')    body.append('kb_id',  _learnKbSelected);

  // ── 先 POST 送資料，後端回應 SSE stream ──────────────────────────────────
  // 注意：SSE 標準只支援 GET，所以改用 fetch + ReadableStream 讀取
  status.textContent = '⏳ 連線中，等待模型載入...';
  bar.style.width = '5%';

  // 打字機效果計時
  let dotCount = 0;
  const thinkTicker = setInterval(() => {
    dotCount = (dotCount + 1) % 4;
    const dots = '●'.repeat(dotCount + 1) + '○'.repeat(3 - dotCount);
    const chars = resultBox.textContent.length;
    if (chars > 0) {
      status.textContent = `✍️ 思考中 ${dots}  已生成 ${chars} 字`;
    } else {
      status.textContent = `⏳ 模型思考中 ${dots}`;
    }
    // 進度條緩慢爬升（最高到 92%，剩下留給完成）
    bar.style.width = Math.min(parseFloat(bar.style.width || 5) + 0.3, 92) + '%';
  }, 400);

  try {
    const resp = await fetch('/api/learn', { method: 'POST', body });
    if (!resp.ok) {
      const d = await resp.json();
      throw new Error(d.error || `HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // 解析 SSE 事件（可能一次收到多行）
      const lines = buf.split('\n');
      buf = lines.pop(); // 最後一行可能不完整，留到下次

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let evt;
        try { evt = JSON.parse(line.slice(6)); } catch { continue; }

        if (evt.type === 'model') {
          status.textContent = `⏳ ${evt.model} 思考中 ●○○`;
        } else if (evt.type === 'token') {
          _learnReport += evt.text;
          resultBox.textContent = _learnReport;
          // 顯示結果區塊（讓使用者即時看到）
          if (document.getElementById('learn-result').style.display === 'none') {
            document.getElementById('learn-result').style.display = '';
            // 隱藏儲存按鈕，等完成再顯示
            document.querySelector('#learn-result .btn-primary').style.display = 'none';
          }
        } else if (evt.type === 'done') {
          _learnReport = evt.report || _learnReport;
          resultBox.textContent = _learnReport;
          clearInterval(thinkTicker);
          bar.style.width = '100%';
          status.textContent = `✅ 學習完成！（${evt.model}，共 ${_learnReport.length} 字）`;
          document.querySelector('#learn-result .btn-primary').style.display = '';
          // 若自學紀錄 modal 已開著，自動重整列表
          if (document.getElementById('learn-sessions-modal').classList.contains('open')) {
            loadSessionsList();
          }
        } else if (evt.type === 'error') {
          throw new Error(evt.error);
        }
      }
    }

  } catch(e) {
    clearInterval(thinkTicker);
    bar.style.width = '0%';
    status.textContent = '❌ 錯誤：' + e.message;
    logger && console.error('[Learn]', e);
  } finally {
    btn.disabled = false;
  }
}

async function saveLearnReport() {
  if (!_learnReport) return;
  const btn = document.querySelector('#learn-result .btn-primary');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 儲存中...'; }

  // 原始資料（你給的內容）
  const source = document.querySelector('input[name="learn-source"]:checked')?.value || 'text';
  let inputContent = '';
  if (source === 'text') {
    inputContent = document.getElementById('learn-text-input')?.value?.trim() || '';
  } else if (source === 'file') {
    inputContent = `（檔案：${_learnFileData?.name || '未知'}）`;
  } else if (source === 'kb') {
    inputContent = `（來自知識庫 ID：${_learnKbSelected}）`;
  }

  const focus = document.getElementById('learn-focus')?.value?.trim() || '';

  // title 用 focus 或 inputContent 的前 40 字
  const titleBase = focus || inputContent.slice(0, 40) || '自學';
  const title = `【自學】${titleBase}`;

  // content 只存原始資料，不存報告（報告已在 learn_sessions/ 裡）
  const content = inputContent + (focus ? `\n\n學習方向：${focus}` : '');

  const r = await fetch('/api/add/text', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      title,
      content,
      importance: 7,
      tags: ['自學紀錄', '立AI'],
    })
  });
  const d = await r.json();
  if (d.id) {
    if (btn) { btn.textContent = '✅ 已存入'; btn.style.background = 'rgba(134,239,172,.2)'; btn.style.color = '#86efac'; }
    await Promise.all([init(), loadAllTags()]);
  } else {
    if (btn) { btn.disabled = false; btn.textContent = '❌ 失敗，重試'; }
  }
}

// ── 自學紀錄 ─────────────────────────────────────────────────────────────────
let _currentSessionId = null;

function openLearnSessions() {
  document.getElementById('learn-sessions-modal').classList.add('open');
  loadSessionsList();
}

async function loadSessionsList() {
  const el = document.getElementById('sessions-list');
  el.innerHTML = '<div style="padding:12px 16px;font-size:.75rem;color:var(--muted);">載入中...</div>';
  const r = await fetch('/api/learn_sessions');
  const sessions = await r.json();
  if (!sessions.length) {
    el.innerHTML = '<div style="padding:20px 16px;font-size:.82rem;color:var(--muted);text-align:center;">還沒有自學紀錄<br>點「🧠 自學」開始學習</div>';
    return;
  }
  const SOURCE_ICON = { text: '📝', file: '📄', kb: '🗂' };
  el.innerHTML = sessions.map(s => `
    <div onclick="loadSessionDetail('${esc(s.session_id)}')"
      id="session-item-${esc(s.session_id)}"
      style="padding:12px 16px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .15s;"
      onmouseover="this.style.background='rgba(134,239,172,.06)'"
      onmouseout="this.style.background=_currentSessionId==='${esc(s.session_id)}'?'rgba(134,239,172,.1)':''">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
        <span>${SOURCE_ICON[s.source_type] || '📝'}</span>
        <span style="font-size:.7rem;font-family:'JetBrains Mono',monospace;color:var(--muted);">${esc(s.timestamp.slice(0,16).replace('T',' '))}</span>
        <span style="font-size:.65rem;background:rgba(134,239,172,.12);color:#86efac;border-radius:4px;padding:1px 6px;margin-left:auto">${esc(s.model||'')}</span>
      </div>
      <div style="font-size:.8rem;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(s.input_preview||'（無輸入預覽）')}</div>
      <div style="font-size:.72rem;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">報告：${esc(s.report_preview||'')}</div>
    </div>
  `).join('');
}

async function loadSessionDetail(sessionId) {
  _currentSessionId = sessionId;
  // 高亮選中的列表項
  document.querySelectorAll('#sessions-list > div[id^="session-item-"]').forEach(el => {
    el.style.background = el.id === `session-item-${sessionId}` ? 'rgba(134,239,172,.1)' : '';
  });

  const detail = document.getElementById('session-detail');
  detail.innerHTML = '<div style="color:var(--muted);padding:40px;text-align:center">載入中...</div>';
  const r = await fetch(`/api/learn_sessions/${sessionId}`);
  if (!r.ok) { detail.innerHTML = '<div style="color:var(--danger);padding:20px">載入失敗</div>'; return; }
  const s = await r.json();

  const SOURCE_LABEL = { text: '文字輸入', file: '檔案上傳', kb: '知識庫' };
  detail.innerHTML = `
    <div style="max-width:780px;margin:0 auto;">
      <!-- Header -->
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;flex-wrap:wrap;">
        <div>
          <div style="font-size:1rem;font-weight:900;color:#86efac;">📂 自學紀錄</div>
          <div style="font-size:.72rem;color:var(--muted);font-family:'JetBrains Mono',monospace;margin-top:2px;">
            ${esc(s.timestamp||'')} ｜ ${esc(SOURCE_LABEL[s.source_type]||s.source_type)} ｜ ${esc(s.model||'')}
            ${s.focus ? `<span style="color:var(--accent);margin-left:8px">🎯 ${esc(s.focus)}</span>` : ''}
          </div>
        </div>
        <div style="margin-left:auto;display:flex;gap:8px;">
          <button class="btn btn-ghost" style="font-size:.78rem;padding:6px 12px;"
            onclick="deleteSession('${esc(s.session_id)}')">🗑 刪除紀錄</button>
        </div>
      </div>

      <!-- 原始資料 -->
      <div style="margin-bottom:20px;">
        <div style="font-size:.72rem;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin-bottom:8px;">
          📥 原始資料
        </div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;
                    font-size:.83rem;line-height:1.7;white-space:pre-wrap;max-height:280px;overflow-y:auto;
                    color:var(--text);font-family:'JetBrains Mono',monospace;">
          ${esc(s.input||'（無文字內容）')}
        </div>
      </div>

      <!-- 分隔 -->
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
        <div style="flex:1;height:1px;background:var(--border)"></div>
        <div style="font-size:.75rem;color:var(--muted)">↓ 立AI 的理解</div>
        <div style="flex:1;height:1px;background:var(--border)"></div>
      </div>

      <!-- 學習報告 -->
      <div>
        <div style="font-size:.72rem;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin-bottom:8px;">
          📋 學習報告
        </div>
        <div style="background:var(--surface);border:1px solid #86efac33;border-radius:10px;padding:16px;
                    font-size:.88rem;line-height:1.85;white-space:pre-wrap;color:var(--text);">
          ${esc(s.report||'（無報告）')}
        </div>
      </div>
    </div>
  `;
}

async function deleteSession(sessionId) {
  if (!confirm('確定刪除這筆自學紀錄？')) return;
  await fetch(`/api/learn_sessions/${sessionId}`, { method: 'DELETE' });
  _currentSessionId = null;
  document.getElementById('session-detail').innerHTML = `
    <div style="color:var(--muted);text-align:center;margin-top:80px;font-size:.9rem;">
      <div style="font-size:2.5rem;margin-bottom:12px;">🗑</div>已刪除
    </div>`;
  loadSessionsList();
}

// ── 側邊欄收合 ───────────────────────────────────────────────────────────────
function toggleSidebar() {
  const app = document.querySelector('.app');
  app.classList.toggle('collapsed');
  localStorage.setItem('sidebar_collapsed', app.classList.contains('collapsed') ? '1' : '0');
}

// 記住收合狀態
function restoreSidebar() {
  if (localStorage.getItem('sidebar_collapsed') === '1') {
    document.querySelector('.app').classList.add('collapsed');
  }
}

async function init() {
  await Promise.all([loadStats(), loadCategories(), loadTags(), doSearch(), loadAllTags(), loadGroups()]);
}

async function loadStats() {
  const r = await fetch('/api/stats');
  const d = await r.json();
  const chips = document.querySelectorAll('.stat-chip .n');
  if (chips[0]) chips[0].textContent = d.total;
  if (chips[1]) chips[1].textContent = d.images;
  if (chips[2]) chips[2].textContent = d.videos;
}

async function loadCategories() {
  const r = await fetch('/api/categories');
  const cats = await r.json();
  const el = document.getElementById('cat-list');
  el.innerHTML = `<div class="nav-item active" data-cat="" onclick="filterCat(this,'')">全部</div>`;
  for (const c of cats) {
    el.innerHTML += `<div class="nav-item" data-cat="${esc(c.category)}" onclick="filterCat(this,'${esc(c.category)}')">${esc(c.category)}<span class="badge">${c.count}</span></div>`;
  }
}

async function loadTags() {
  const r = await fetch('/api/tags');
  const tags = await r.json();
  const el = document.getElementById('tag-cloud');
  el.innerHTML = tags.map(t => `<span class="tag-pill" onclick="toggleTag(this,'${esc(t)}')">${esc(t)}</span>`).join('');
}

// ── Search ────────────────────────────────────────────────────────────────
function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 350);
}

async function doSearch() {
  const q = document.getElementById('search-input').value;
  const sort = document.getElementById('sort-select').value;
  const allActive = [...activeTags, ...searchActiveTags];
  const params = new URLSearchParams({ q, category: currentCat, sort });
  if (allActive.length) params.set('tags', allActive.join(','));
  const r = await fetch('/api/search?' + params);
  const items = await r.json();
  renderCards(items);
}

function renderCards(items) {
  const el = document.getElementById('cards-container');
  if (!items.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🔍</div><div>找不到符合的知識</div></div>';
    return;
  }
  el.innerHTML = items.map(item => {
    const stars = '★'.repeat(Math.min(item.importance, 5));
    const tags = (item.tags || []).slice(0, 3).map(t => `<span class="card-tag">${esc(t)}</span>`).join('');
    const typeColor = item.entry_type === 'image' ? 'img' : item.entry_type === 'video' ? 'vid' : '';
    const typeLabel = { text: '文字', image: '圖片', video: '影片', note: '筆記' }[item.entry_type] || item.entry_type;

    // 群組標記
    const groupBadge = item.group_id
      ? `<span style="font-size:.65rem;background:rgba(126,184,247,.15);color:var(--accent2);border-radius:4px;padding:1px 6px;margin-left:4px">群組</span>`
      : '';

    const thumb = item.thumb_path ? `<img class="thumb" src="/api/thumb/${item.id}" onerror="this.style.display='none'" onclick="${item.group_id ? `openGroupModal(event,${item.group_id})` : `openLightbox(event,'/api/file/${item.id}')`}" style="cursor:zoom-in">` : '';
    return `
      <div class="card" onclick="openDetail(${item.id})">
        ${thumb}
        <div class="card-type"><span class="dot ${typeColor}"></span>${typeLabel}${groupBadge}</div>
        <h3>${esc(item.title)}</h3>
        <div class="summary">${esc(item.ai_summary || item.content.slice(0,60) || '')}</div>
        <div class="card-footer">
          <div class="card-tags">${tags}</div>
          <span class="stars">${stars}</span>
        </div>
        <div style="margin-top:6px"><span class="cat-badge">${esc(item.category)}</span></div>
      </div>`;
  }).join('');
}

// ── 搜尋標籤篩選 ──────────────────────────────────────────────────────────
function searchTagChanged() {
  const inp = document.getElementById('search-tag-input');
  const q = inp.value.trim().toLowerCase();
  const dd = document.getElementById('search-tag-dropdown');
  const available = _allTags.filter(t => !searchActiveTags.includes(t) && t.toLowerCase().includes(q));
  if (!available.length && !q) { dd.classList.remove('open'); return; }
  let html = available.slice(0, 12).map(t =>
    `<div class="search-tag-opt" onmousedown="addSearchTag('${esc(t)}')">${esc(t)}</div>`
  ).join('');
  if (!html) { dd.classList.remove('open'); return; }
  dd.innerHTML = html;
  dd.classList.add('open');
}

function searchTagBlur() {
  setTimeout(() => {
    document.getElementById('search-tag-dropdown').classList.remove('open');
  }, 150);
}

function searchTagKey(e) {
  if (e.key === 'Enter') {
    const val = document.getElementById('search-tag-input').value.trim();
    if (val) addSearchTag(val);
  } else if (e.key === 'Escape') {
    document.getElementById('search-tag-dropdown').classList.remove('open');
  }
}

function addSearchTag(tag) {
  if (searchActiveTags.includes(tag)) return;
  searchActiveTags.push(tag);
  document.getElementById('search-tag-input').value = '';
  document.getElementById('search-tag-dropdown').classList.remove('open');
  renderSearchTagChips();
  doSearch();
}

function removeSearchTag(tag) {
  searchActiveTags = searchActiveTags.filter(t => t !== tag);
  renderSearchTagChips();
  doSearch();
}

function renderSearchTagChips() {
  const bar = document.getElementById('search-tags-bar');
  // 移除舊的 chip（保留輸入框）
  bar.querySelectorAll('.search-tag-chip').forEach(c => c.remove());
  const wrap = bar.querySelector('.search-tags-input-wrap');
  searchActiveTags.forEach(tag => {
    const chip = document.createElement('div');
    chip.className = 'search-tag-chip active';
    chip.innerHTML = `${esc(tag)}<span class="rm" onclick="removeSearchTag('${esc(tag)}')">×</span>`;
    bar.insertBefore(chip, wrap);
  });
}

// ── Filters ───────────────────────────────────────────────────────────────
function filterCat(el, cat) {
  document.querySelectorAll('.nav-item').forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  currentCat = cat;
  doSearch();
}

function toggleTag(el, tag) {
  if (activeTags.includes(tag)) {
    activeTags = activeTags.filter(t => t !== tag);
    el.classList.remove('active');
  } else {
    activeTags.push(tag);
    el.classList.add('active');
  }
  doSearch();
}

// ── Add Modal ─────────────────────────────────────────────────────────────
function openAddModal() { document.getElementById('add-modal').classList.add('open'); loadGroups(); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

function switchTab(type) {
  ['text','note','image','video','pdf'].forEach(t => {
    document.getElementById('tab-'+t).style.display = t===type ? '' : 'none';
    document.querySelectorAll('.tab')[['text','note','image','video','pdf'].indexOf(t)].classList.toggle('active', t===type);
  });
  if (type === 'note') {
    setTimeout(() => document.getElementById('note-editor').focus(), 100);
  }
}

function setImp(el, val) {
  document.querySelectorAll('#txt-imp .imp-btn').forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  currentImp = val;
}

// ── 富文字編輯器 ─────────────────────────────────────────────────────────────
function execCmd(cmd, val=null) {
  document.getElementById('note-editor').focus();
  document.execCommand(cmd, false, val);
}

function insertHtml(html) {
  document.getElementById('note-editor').focus();
  document.execCommand('insertHTML', false, html);
}

function insertEditorImage() {
  document.getElementById('editor-img-input').click();
}

function handleEditorImage(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('note-editor').focus();
    document.execCommand('insertHTML', false,
      `<img src="${e.target.result}" style="max-width:100%;border-radius:6px;margin:6px 0">`);
  };
  reader.readAsDataURL(file);
  input.value = '';
}

async function submitNote() {
  const title = document.getElementById('note-title').value.trim();
  const editor = document.getElementById('note-editor');
  const html = editor.innerHTML.trim();
  const text = editor.innerText.trim();
  if (!title) return alert('請輸入筆記標題');
  if (!text) return alert('請輸入筆記內容');
  const tags = getTagsFrom('note');
  const btn = document.getElementById('note-submit-btn');
  btn.innerHTML = '儲存中<span class="loading"></span>';
  btn.disabled = true;
  const r = await fetch('/api/add/text', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ title, content: html, importance: currentImp, tags, is_note: true })
  });
  const d = await r.json();
  btn.innerHTML = '💾 儲存筆記'; btn.disabled = false;
  if (d.id) {
    closeModal('add-modal');
    document.getElementById('note-title').value = '';
    editor.innerHTML = '';
    clearTags('note');
    await init();
  } else { alert('儲存失敗：' + (d.error||'未知錯誤')); }
}

async function submitText() {
  const title = document.getElementById('txt-title').value.trim();
  const content = document.getElementById('txt-content').value.trim();
  if (!title) return alert('請輸入標題');
  const tags = getTagsFrom('txt');
  const btn = document.getElementById('txt-submit-btn');
  btn.innerHTML = '儲存中<span class="loading"></span>';
  btn.disabled = true;
  const r = await fetch('/api/add/text', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ title, content, importance: currentImp, tags })
  });
  const d = await r.json();
  btn.innerHTML = '儲存（AI 自動分類）'; btn.disabled = false;
  if (d.id) {
    closeModal('add-modal');
    document.getElementById('txt-title').value = '';
    document.getElementById('txt-content').value = '';
    clearTags('txt');
    await Promise.all([init()]);
  } else { alert('儲存失敗：' + (d.error||'未知錯誤')); }
}

// ── 圖片子模式 ───────────────────────────────────────────────────────────────
let _imgMode = 'single';

function switchImgMode(mode) {
  _imgMode = mode;
  ['single','multi','group'].forEach(m => {
    document.getElementById('img-mode-'+m).style.display = m===mode ? '' : 'none';
    document.getElementById('img-mode-btn-'+m).classList.toggle('active', m===mode);
  });
  selectedFiles['image'] = [];
  const btn = document.getElementById('img-submit-btn');
  btn.style.display = 'none';
  document.getElementById('img-progress').textContent = '';
  ['single','multi','group'].forEach(m => {
    const p = document.getElementById('img-preview-'+m);
    if (p) p.innerHTML = '';
  });
  if (mode === 'group') loadGroups();
}

function _showPreview(files, previewId) {
  const box = document.getElementById(previewId);
  if (!box) return;
  box.innerHTML = '';
  files.slice(0,12).forEach(f => {
    const url = URL.createObjectURL(f);
    const img = document.createElement('img');
    img.src = url;
    img.style.cssText = 'width:60px;height:60px;object-fit:cover;border-radius:6px;border:1px solid var(--border)';
    box.appendChild(img);
  });
  if (files.length > 12) {
    const more = document.createElement('div');
    more.style.cssText = 'width:60px;height:60px;border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:.75rem;color:var(--muted)';
    more.textContent = '+' + (files.length - 12);
    box.appendChild(more);
  }
}

function _showUploadBtn(count) {
  const btn = document.getElementById('img-submit-btn');
  btn.style.display = '';
  btn.textContent = count === 1 ? '⬆️ 上傳圖片' : `⬆️ 上傳 ${count} 張圖片`;
  btn.disabled = false;
}

function fileSelectedSingle(input) {
  if (!input.files[0]) return;
  selectedFiles['image'] = [input.files[0]];
  document.getElementById('img-drop-text-single').textContent = '✅ ' + input.files[0].name;
  _showPreview(selectedFiles['image'], 'img-preview-single');
  _showUploadBtn(1);
}
function dropFileSingle(e) {
  e.preventDefault(); e.currentTarget.classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files).filter(f=>f.type.startsWith('image/')).slice(0,1);
  if (!files.length) return;
  selectedFiles['image'] = files;
  document.getElementById('img-drop-text-single').textContent = '✅ ' + files[0].name;
  _showPreview(files, 'img-preview-single');
  _showUploadBtn(1);
}

function fileSelectedMulti(input) {
  const files = Array.from(input.files);
  if (!files.length) return;
  selectedFiles['image'] = files;
  document.getElementById('img-drop-text-multi').textContent = `✅ 已選取 ${files.length} 張`;
  _showPreview(files, 'img-preview-multi');
  _showUploadBtn(files.length);
}
function dropFileMulti(e) {
  e.preventDefault(); e.currentTarget.classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files).filter(f=>f.type.startsWith('image/'));
  if (!files.length) return;
  selectedFiles['image'] = files;
  document.getElementById('img-drop-text-multi').textContent = `✅ 已拖曳 ${files.length} 張`;
  _showPreview(files, 'img-preview-multi');
  _showUploadBtn(files.length);
}

function fileSelectedGroup(input) {
  const files = Array.from(input.files);
  if (!files.length) return;
  selectedFiles['image'] = files;
  document.getElementById('img-drop-text-group').textContent = `✅ 已選取 ${files.length} 張`;
  _showPreview(files, 'img-preview-group');
  _showUploadBtn(files.length);
}
function dropFileGroup(e) {
  e.preventDefault(); e.currentTarget.classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files).filter(f=>f.type.startsWith('image/'));
  if (!files.length) return;
  selectedFiles['image'] = files;
  document.getElementById('img-drop-text-group').textContent = `✅ 已拖曳 ${files.length} 張`;
  _showPreview(files, 'img-preview-group');
  _showUploadBtn(files.length);
}

function fileSelected(input, type) {
  if (type === 'image') {
    selectedFiles['image'] = Array.from(input.files);
    const dropText = document.getElementById('img-drop-text');
    dropText.textContent = `✅ 已選取 ${input.files.length} 張`;
    showImgPreview(selectedFiles['image']);
    // 顯示上傳按鈕
    const btn = document.getElementById('img-submit-btn');
    btn.style.display = '';
    btn.textContent = `⬆️ 上傳 ${input.files.length} 張圖片`;
    btn.disabled = false;
  } else {
    selectedFiles[type] = input.files[0];
    const dropText = document.getElementById('vid-drop-text');
    if (input.files[0]) dropText.textContent = '✅ 已選取：' + input.files[0].name;
  }
}

function showImgPreview(files) {
  const box = document.getElementById('img-preview');
  if (!box) return;
  box.innerHTML = '';
  files.slice(0, 12).forEach(f => {
    const url = URL.createObjectURL(f);
    const img = document.createElement('img');
    img.src = url;
    img.style.cssText = 'width:60px;height:60px;object-fit:cover;border-radius:6px;border:1px solid var(--border)';
    box.appendChild(img);
  });
  if (files.length > 12) {
    const more = document.createElement('div');
    more.style.cssText = 'width:60px;height:60px;border-radius:6px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:.75rem;color:var(--muted)';
    more.textContent = '+' + (files.length - 12);
    box.appendChild(more);
  }
}

function dragOver(e) { e.preventDefault(); e.currentTarget.classList.add('dragover'); }

function dropFile(e, type) {
  e.preventDefault();
  e.currentTarget.classList.remove('dragover');
  if (type === 'image') {
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (!files.length) return;
    selectedFiles['image'] = files;
    document.getElementById('img-drop-text').textContent = `✅ 已選取 ${files.length} 張`;
    showImgPreview(files);
    // 顯示上傳按鈕
    const btn = document.getElementById('img-submit-btn');
    btn.style.display = '';
    btn.textContent = `⬆️ 上傳 ${files.length} 張圖片`;
    btn.disabled = false;
  } else {
    const file = e.dataTransfer.files[0];
    if (file) {
      selectedFiles[type] = file;
      document.getElementById('vid-drop-text').textContent = '✅ 已選取：' + file.name;
    }
  }
}

async function submitFile(type) {
  if (type === 'image') {
    const files = selectedFiles['image'];
    if (!files || !files.length) return alert('請先選擇圖片');
    const btn = document.getElementById('img-submit-btn');
    const progress = document.getElementById('img-progress');
    btn.disabled = true;

    // 群組模式：檢查是否選了群組
    let groupId = '';
    if (_imgMode === 'group') {
      groupId = document.getElementById('img-group-select')?.value || '';
      if (!groupId) { btn.disabled = false; return alert('請先選擇或建立群組'); }
    }

    let done = 0, failed = 0;
    for (const file of files) {
      progress.textContent = `上傳中 ${done+failed+1} / ${files.length}：${file.name}`;
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name.replace(/\.[^.]+$/, ''));
      formData.append('importance', currentImp);
      if (groupId) formData.append('group_id', groupId);
      try {
        const r = await fetch('/api/add/image', { method:'POST', body: formData });
        const d = await r.json();
        if (d.id) done++; else failed++;
      } catch { failed++; }
    }
    btn.disabled = false;
    progress.innerHTML = `✅ 完成！成功 <b style="color:var(--accent)">${done}</b> 張` + (failed ? `，失敗 ${failed} 張` : '');
    selectedFiles['image'] = [];
    ['single','multi','group'].forEach(m => {
      const p = document.getElementById('img-preview-'+m);
      if (p) p.innerHTML = '';
    });
    btn.style.display = 'none';
    await Promise.all([init(), loadAllTags()]);
    setTimeout(() => { progress.textContent = ''; closeModal('add-modal'); }, 1500);
    return;
  }
  // 影片
  const file = selectedFiles[type];
  if (!file) return alert('請先選擇檔案');
  const title = document.getElementById('vid-title').value.trim();
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', title);
  formData.append('importance', currentImp);
  const btn = document.getElementById(type+'-submit-btn');
  btn.innerHTML = '處理中（AI分析）<span class="loading"></span>';
  btn.disabled = true;
  const r = await fetch('/api/add/'+type, { method:'POST', body: formData });
  const d = await r.json();
  btn.innerHTML = '上傳並擷取關鍵畫面'; btn.disabled=false;
  if (d.id) {
    closeModal('add-modal');
    selectedFiles[type] = null;
    await init();
  } else { alert('上傳失敗：'+(d.error||'未知錯誤')); }
}

// ── Detail ────────────────────────────────────────────────────────────────
async function openDetail(id) {
  const r = await fetch('/api/entry/'+id);
  const item = await r.json();
  document.getElementById('detail-title').textContent = item.title;
  const stars = '★'.repeat(Math.min(item.importance,5)) + '☆'.repeat(Math.max(0,5-item.importance));
  const tagStr = (item.tags||[]).join(', ');
  let html = ``;

  // PDF 特殊處理
  const content = item.content || '';
  console.log('[PDF DEBUG] content:', content.slice(0, 80));
  const pdfMatch = content.match(/\[PDF_FILE:([^\]]+)\]/);
  console.log('[PDF DEBUG] pdfMatch:', pdfMatch);
  if (pdfMatch) {
    const filename = pdfMatch[1];
    const pdfUrl   = `/api/pdf/${filename}`;
    const dlUrl    = `/api/pdf/${filename}/download`;
    const textContent = content.replace(/\[PDF_FILE:[^\]]+\]\n*/, '').trim();
    html += `
      <div style="margin-bottom:12px;display:flex;gap:8px;">
        <a href="${pdfUrl}" target="_blank" class="btn btn-primary" style="padding:6px 14px;font-size:.82rem;text-decoration:none;">🔍 在線預覽</a>
        <a href="${dlUrl}" class="btn btn-ghost" style="padding:6px 14px;font-size:.82rem;text-decoration:none;">⬇️ 下載 PDF</a>
      </div>
      <iframe src="${pdfUrl}" style="width:100%;height:480px;border:1px solid var(--border);border-radius:8px;background:#fff;"></iframe>
      ${textContent ? `<div style="margin-top:12px;font-size:.8rem;color:var(--muted);white-space:pre-wrap;max-height:200px;overflow-y:auto">${esc(textContent.slice(0,800))}${textContent.length>800?'...':''}</div>` : ''}
    `;
    document.getElementById('detail-body').innerHTML = html;
    document.getElementById('detail-modal').classList.add('open');
    return;
  }
  if (item.thumb_path) html += `<img class="detail-img" src="/api/thumb/${item.id}" onerror="this.style.display='none'" onclick="openLightbox(event,'/api/file/${item.id}')" style="cursor:zoom-in" title="點擊看大圖">`;
  if (item.ai_summary) html += `<div style="color:var(--accent2);font-size:.82rem;margin-bottom:12px">💡 ${esc(item.ai_summary)}</div>`;
  if (item.content) {
    // 判斷是否為 HTML 筆記（包含 HTML 標籤）
    const isHtml = /<[a-z][\s\S]*>/i.test(item.content);
    if (isHtml) {
      html += `<div class="editor-body" style="min-height:unset;max-height:unset;border:none;padding:0;margin-bottom:12px;cursor:default" contenteditable="false">${item.content}</div>`;
    } else {
      html += `<div class="detail-content" style="margin-bottom:12px">${esc(item.content)}</div>`;
    }
  }
  if (item.ocr_text) html += `<div style="font-size:.75rem;color:var(--muted);margin-bottom:4px">OCR 文字</div><div class="ocr-block" style="margin-bottom:14px">${esc(item.ocr_text)}</div>`;

  // 可編輯區塊
  const isHtmlContent = item.content && /<[a-z][\s\S]*>/i.test(item.content);
  html += `
  <div style="background:var(--bg);border-radius:10px;padding:14px;margin-bottom:14px">
    <div style="font-size:.72rem;color:var(--muted);margin-bottom:10px;letter-spacing:.05em">✏️ 編輯資訊</div>
    <div class="form-group">
      <label class="form-label">標題</label>
      <input class="form-input" id="edit-title" value="${esc(item.title)}">
    </div>
    <div class="form-group">
      <label class="form-label">內容</label>
      ${isHtmlContent ? `
        <div class="editor-toolbar">
          <button class="editor-btn" onclick="execEditCmd('bold')"><b>B</b></button>
          <button class="editor-btn" onclick="execEditCmd('italic')"><i>I</i></button>
          <button class="editor-btn" onclick="execEditCmd('underline')"><u>U</u></button>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="execEditCmd('insertUnorderedList')">• 清單</button>
          <button class="editor-btn" onclick="execEditCmd('insertOrderedList')">1. 清單</button>
          <div class="editor-sep"></div>
          <button class="editor-btn" onclick="execEditCmd('removeFormat')">✕格式</button>
        </div>
        <div class="editor-body" id="edit-content-html" contenteditable="true" style="min-height:120px">${item.content}</div>
      ` : `
        <textarea class="form-textarea" id="edit-content-text" style="min-height:120px">${esc(item.content || '')}</textarea>
      `}
    </div>
    <div class="form-group">
      <label class="form-label">分類</label>
      <select class="form-select" id="edit-category">
        ${['技術/程式','AI/機器學習','筆記/學習','工作/專案','影片/媒體','圖片/視覺','參考資料','個人/日記','未分類'].map(c =>
          `<option value="${c}" ${c===item.category?'selected':''}>${c}</option>`
        ).join('')}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">標籤</label>
      <div class="tag-input-wrap" id="edit-tag-wrap">
        <div class="tag-chips" id="edit-tag-chips" onclick="focusTagInput('edit')">
          ${(item.tags||[]).map(t => `<span class="tag-chip-item" data-tag="${esc(t)}">${esc(t)}<span class="rm" onclick="removeTag(event,'edit','${esc(t)}')">×</span></span>`).join('')}
          <input class="tag-text-input" id="edit-tag-input" placeholder="新增標籤..." autocomplete="off"
            oninput="tagInputChanged('edit')" onkeydown="tagInputKey(event,'edit')" onfocus="tagInputChanged('edit')" onblur="tagBlur('edit')">
        </div>
        <div class="tag-dropdown" id="edit-tag-dropdown"></div>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">重要性</label>
      <div class="imp-row" id="edit-imp-row">
        ${[1,3,5,7,9].map(v=>`<div class="imp-btn ${v===item.importance?'active':''}" onclick="setEditImp(this,${v})">${v}</div>`).join('')}
      </div>
    </div>
    <button class="btn btn-primary" onclick="saveEntry(${item.id}, ${isHtmlContent})" style="margin-top:4px">💾 儲存變更</button>
    <span id="save-msg" style="font-size:.78rem;color:var(--accent);margin-left:10px"></span>
  </div>`;

  html += `<div style="display:flex;gap:8px"><button class="btn btn-danger" onclick="deleteEntry(${item.id})">刪除</button></div>`;
  document.getElementById('detail-body').innerHTML = html;
  document.getElementById('detail-modal').classList.add('open');
  // 儲存目前重要性
  document.getElementById('edit-imp-row').dataset.val = item.importance;
}

function setEditImp(el, val) {
  document.querySelectorAll('#edit-imp-row .imp-btn').forEach(e => e.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('edit-imp-row').dataset.val = val;
}

function execEditCmd(cmd) {
  document.getElementById('edit-content-html').focus();
  document.execCommand(cmd, false, null);
}

async function saveEntry(id, isHtml) {
  const titleEl = document.getElementById('edit-title');
  const title = titleEl ? titleEl.value.trim() : '';
  let content = '';
  if (isHtml) {
    const el = document.getElementById('edit-content-html');
    content = el ? el.innerHTML.trim() : '';
  } else {
    const el = document.getElementById('edit-content-text');
    content = el ? el.value.trim() : '';
  }
  const category   = document.getElementById('edit-category').value;
  const tags = getTagsFrom('edit');
  const importance = parseInt(document.getElementById('edit-imp-row').dataset.val || 5);
  const r = await fetch('/api/entry/'+id+'/update', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({title, content, category, tags, importance})
  });
  const d = await r.json();
  const msg = document.getElementById('save-msg');
  if (d.ok) {
    msg.textContent = '✅ 已儲存';
    await init();
    setTimeout(() => { msg.textContent = ''; }, 2000);
  } else {
    msg.textContent = '❌ 儲存失敗';
  }
}

async function deleteEntry(id) {
  if (!confirm('確定刪除？')) return;
  await fetch('/api/entry/'+id, {method:'DELETE'});
  closeModal('detail-modal');
  await init();
}

// ── 標籤選擇器 ───────────────────────────────────────────────────────────────
let _allTags = [];

async function loadAllTags() {
  const r = await fetch('/api/tags');
  _allTags = await r.json();
}

function getTagsFrom(prefix) {
  const chips = document.querySelectorAll(`#${prefix}-tag-chips .tag-chip-item`);
  return Array.from(chips).map(c => c.dataset.tag).filter(Boolean);
}

function clearTags(prefix) {
  const chips = document.querySelectorAll(`#${prefix}-tag-chips .tag-chip-item`);
  chips.forEach(c => c.remove());
  const inp = document.getElementById(`${prefix}-tag-input`);
  if (inp) inp.value = '';
}

function focusTagInput(prefix) {
  document.getElementById(`${prefix}-tag-input`).focus();
}

function addTag(prefix, tag) {
  tag = tag.trim();
  if (!tag) return;
  // 避免重複
  const existing = getTagsFrom(prefix);
  if (existing.includes(tag)) return;
  const chips = document.getElementById(`${prefix}-tag-chips`);
  const inp = document.getElementById(`${prefix}-tag-input`);
  const chip = document.createElement('span');
  chip.className = 'tag-chip-item';
  chip.dataset.tag = tag;
  chip.innerHTML = `${esc(tag)}<span class="rm" onclick="removeTag(event,'${prefix}','${esc(tag)}')">×</span>`;
  chips.insertBefore(chip, inp);
  inp.value = '';
  closeTagDropdown(prefix);
}

function removeTag(e, prefix, tag) {
  e.stopPropagation();
  const chip = document.querySelector(`#${prefix}-tag-chips .tag-chip-item[data-tag="${tag}"]`);
  if (chip) chip.remove();
}

function tagInputChanged(prefix) {
  const inp = document.getElementById(`${prefix}-tag-input`);
  const q = inp.value.trim().toLowerCase();
  const existing = getTagsFrom(prefix);
  const dropdown = document.getElementById(`${prefix}-tag-dropdown`);

  // 過濾標籤
  let matched = _allTags.filter(t => !existing.includes(t) && t.toLowerCase().includes(q));
  if (matched.length === 0 && !q) { closeTagDropdown(prefix); return; }

  let html = matched.slice(0, 10).map(t =>
    `<div class="tag-option" onmousedown="addTag('${prefix}','${esc(t)}')">${esc(t)}</div>`
  ).join('');

  // 自輸選項
  if (q && !_allTags.includes(q) && !existing.includes(q)) {
    html += `<div class="tag-option" onmousedown="addTag('${prefix}','${esc(q)}')">${esc(q)} <span class="new-badge">新標籤</span></div>`;
  }

  if (!html) { closeTagDropdown(prefix); return; }
  dropdown.innerHTML = html;
  dropdown.classList.add('open');
}

function tagInputKey(e, prefix) {
  const inp = document.getElementById(`${prefix}-tag-input`);
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault();
    const val = inp.value.trim().replace(/,$/, '');
    if (val) addTag(prefix, val);
  } else if (e.key === 'Backspace' && !inp.value) {
    // 刪除最後一個標籤
    const chips = document.querySelectorAll(`#${prefix}-tag-chips .tag-chip-item`);
    if (chips.length) chips[chips.length-1].remove();
  }
}

function tagBlur(prefix) {
  // 延遲關閉讓 mousedown 先觸發
  setTimeout(() => closeTagDropdown(prefix), 150);
  // 把還在輸入框的文字加為標籤
  const inp = document.getElementById(`${prefix}-tag-input`);
  if (inp && inp.value.trim()) addTag(prefix, inp.value.trim());
}

function closeTagDropdown(prefix) {
  const dd = document.getElementById(`${prefix}-tag-dropdown`);
  if (dd) { dd.classList.remove('open'); dd.innerHTML = ''; }
}

// ── 群組輪播 ─────────────────────────────────────────────────────────────────
let _groupImages = [];
let _groupIdx = 0;

async function loadGroups() {
  const r = await fetch('/api/groups');
  const groups = await r.json();
  const sel = document.getElementById('img-group-select');
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = '<option value="">不加入群組</option>';
  groups.forEach(g => {
    sel.innerHTML += `<option value="${g.id}">${esc(g.name)}（${g.count} 張）</option>`;
  });
  if (cur) sel.value = cur;
}

async function createNewGroup() {
  const name = prompt('新群組名稱：');
  if (!name || !name.trim()) return;
  const r = await fetch('/api/groups', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name: name.trim()})
  });
  const d = await r.json();
  if (d.id) {
    await loadGroups();
    document.getElementById('img-group-select').value = d.id;
  }
}

async function openGroupModal(e, groupId) {
  e.stopPropagation();
  const r = await fetch('/api/groups/' + groupId);
  const d = await r.json();
  _groupImages = d.images || [];
  _groupIdx = 0;
  document.getElementById('group-title').textContent = d.group.name || '群組';
  document.getElementById('group-modal').classList.add('open');
  document.body.style.overflow = 'hidden';
  renderCarousel();
}

function closeGroupModal() {
  document.getElementById('group-modal').classList.remove('open');
  document.body.style.overflow = '';
  _groupImages = [];
}

function renderCarousel() {
  if (!_groupImages.length) return;
  const item = _groupImages[_groupIdx];
  document.getElementById('carousel-img').src = '/api/file/' + item.id;
  document.getElementById('group-counter').textContent = `${_groupIdx + 1} / ${_groupImages.length}`;
  // dots
  const dots = document.getElementById('group-dots');
  dots.innerHTML = _groupImages.map((_, i) =>
    `<div class="g-dot ${i===_groupIdx?'active':''}" onclick="carouselGo(${i})"></div>`
  ).join('');
}

function carouselPrev() {
  if (!_groupImages.length) return;
  _groupIdx = (_groupIdx - 1 + _groupImages.length) % _groupImages.length;
  renderCarousel();
}

function carouselNext() {
  if (!_groupImages.length) return;
  _groupIdx = (_groupIdx + 1) % _groupImages.length;
  renderCarousel();
}

function carouselGo(i) { _groupIdx = i; renderCarousel(); }

// 鍵盤左右鍵控制
document.addEventListener('keydown', e => {
  if (!document.getElementById('group-modal').classList.contains('open')) return;
  if (e.key === 'ArrowLeft') carouselPrev();
  if (e.key === 'ArrowRight') carouselNext();
  if (e.key === 'Escape') closeGroupModal();
});

// 觸控滑動
let _touchStartX = 0;
document.getElementById && document.addEventListener('DOMContentLoaded', () => {
  const carousel = document.getElementById('group-carousel');
  if (!carousel) return;
  carousel.addEventListener('touchstart', e => { _touchStartX = e.touches[0].clientX; });
  carousel.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - _touchStartX;
    if (dx > 50) carouselPrev();
    else if (dx < -50) carouselNext();
  });
});

// ── Lightbox ─────────────────────────────────────────────────────────────
function openLightbox(e, src) {
  e.stopPropagation();
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
  document.getElementById('lightbox-img').src = '';
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeLightbox();
});

// ── Utils ─────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

init();

// 偵測 URL hash，自動開啟對應功能
if (window.location.hash === '#code-rules') {
  setTimeout(() => openCodeRules(), 800);
  history.replaceState(null, '', window.location.pathname);
}

// ── 即時同步 WebSocket ────────────────────────────────────────────────────
const socket = io();
const syncDot = document.getElementById('sync-dot');
const syncBadge = document.getElementById('sync-badge');

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2500);
}

socket.on('connect', () => {
  syncDot.className = 'sync-dot online';
  syncBadge.textContent = '已連線';
});

socket.on('disconnect', () => {
  syncDot.className = 'sync-dot';
  syncBadge.textContent = '離線';
});

// 收到其他設備的更新 → 重新整理畫面
socket.on('entry_added', data => {
  showToast(`📥 新增：${data.title}`);
  init();
});

socket.on('entry_updated', data => {
  showToast(`✏️ 已更新：${data.title}`);
  init();
});

socket.on('entry_deleted', data => {
  showToast(`🗑 已刪除一筆資料`);
  init();
});

socket.on('tags_updated', data => {
  _allTags = data.tags || [];
});

socket.on('groups_updated', () => {
  loadGroups();
});

// ── 立AI 聊天泡泡 ─────────────────────────────────────────────────────────
function toggleChat() {
  const panel = document.getElementById('chat-panel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open') && document.querySelectorAll('.msg').length === 0) {
    appendMsg('ai', '你好！我是立，有什麼想問我的嗎？我會同時參考你的知識庫來回答。', '立AI');
  }
}

function appendMsg(role, text, source) {
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  if (role === 'ai') {
    div.innerHTML = '<div class="src">🤖 ' + esc(source||'立') + '</div>' + esc(text).replace(/\n/g,'<br>');
  } else {
    div.textContent = text;
  }
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function appendSaveBar(msgDiv, question, reply, source) {
  // 在 AI 訊息泡泡下方加「存入知識庫？」確認列
  const bar = document.createElement('div');
  bar.className = 'msg-save-bar';
  bar.innerHTML = `
    <span style="font-size:.7rem;color:var(--muted);align-self:center;">存進知識庫？</span>
    <button class="msg-save-btn msg-save-yes" onclick="confirmSaveChat(this,'${_escAttr(question)}','${_escAttr(reply)}','${_escAttr(source)}')">💾 存入</button>
    <button class="msg-save-btn msg-save-no"  onclick="dismissSaveBar(this)">✕ 不用</button>
  `;
  msgDiv.appendChild(bar);
}

function _escAttr(s) {
  return String(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/\n/g,'\\n');
}

async function confirmSaveChat(btn, question, reply, source) {
  btn.parentElement.innerHTML = '<span class="msg-save-done">⏳ 儲存中...</span>';
  const title = `【對話】${question.length > 40 ? question.slice(0,40) + '...' : question}`;
  // content 存你問的問題，ai_summary 位置概念上是立AI的回答
  // 但 add_text 只有 content，所以備註在後面讓人看得出來
  const content = question;
  const r = await fetch('/api/add/text', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      title,
      content,
      importance: 5,
      tags: ['對話紀錄', '立AI推理'],
    })
  });
  const d = await r.json();
  if (d.id) {
    btn.closest('.msg-save-bar').innerHTML = '<span class="msg-save-done">✅ 已存入知識庫</span>';
    await Promise.all([init(), loadAllTags()]);
  } else {
    btn.closest('.msg-save-bar').innerHTML = '<span class="msg-save-done" style="color:var(--danger)">❌ 儲存失敗</span>';
  }
}

function dismissSaveBar(btn) {
  btn.closest('.msg-save-bar').innerHTML = '<span class="msg-save-done">已略過</span>';
  setTimeout(() => { btn.closest && btn.closest('.msg-save-bar') && btn.closest('.msg-save-bar').remove(); }, 1200);
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendMsg('user', text);
  const sendBtn = document.getElementById('chat-send');
  sendBtn.disabled = true;
  const thinking = appendMsg('ai', '思考中...', '立');
  thinking.classList.add('thinking');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 240000); // 4分鐘
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, mode: _currentMode}),
      signal: controller.signal
    });
    clearTimeout(timer);
    const d = await r.json();
    thinking.remove();
    const replyText = d.reply || '（無回應）';
    const sourceText = d.source || '立';
    const msgDiv = appendMsg('ai', replyText, sourceText);
    // 只有 library 模式的推理回答才顯示存入確認
    if (d.saveable && _currentMode === 'library') {
      appendSaveBar(msgDiv, text, replyText, sourceText);
    }
  } catch(e) {
    clearTimeout(timer);
    thinking.remove();
    if (e.name === 'AbortError') {
      appendMsg('ai', '回應逾時（超過4分鐘），請再試一次或換個問法', '系統');
    } else {
      appendMsg('ai', '連線失敗，請確認立AI是否在線', '系統');
    }
  }
  sendBtn.disabled = false;
}

// ── PDF 上傳 ──────────────────────────────────────────────────────────────────
let _pdfFiles = [];

function fileSelectedPDF(input) {
  _pdfFiles = Array.from(input.files);
  if (!_pdfFiles.length) return;
  document.getElementById('pdf-preview').innerHTML = _pdfFiles.map(f =>
    `<div style="padding:4px 0;border-bottom:1px solid var(--border)">📑 ${esc(f.name)} <span style="color:var(--muted)">(${(f.size/1024).toFixed(1)} KB)</span></div>`
  ).join('');
  const btn = document.getElementById('pdf-submit-btn');
  btn.style.display = ''; btn.textContent = `⬆️ 上傳 ${_pdfFiles.length} 個 PDF`; btn.disabled = false;
  document.getElementById('pdf-drop-text').textContent = `✅ 已選取 ${_pdfFiles.length} 個 PDF`;
}

function dropFilePDF(e) {
  e.preventDefault(); e.currentTarget.classList.remove('dragover');
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (!files.length) return;
  _pdfFiles = files;
  document.getElementById('pdf-preview').innerHTML = files.map(f =>
    `<div style="padding:4px 0;">📑 ${esc(f.name)}</div>`).join('');
  const btn = document.getElementById('pdf-submit-btn');
  btn.style.display = ''; btn.textContent = `⬆️ 上傳 ${files.length} 個 PDF`; btn.disabled = false;
  document.getElementById('pdf-drop-text').textContent = `✅ 已拖曳 ${files.length} 個 PDF`;
}

async function submitPDF() {
  if (!_pdfFiles.length) return alert('請先選擇 PDF');
  const tags = getTagsFrom('pdf');
  const btn = document.getElementById('pdf-submit-btn');
  const progress = document.getElementById('pdf-progress');
  btn.disabled = true;
  let done = 0, failed = 0;
  for (const file of _pdfFiles) {
    progress.textContent = `上傳中 ${done+failed+1} / ${_pdfFiles.length}：${file.name}`;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name.replace(/\.pdf$/i, ''));
    formData.append('tags', JSON.stringify(tags));
    formData.append('importance', currentImp);
    try {
      const r = await fetch('/api/add/pdf', { method:'POST', body: formData });
      const d = await r.json();
      if (d.id) done++; else failed++;
    } catch { failed++; }
  }
  btn.disabled = false;
  progress.innerHTML = `✅ 成功 <b style="color:var(--accent)">${done}</b> 個` + (failed ? `，失敗 ${failed} 個` : '');
  _pdfFiles = [];
  document.getElementById('pdf-preview').innerHTML = '';
  document.getElementById('pdf-drop-text').innerHTML = '📑 點擊或拖曳 PDF 到這裡<br><small>支援多檔，自動擷取文字內容</small>';
  btn.style.display = 'none';
  await Promise.all([init(), loadAllTags()]);
  setTimeout(() => { progress.textContent = ''; closeModal('add-modal'); }, 1500);
}

document.addEventListener('DOMContentLoaded', () => {
  restoreSidebar();
  // 聊天輸入框 Enter 送出
  const inp = document.getElementById('chat-input');
  if (inp) {
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
  }
  // 圖片上傳按鈕
  const imgBtn = document.getElementById('img-submit-btn');
  if (imgBtn) imgBtn.addEventListener('click', () => submitFile('image'));
  const pdfBtn = document.getElementById('pdf-submit-btn');
  if (pdfBtn) pdfBtn.addEventListener('click', () => submitPDF());
});
</script>

<!-- Toast 通知 -->
<div class="toast" id="toast"></div>

<!-- 程式碼規範庫 Modal -->
<div class="modal-overlay" id="code-rules-modal" style="align-items:stretch;padding:0;">
  <div style="background:var(--bg);width:100%;height:100%;display:flex;flex-direction:column;overflow:hidden;">
    <!-- Header -->
    <div style="background:var(--surface);border-bottom:1px solid var(--border);padding:14px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0;">
      <h2 style="color:var(--accent2);font-size:1rem;font-weight:900;">📐 程式碼規範庫</h2>
      <span style="font-size:.75rem;color:var(--muted)">立AI 與 gpt-oss 的開發規範</span>
      <div style="flex:1"></div>
      <button class="btn btn-primary" onclick="openAddRule()" style="padding:6px 14px;font-size:.82rem;">＋ 新增規則</button>
      <button class="modal-close" onclick="closeCodeRules()" style="margin-left:8px;">✕</button>
    </div>
    <!-- Body -->
    <div style="display:flex;flex:1;overflow:hidden;">
      <!-- 左側分類 -->
      <div style="width:180px;background:var(--surface);border-right:1px solid var(--border);padding:12px 0;flex-shrink:0;overflow-y:auto;">
        <div id="code-cat-all" class="nav-item active" onclick="filterCodeCat('all',this)" style="font-size:.83rem;">全部規則</div>
        <div id="code-cat-coding" class="nav-item" onclick="filterCodeCat('coding',this)" style="font-size:.83rem;">📐 程式碼規則</div>
        <div id="code-cat-arch" class="nav-item" onclick="filterCodeCat('arch',this)" style="font-size:.83rem;">🏗 架構方向</div>
        <div id="code-cat-module" class="nav-item" onclick="filterCodeCat('module',this)" style="font-size:.83rem;">🔗 模組規則</div>
        <div id="code-cat-bug" class="nav-item" onclick="filterCodeCat('bug',this)" style="font-size:.83rem;">🐛 已知Bug與解法</div>
        <div id="code-cat-ai_rules" class="nav-item" onclick="filterCodeCat('ai_rules',this)" style="font-size:.83rem;">🤖 AI行為準則</div>
      </div>
      <!-- 規則列表 -->
      <div style="flex:1;overflow-y:auto;padding:16px;" id="code-rules-list">
        <div class="empty"><div class="icon">📐</div><div>載入中...</div></div>
      </div>
    </div>
  </div>
</div>

<!-- 新增/編輯規則 Modal -->
<div class="modal-overlay" id="add-rule-modal">
  <div class="modal" style="max-width:560px;">
    <div class="modal-header">
      <h2 id="rule-modal-title">新增規則</h2>
      <button class="modal-close" onclick="closeAddRule()">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="rule-edit-id">
      <div class="form-group">
        <label class="form-label">分類</label>
        <select class="form-select" id="rule-category">
          <option value="coding">📐 程式碼規則</option>
          <option value="arch">🏗 架構方向</option>
          <option value="module">🔗 模組規則</option>
          <option value="bug">🐛 已知Bug與解法</option>
          <option value="ai_rules">🤖 AI行為準則</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">標題</label>
        <input class="form-input" id="rule-title" placeholder="規則標題...">
      </div>
      <div class="form-group">
        <label class="form-label">內容</label>
        <textarea class="form-textarea" id="rule-content" rows="6" placeholder="詳細說明這條規則..."></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">優先級</label>
        <select class="form-select" id="rule-priority">
          <option value="1">🔴 必須遵守</option>
          <option value="2" selected>🟡 建議</option>
          <option value="3">🟢 參考</option>
        </select>
      </div>
      <div style="display:flex;gap:8px;margin-top:4px;">
        <button class="btn btn-primary" onclick="saveRule()">💾 儲存</button>
        <button class="btn btn-ghost" onclick="closeAddRule()">取消</button>
        <button class="btn btn-danger" id="rule-delete-btn" onclick="deleteRule()" style="display:none;margin-left:auto;">刪除</button>
      </div>
    </div>
  </div>
</div>

<!-- 群組輪播 -->
<div id="group-modal">
  <button id="group-close" onclick="closeGroupModal()">✕</button>
  <div id="group-title">群組</div>
  <div id="group-carousel">
    <button class="carousel-btn prev" onclick="carouselPrev()">‹</button>
    <img id="carousel-img" src="" alt="">
    <button class="carousel-btn next" onclick="carouselNext()">›</button>
  </div>
  <div id="group-counter">1 / 1</div>
  <div id="group-dots"></div>
</div>

<!-- Lightbox 大圖 -->
<div id="lightbox" onclick="closeLightbox()">
  <button id="lightbox-close" onclick="closeLightbox()">✕</button>
  <img id="lightbox-img" src="" alt="">
</div>

<!-- 自學紀錄 Modal -->
<div class="modal-overlay" id="learn-sessions-modal" style="align-items:stretch;padding:0;">
  <div style="background:var(--bg);width:100%;height:100%;display:flex;flex-direction:column;overflow:hidden;">
    <!-- Header -->
    <div style="background:var(--surface);border-bottom:1px solid var(--border);padding:14px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0;">
      <h2 style="color:#86efac;font-size:1rem;font-weight:900;">📂 自學紀錄</h2>
      <span style="font-size:.75rem;color:var(--muted)">每次自學的原始資料與立AI回答</span>
      <div style="flex:1"></div>
      <button class="modal-close" onclick="closeModal('learn-sessions-modal')">✕</button>
    </div>
    <!-- Body -->
    <div style="display:flex;flex:1;overflow:hidden;">
      <!-- 左側列表 -->
      <div style="width:280px;background:var(--surface);border-right:1px solid var(--border);overflow-y:auto;flex-shrink:0;" id="sessions-list">
        <div style="padding:12px 16px;font-size:.75rem;color:var(--muted);">載入中...</div>
      </div>
      <!-- 右側詳細 -->
      <div style="flex:1;overflow-y:auto;padding:24px;" id="session-detail">
        <div style="color:var(--muted);text-align:center;margin-top:80px;font-size:.9rem;">
          <div style="font-size:2.5rem;margin-bottom:12px;">📂</div>
          選擇左側紀錄來查看詳情
        </div>
      </div>
    </div>
  </div>
</div>

<!-- 立AI 聊天泡泡 -->
<div id="chat-bubble">
  <div id="chat-panel">
    <div id="chat-header">
      <div><div class="name">🦞 立 AI</div><div class="hint">知識庫 + Ollama</div></div>
      <button id="chat-close" onclick="toggleChat()">✕</button>
    </div>
    <div id="chat-messages"></div>
    <div id="chat-input-row">
      <textarea id="chat-input" placeholder="問立AI任何事..."></textarea>
      <button id="chat-send" onclick="sendChat()">送出</button>
    </div>
  </div>
  <button id="chat-toggle" onclick="toggleChat()" title="問立AI">🦞</button>
</div>

</body>
</html>"""

# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/stats")
def api_stats():
    return jsonify(get_store().stats())

@app.route("/api/categories")
def api_categories():
    return jsonify(get_store().get_categories())

@app.route("/api/tags")
def api_tags():
    return jsonify(get_store().get_tags())

@app.route("/api/search")
def api_search():
    q        = request.args.get("q", "")
    category = request.args.get("category", "")
    sort     = request.args.get("sort", "importance")
    tags_str = request.args.get("tags", "")
    tags     = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
    results  = get_store().search(query=q, category=category, tags=tags, sort=sort)
    return jsonify(results)

@app.route("/api/entry/<int:entry_id>")
def api_entry(entry_id):
    entry = get_store().get(entry_id)
    if not entry:
        return jsonify({"error": "not found"}), 404
    return jsonify(entry)

@app.route("/api/entry/<int:entry_id>", methods=["DELETE"])
def api_delete(entry_id):
    get_store().delete(entry_id)
    _broadcast('entry_deleted', {"id": entry_id})
    return jsonify({"ok": True})

@app.route("/api/entry/<int:entry_id>/update", methods=["POST"])
def api_update(entry_id):
    data = request.get_json(silent=True) or {}
    ok = get_store().update(entry_id,
        title      = data.get("title"),
        content    = data.get("content"),
        category   = data.get("category"),
        tags       = data.get("tags"),
        importance = int(data.get("importance", 5)),
    )
    if ok:
        entry = get_store().get(entry_id)
        _broadcast('entry_updated', {"id": entry_id, "title": entry.get("title","") if entry else ""})
        _broadcast('tags_updated', {"tags": get_store().get_tags()})
    return jsonify({"ok": ok})

@app.route("/api/thumb/<int:entry_id>")
def api_thumb(entry_id):
    from flask import send_file
    entry = get_store().get(entry_id)
    if not entry:
        return "", 404
    path = pathlib.Path(entry.get("thumb_path", ""))
    if not path.exists():
        path = pathlib.Path(entry.get("file_path", ""))
    if path.exists():
        return send_file(str(path))
    return "", 404

@app.route("/api/file/<int:entry_id>")
def api_file(entry_id):
    """回傳原始圖片（高畫質）"""
    from flask import send_file
    entry = get_store().get(entry_id)
    if not entry:
        return "", 404
    path = pathlib.Path(entry.get("file_path", ""))
    if path.exists():
        return send_file(str(path))
    # fallback 到縮圖
    path = pathlib.Path(entry.get("thumb_path", ""))
    if path.exists():
        return send_file(str(path))
    return "", 404

@app.route("/api/add/text", methods=["POST"])
def api_add_text():
    data       = request.get_json(silent=True) or {}
    title      = str(data.get("title", "")).strip()
    content    = str(data.get("content", "")).strip()
    importance = int(data.get("importance", 5))
    tags       = data.get("tags", [])
    if not title:
        return jsonify({"error": "標題不能為空"}), 400
    try:
        entry_id = get_store().add_text(title, content, importance, tags)
        _broadcast('entry_added', {"id": entry_id, "title": title})
        _broadcast('tags_updated', {"tags": get_store().get_tags()})
        return jsonify({"id": entry_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/add/image", methods=["POST"])
def api_add_image():
    if "file" not in request.files:
        return jsonify({"error": "沒有檔案"}), 400
    f        = request.files["file"]
    title    = request.form.get("title", "").strip()
    imp      = int(request.form.get("importance", 5))
    group_id = request.form.get("group_id", "")
    group_id = int(group_id) if group_id else None
    tmp = pathlib.Path("knowledge_data/tmp_" + f.filename)
    f.save(str(tmp))
    try:
        entry_id = get_store().add_image(str(tmp), title, imp, group_id=group_id)
        entry = get_store().get(entry_id)
        _broadcast('entry_added', {"id": entry_id, "title": entry.get("title","") if entry else title})
        _broadcast('tags_updated', {"tags": get_store().get_tags()})
        return jsonify({"id": entry_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        tmp.unlink(missing_ok=True)

@app.route("/api/add/video", methods=["POST"])
def api_add_video():
    if "file" not in request.files:
        return jsonify({"error": "沒有檔案"}), 400
    f     = request.files["file"]
    title = request.form.get("title", "").strip()
    imp   = int(request.form.get("importance", 5))
    tmp = pathlib.Path("knowledge_data/tmp_" + f.filename)
    f.save(str(tmp))
    try:
        entry_id = get_store().add_video(str(tmp), title, imp)
        entry = get_store().get(entry_id)
        _broadcast('entry_added', {"id": entry_id, "title": entry.get("title","") if entry else title})
        return jsonify({"id": entry_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        tmp.unlink(missing_ok=True)

# ── 群組 API ──────────────────────────────────────────────────────────────────

@app.route("/api/groups")
def api_groups():
    return jsonify(get_store().get_groups())

@app.route("/api/groups", methods=["POST"])
def api_create_group():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "名稱不能為空"}), 400
    group_id = get_store().create_group(name)
    _broadcast('groups_updated', {})
    return jsonify({"id": group_id})

@app.route("/api/groups/<int:group_id>")
def api_group(group_id):
    group = get_store().get_group(group_id)
    if not group:
        return jsonify({"error": "找不到群組"}), 404
    images = get_store().get_group_images(group_id)
    return jsonify({"group": group, "images": images})

@app.route("/api/groups/<int:group_id>", methods=["DELETE"])
def api_delete_group(group_id):
    get_store().delete_group(group_id)
    _broadcast('groups_updated', {})
    return jsonify({"ok": True})

@app.route("/api/add/pdf", methods=["POST"])
def api_add_pdf():
    if "file" not in request.files:
        return jsonify({"error": "沒有檔案"}), 400
    f     = request.files["file"]
    title = request.form.get("title", "").strip() or f.filename
    imp   = int(request.form.get("importance", 5))
    try:
        tags = json.loads(request.form.get("tags", "[]"))
    except Exception:
        tags = []

    # 永久儲存 PDF
    pdf_dir = pathlib.Path("knowledge_data/pdfs")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{int(_time.time())}_{f.filename}"
    pdf_path  = pdf_dir / safe_name
    f.save(str(pdf_path))

    try:
        content_text = ""
        try:
            import pypdf
            reader = pypdf.PdfReader(str(pdf_path))
            pages_text = []
            for page in reader.pages:
                t = page.extract_text()
                if t: pages_text.append(t.strip())
            content_text = "\n\n".join(pages_text)[:5000]
        except Exception as e:
            content_text = f"（PDF 文字擷取失敗：{e}）"

        full_content = f"[PDF_FILE:{safe_name}]\n\n{content_text}"
        entry_id = get_store().add_text(title=title, content=full_content,
                                        importance=imp, tags=tags + ["PDF"])
        _broadcast('entry_added', {"id": entry_id, "title": title})
        _broadcast('tags_updated', {"tags": get_store().get_tags()})
        return jsonify({"id": entry_id, "filename": safe_name})
    except Exception as e:
        pdf_path.unlink(missing_ok=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf/<filename>")
def api_serve_pdf(filename):
    from flask import send_file
    pdf_path = pathlib.Path("knowledge_data/pdfs") / filename
    if not pdf_path.exists():
        return jsonify({"error": "找不到檔案"}), 404
    return send_file(str(pdf_path), mimetype="application/pdf", as_attachment=False)

@app.route("/api/pdf/<filename>/download")
def api_download_pdf(filename):
    from flask import send_file
    pdf_path = pathlib.Path("knowledge_data/pdfs") / filename
    if not pdf_path.exists():
        return jsonify({"error": "找不到檔案"}), 404
    orig_name = "_".join(filename.split("_")[1:]) if "_" in filename else filename
    return send_file(str(pdf_path), mimetype="application/pdf",
                     as_attachment=True, download_name=orig_name)


# ── Ollama 工具函式 ───────────────────────────────────────────────────────────

# 模型優先順序：由大到小，自動 fallback
_LEARN_MODELS  = ["gpt-oss:20b", "qwen2.5:14b", "qwen2.5:7b", "gemma3:4b", "llama3.2:3b", "phi3:mini"]
_CHAT_MODELS   = ["gemma3:4b", "qwen2.5:7b", "llama3.2:3b", "phi3:mini"]
_VISION_MODELS = ["llava:7b", "llava:13b", "moondream"]

_available_models_cache: list[str] | None = None

def _get_available_models() -> list[str]:
    """向 Ollama 查詢已安裝的模型，結果快取。"""
    global _available_models_cache
    if _available_models_cache is not None:
        return _available_models_cache
    try:
        r = req.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        _available_models_cache = models
        logger.info(f"[Ollama] 已安裝模型：{models}")
        return models
    except Exception as e:
        logger.warning(f"[Ollama] 無法取得模型列表：{e}")
        return []

def _available_models_cache_reset():
    global _available_models_cache
    _available_models_cache = None

def _pick_model(candidates: list[str]) -> str | None:
    """從候選清單中選第一個已安裝的模型。"""
    available = _get_available_models()
    # 先精確比對，再前綴比對（例如 qwen2.5:7b 會匹配 qwen2.5:7b-instruct-q4）
    for cand in candidates:
        for av in available:
            if av == cand or av.startswith(cand.split(":")[0]):
                return av
    return None

def _ollama_generate(model: str, system: str, prompt: str,
                     temperature: float = 0.6, num_predict: int = -1,
                     timeout=None) -> str:
    """呼叫 Ollama /api/generate（非 streaming）。timeout=None 代表無限等待。"""
    r = req.post("http://localhost:11434/api/generate", json={
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict}
    }, timeout=timeout)
    r.raise_for_status()
    return r.json().get("response", "").strip()

def _ollama_generate_stream(model: str, system: str, prompt: str,
                             temperature: float = 0.6, num_predict: int = -1):
    """呼叫 Ollama /api/generate（streaming），逐塊 yield 文字片段，無 timeout 限制。"""
    with req.post("http://localhost:11434/api/generate", json={
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": num_predict}
    }, stream=True, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
                token = chunk.get("response", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                continue

def _ollama_chat(model: str, messages: list[dict],
                 temperature: float = 0.3, num_predict: int = -1,
                 timeout=None) -> str:
    """呼叫 Ollama /api/chat（非 streaming）。timeout=None 代表無限等待。"""
    r = req.post("http://localhost:11434/api/chat", json={
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict}
    }, timeout=timeout)
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "").strip()


# ── 自學 API ──────────────────────────────────────────────────────────────────

def _prepare_learn_content(source: str, form, files) -> tuple[str, str | None]:
    """從不同來源取得要學習的文字。回傳 (content_text, error_msg)。"""
    if source == "text":
        return form.get("text", "").strip(), None

    elif source == "file":
        if "file" not in files:
            return "", "沒有檔案"
        f = files["file"]
        fname = f.filename.lower()
        if fname.endswith(".pdf"):
            tmp = pathlib.Path("knowledge_data/tmp_learn.pdf")
            f.save(str(tmp))
            try:
                import pypdf
                reader = pypdf.PdfReader(str(tmp))
                pages = [p.extract_text() or "" for p in reader.pages]
                return "\n\n".join(pages)[:8000], None
            finally:
                tmp.unlink(missing_ok=True)
        elif fname.endswith(".txt"):
            return f.read().decode("utf-8", errors="ignore")[:8000], None
        elif any(fname.endswith(ext) for ext in [".png",".jpg",".jpeg",".webp"]):
            img_data = base64.b64encode(f.read()).decode()
            vision_model = _pick_model(_VISION_MODELS) or "llava:7b"
            r = req.post("http://localhost:11434/api/generate", json={
                "model": vision_model,
                "prompt": "請完整描述這張圖片的所有文字內容和視覺資訊，用繁體中文回答。",
                "images": [img_data],
                "stream": False
            }, timeout=None)
            return r.json().get("response", "").strip(), None
        return "", "不支援的檔案格式"

    elif source == "kb":
        kb_id = int(form.get("kb_id", 0))
        entry = get_store().get(kb_id)
        if not entry:
            return "", "找不到知識庫資料"
        return f"{entry['title']}\n\n{entry['content'] or entry['ai_summary']}", None

    return "", "未知來源"


@app.route("/api/learn", methods=["POST"])
def api_learn():
    """SSE streaming 自學端點：即時把 Ollama 的 token 推給前端。"""
    from flask import Response, stream_with_context

    source = request.form.get("source", "text")
    focus  = request.form.get("focus", "").strip()

    # ── 先準備內容（同步）────────────────────────────────────────────────────
    content_text, err = _prepare_learn_content(source, request.form, request.files)
    if err:
        return jsonify({"error": err}), 400
    if not content_text:
        return jsonify({"error": "無法取得資料內容"}), 400

    content_text = content_text[:6000]
    focus_prompt = f"\n\n請特別著重在：{focus}" if focus else ""

    system_prompt = """你是「立」，顏立桓的AI助理，現在進入「自學模式」。
你的任務是閱讀資料後，輸出一份結構化的學習報告，格式如下：

【📖 資料摘要】
簡要說明這份資料在講什麼（2-3句）

【💡 核心概念】
列出3-5個最重要的概念或知識點

【🔍 立AI的看法】
以第一人稱說明你對這份資料的理解、疑問、或延伸思考

【📝 學到了什麼】
具體列出從這份資料學到的新知識或技能

【⚡ 可應用的場景】
說明這些知識在哪些情況下可以派上用場

請用繁體中文，語氣活潑自然。"""

    prompt = f"以下是要學習的資料：\n\n{content_text}{focus_prompt}\n\n請輸出學習報告："

    model = _pick_model(_LEARN_MODELS)
    if not model:
        return jsonify({"error": "找不到可用的 Ollama 模型，請先執行 ollama pull <模型名稱>"}), 503

    logger.info(f"[Learn] 使用模型 {model}，開始 streaming")

    def sse_generator():
        """SSE 事件產生器：持續把 token 推給前端，直到 done。"""
        # 先送模型資訊
        yield f"data: {json.dumps({'type':'model','model':model})}\n\n"
        full_report = []
        try:
            for token in _ollama_generate_stream(
                model=model,
                system=system_prompt,
                prompt=prompt,
                temperature=0.6,
                num_predict=-1,   # 不限制，直到模型自然結束
            ):
                full_report.append(token)
                yield f"data: {json.dumps({'type':'token','text':token})}\n\n"

            report_text = "".join(full_report)

            # ── 存紀錄 ──────────────────────────────────────────────────────
            session_id = _save_learn_session(
                source_type = source,
                source_text = content_text,
                report      = report_text,
                model       = model,
                focus       = focus,
            )

            # 完成事件
            yield f"data: {json.dumps({'type':'done','report':report_text,'model':model,'session_id':session_id})}\n\n"
            logger.info(f"[Learn] 完成，session={session_id}，共 {len(report_text)} 字")

        except Exception as e:
            logger.error(f"[Learn] streaming 錯誤：{traceback.format_exc()}")
            yield f"data: {json.dumps({'type':'error','error':str(e)})}\n\n"

    return Response(
        stream_with_context(sse_generator()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 避免 nginx 快取
        }
    )


# ── 立AI 工具定義 ─────────────────────────────────────────────────────────────

def _search_learn_sessions(query: str, limit: int = 3) -> list[dict]:
    """
    兩階段搜尋自學紀錄：
      1. 標籤比對（快）：query 關鍵詞與 JSON 的 tags 欄位交集，有命中直接回傳
      2. 全文掃描（慢）：若標籤比對結果不足，才逐字讀 input+report 做全文搜尋
    """
    keywords = [k.lower() for k in query.split() if len(k) >= 2]
    if not keywords:
        return []

    all_files = sorted(_LEARN_DIR.glob("*.json"), reverse=True)
    tag_hits   = []   # 標籤命中
    full_hits  = []   # 全文命中（備用）
    no_tag_files = [] # 沒有 tags 欄位的舊紀錄，留到全文掃

    # ── 第一階段：標籤比對 ───────────────────────────────────────────────────
    for p in all_files:
        try:
            raw = p.read_text(encoding="utf-8")
            d   = json.loads(raw)
        except Exception:
            continue

        tags = d.get("tags")
        if not tags:
            # 舊紀錄沒有 tags，記錄下來留到第二階段
            no_tag_files.append((p, d))
            continue

        tags_lower = [t.lower() for t in tags]
        # 只要有任一關鍵詞命中 tags，就算標籤命中
        if any(kw in tag for kw in keywords for tag in tags_lower):
            tag_hits.append(d)
            if len(tag_hits) >= limit:
                break   # 夠了就不繼續掃

    if len(tag_hits) >= limit:
        logger.debug(f"[Search] 標籤命中 {len(tag_hits)} 筆，直接回傳")
        return tag_hits[:limit]

    # ── 第二階段：全文掃描（補足不夠的部分）────────────────────────────────
    already = {d["session_id"] for d in tag_hits}
    remaining = limit - len(tag_hits)

    # 先把有 tags 但沒命中的檔案也一起掃（標籤比對已跑過，從頭再掃全文）
    for p in all_files:
        if len(full_hits) >= remaining:
            break
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("session_id") in already:
            continue
        haystack = (d.get("input", "") + " " + d.get("report", "")).lower()
        if all(kw in haystack for kw in keywords):
            full_hits.append(d)
            already.add(d["session_id"])

    result = tag_hits + full_hits
    logger.debug(f"[Search] 標籤命中 {len(tag_hits)} 筆 + 全文命中 {len(full_hits)} 筆")
    return result[:limit]

def _tool_search(query: str, limit: int = 5) -> str:
    """搜尋知識庫"""
    results = get_store().search(query=query, limit=limit)
    if not results:
        return "找不到相關筆記。"
    lines = [f"[ID:{r['id']}] {r['title']} — {r['ai_summary'] or r['content'][:60]}" for r in results]
    return "\n".join(lines)

def _tool_add(title: str, content: str, tags: list = None, importance: int = 5) -> str:
    """新增文字筆記"""
    entry_id = get_store().add_text(title, content, importance, tags or [])
    _broadcast('entry_added', {"id": entry_id, "title": title})
    return f"✅ 已新增筆記「{title}」（ID:{entry_id}）"

def _tool_update(entry_id: int, title: str = None, content: str = None,
                 tags: list = None, category: str = None, importance: int = None) -> str:
    """修改筆記"""
    entry = get_store().get(entry_id)
    if not entry:
        return f"❌ 找不到 ID:{entry_id} 的筆記"
    kwargs = {}
    if title is not None:      kwargs["title"] = title
    if content is not None:    kwargs["content"] = content
    if tags is not None:       kwargs["tags"] = tags
    if category is not None:   kwargs["category"] = category
    if importance is not None: kwargs["importance"] = importance
    get_store().update(entry_id, **kwargs)
    _broadcast('entry_updated', {"id": entry_id, "title": title or entry["title"]})
    return f"✅ 已更新筆記「{entry['title']}」（ID:{entry_id}）"

def _tool_delete(entry_id: int) -> str:
    """刪除筆記"""
    entry = get_store().get(entry_id)
    if not entry:
        return f"❌ 找不到 ID:{entry_id} 的筆記"
    title = entry["title"]
    get_store().delete(entry_id)
    _broadcast('entry_deleted', {"id": entry_id})
    return f"✅ 已刪除筆記「{title}」"

def _tool_list(category: str = "", limit: int = 50, date: str = "") -> str:
    """列出筆記，可依日期過濾（date 格式：YYYY-MM-DD 或 YYYYMMDD）"""
    results = get_store().search(category=category, sort="time", limit=limit)
    if not results:
        return "知識庫目前沒有任何筆記。"
    # 日期過濾
    if date:
        date_clean = date.replace("-", "")[:8]  # 統一成 YYYYMMDD
        results = [r for r in results if r.get("created_at","").replace("-","")[:8] == date_clean]
        if not results:
            return f"找不到 {date} 當天上傳的資料。"
    lines = [f"[ID:{r['id']}] {r['title']} ｜ {r['category']} ｜ 上傳:{r['created_at'][:10]}" for r in results]
    return f"共 {len(lines)} 筆：\n" + "\n".join(lines)

# 工具清單供 Ollama 參考
TOOLS_DESC = """你有以下工具可以呼叫，需要時在回答中插入 JSON 指令：

1. 搜尋：{"tool":"search","query":"關鍵字"}
2. 新增：{"tool":"add","title":"標題","content":"內容","tags":["標籤"],"importance":5}
3. 修改：{"tool":"update","id":ID,"title":"新標題","content":"新內容","tags":["新標籤"],"category":"分類","importance":5}
4. 刪除：{"tool":"delete","id":ID}
5. 列出：{"tool":"list","category":"分類","limit":10,"date":"YYYY-MM-DD"}
   → 查詢特定日期上傳的資料時，一定要帶 date 參數
   → 例如查 2026-04-20 上傳的：{"tool":"list","date":"2026-04-20"}

規則：
- 只在使用者要求操作時才呼叫工具
- 工具指令必須是獨立一行的純 JSON
- 執行後用繁體中文告知結果
- 不確定要刪除或修改哪一筆時，先搜尋確認再操作
- 所有回答用繁體中文"""

# ── 器官工具函式 ───────────────────────────────────────────────────────────────
_ASSEMBLED_DIR = pathlib.Path(__file__).parent / "workshop_data" / "assembled"

def _get_organs() -> list[dict]:
    """取得所有已組裝的器官清單。"""
    if not _ASSEMBLED_DIR.exists():
        return []
    organs = []
    for f in sorted(_ASSEMBLED_DIR.glob("*.py"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        organs.append({
            "name":     f.stem.replace("_", " "),
            "filename": f.name,
            "path":     str(f),
            "size":     f.stat().st_size,
            "mtime":    datetime.datetime.fromtimestamp(
                            f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return organs

def _tool_organ_list() -> str:
    """列出所有器官及技能描述。"""
    reg = get_registry() if _SKILL_SYSTEM else None
    if reg:
        summary = reg.summary()
        return f"📦 器官技能庫：\n{summary}" if summary else "器官庫是空的。"
    # fallback
    organs = _get_organs()
    if not organs:
        return "器官庫是空的，請先在工坊完成並組裝專案。"
    lines = ["📦 器官庫（工坊產出）："]
    for o in organs:
        lines.append(f"  🔩 {o['name']}  ·  {o['filename']}  ·  {o['size']//1024 or 1}KB  ·  {o['mtime']}")
    return "\n".join(lines)

def _tool_organ_run(filename: str, args: str = "") -> str:
    """執行指定器官，支援傳入參數。"""
    if _SKILL_SYSTEM:
        reg    = get_registry()
        # 先用關鍵字選器官
        skill  = select_organ(filename.replace(".py",""), reg) if reg else None
        if skill:
            arg_list = args.split() if args else []
            result   = execute_organ(skill, arg_list)
            status   = "✅ 執行成功" if result["success"] else "❌ 執行失敗"
            out      = result.get("output") or result.get("error") or "（無輸出）"
            return f"{status}：{skill['name']}\n{out[:600]}"

    # fallback：直接 subprocess
    import subprocess, sys as _sys
    fname = pathlib.Path(filename).name
    path  = _ASSEMBLED_DIR / fname
    if not path.exists():
        matches = [f for f in _ASSEMBLED_DIR.glob("*.py")
                   if filename.replace(".py","").lower() in f.stem.lower()]
        if matches:
            path = matches[0]
        else:
            return f"找不到器官：{filename}\n請用 organ_list 確認正確的檔名。"
    try:
        cmd    = [_sys.executable, str(path)] + (args.split() if args else [])
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=30, encoding="utf-8", errors="replace")
        out    = (result.stdout + result.stderr).strip()
        status = "✅ 執行成功" if result.returncode == 0 else f"❌ 執行失敗"
        return f"{status}：{path.name}\n{out[:600] if out else '（無輸出）'}"
    except subprocess.TimeoutExpired:
        return f"⏱ 執行超時（30秒）：{path.name}"
    except Exception as e:
        return f"執行錯誤：{e}"

def _tool_organ_info(filename: str) -> str:
    """查看器官程式碼內容。"""
    filename = pathlib.Path(filename).name
    path = _ASSEMBLED_DIR / filename
    if not path.exists():
        matches = [f for f in _ASSEMBLED_DIR.glob("*.py")
                   if filename.replace(".py","").lower() in f.stem.lower()]
        if matches:
            path = matches[0]
        else:
            return f"找不到器官：{filename}"
    code = path.read_text(encoding="utf-8", errors="replace")
    preview = code[:800] + ("\n...（截斷，共 {} 字元）".format(len(code)) if len(code) > 800 else "")
    return f"📄 {path.name}：\n```python\n{preview}\n```"


WORKSHOP_URL = "http://localhost:7862"

def _tool_workshop_create(name: str, requirement: str) -> str:
    """讓立AI 觸發工坊自動製作器官。"""
    import socket as _sk
    with _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', 7862)) != 0:
            return "⚠ 工坊未啟動（localhost:7862），請先開啟工坊"
    callback_url = "http://localhost:7861/api/workshop_callback"
    try:
        r = req.post(f"{WORKSHOP_URL}/api/auto_create", json={
            "name":         name,
            "requirement":  requirement,
            "callback_url": callback_url,
        }, timeout=10)
        d = r.json()
        if d.get("ok"):
            return (f"✅ 已送工坊自動製作：「{name}」\n"
                    f"專案ID：{d.get('project_id','')}\n"
                    f"完成後會自動通知你，請稍候...")
        return f"❌ 工坊拒絕：{d.get('error','未知錯誤')}"
    except Exception as e:
        return f"❌ 連線工坊失敗：{e}"


def _execute_tools(text: str) -> tuple[str, list[str]]:
    """從 Ollama 回應中找出並執行工具指令，回傳（清理後的文字, 執行結果列表）"""
    import re
    results = []

    # 先把 markdown code block 裡的 JSON 提取出來（gemma3 常這樣包）
    text = re.sub(r'```(?:json)?\s*(\{[^`]*\})\s*```', r'\1', text)

    def replace_tool(m):
        raw = m.group(0)
        try:
            # gemma3 有時用單引號，統一轉雙引號
            fixed = raw.replace("'", '"')
            cmd = json.loads(fixed)
            tool = cmd.get("tool", "")
            if tool == "search":
                r = _tool_search(cmd.get("query",""), cmd.get("limit",5))
            elif tool == "add":
                r = _tool_add(cmd["title"], cmd.get("content",""),
                              cmd.get("tags"), cmd.get("importance",5))
            elif tool == "update":
                r = _tool_update(int(cmd["id"]), cmd.get("title"),
                                 cmd.get("content"), cmd.get("tags"),
                                 cmd.get("category"), cmd.get("importance"))
            elif tool == "delete":
                r = _tool_delete(int(cmd["id"]))
            elif tool == "list":
                r = _tool_list(cmd.get("category",""), cmd.get("limit",50), cmd.get("date",""))
            elif tool == "organ_list":
                r = _tool_organ_list()
            elif tool == "organ_run":
                r = _tool_organ_run(cmd.get("filename",""), cmd.get("args",""))
            elif tool == "organ_info":
                r = _tool_organ_info(cmd.get("filename",""))
            elif tool == "workshop_create":
                r = _tool_workshop_create(cmd.get("name","新器官"), cmd.get("requirement",""))
            else:
                return raw
            results.append(r)
            return f"\n{r}\n"
        except Exception as e:
            return f"\n[工具執行錯誤：{e}]\n"

    cleaned = re.sub(r'\{[^{}]*"tool"[^{}]*\}', replace_tool, text)
    return cleaned.strip(), results


# ── 立AI 聊天 API ─────────────────────────────────────────────────────────────

@app.route("/api/workshop_callback", methods=["POST"])
def api_workshop_callback():
    """接收工坊完成通知，讓立AI 知道器官做好了。"""
    data    = request.get_json(silent=True) or {}
    status  = data.get("status", "")
    message = data.get("message", "")
    pid     = data.get("project_id", "")

    logger.info(f"[Workshop] 收到回調：{status} — {message}")

    # 重新整理技能描述
    if status == "done":
        try:
            from organ_skill_system import refresh_registry
            refresh_registry()
            logger.info("[Workshop] 技能描述已更新")
        except Exception as e:
            logger.warning(f"[Workshop] 更新技能描述失敗：{e}")

    # 廣播給前端
    socketio.emit("workshop_update", {
        "status":  status,
        "message": message,
        "pid":     pid,
    })

    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data    = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    mode    = str(data.get("mode", "library"))  # 'library' 或 'codedb'
    if not message:
        return jsonify({"reply": "請輸入問題", "source": "立 AI"})

    store = get_store()

    # ── 程式碼規範庫模式 ──────────────────────────────────────────────────────
    if mode == "codedb":
        # 從 code_rules.db 搜尋相關規則
        with _code_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM code_rules ORDER BY priority ASC",
            ).fetchall()

        code_context = ""
        if rows:
            code_context = "\n[程式碼規範庫內容]\n"
            for r in rows:
                pri_map = {1:"必須遵守", 2:"建議", 3:"參考"}
                cat_map = {"coding":"程式碼規則","arch":"架構方向","module":"模組規則",
                           "bug":"已知Bug","ai_rules":"AI行為準則"}
                code_context += f"- [{pri_map.get(r['priority'],'')}][{cat_map.get(r['category'],r['category'])}] {r['title']}：{r['content'][:150]}\n"

        try:
            import datetime as dt
            today = dt.datetime.now().strftime("%Y-%m-%d")

            system_prompt = f"""你是「立」，顏立桓的程式碼規範助理，今天是 {today}。
你的職責是根據程式碼規範庫回答問題，幫助確認程式碼是否符合規範。

{code_context}

規則：
- 只根據規範庫內容回答，不要自創規則
- 若問題規範庫沒有涵蓋，直接說「規範庫尚未定義此規則」
- 所有回答用繁體中文，簡潔清楚"""

            prompt = f"使用者問：{message}\n\n請根據規範庫回答："

            chat_model = _pick_model(_CHAT_MODELS) or "gemma3:4b"
            raw_reply = _ollama_chat(
                model=chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt}
                ],
                temperature=0.2, num_predict=500, timeout=120,
            )
            if not raw_reply:
                return jsonify({"reply": "你好！有什麼程式碼規範問題嗎？", "source": "📐 規範庫"})

            return jsonify({"reply": raw_reply, "source": f"📐 規範庫（{chat_model}）"})

        except Exception as e:
            # Ollama 離線，直接列出相關規則
            if rows:
                reply = "根據規範庫找到以下規則：\n"
                for r in list(rows)[:5]:
                    reply += f"\n• {r['title']}：{r['content'][:100]}"
                return jsonify({"reply": reply, "source": "📐 規範庫（離線）"})
            return jsonify({"reply": f"發生錯誤：{e}", "source": "📐 規範庫"})

    # ── 圖書館模式（原本邏輯）────────────────────────────────────────────────
    # 搜尋知識庫
    kb_results = store.search(query=message, sort="importance", limit=5)
    kb_context = ""
    if kb_results:
        kb_context = "\n[知識庫相關內容]\n"
        for r in kb_results:
            kb_context += f"- [ID:{r['id']}] {r['title']}：{r['content'][:120] or r['ai_summary'][:120]}\n"

    # 搜尋自學紀錄
    learn_results = _search_learn_sessions(message, limit=3)
    learn_context = ""
    if learn_results:
        learn_context = "\n[自學紀錄相關內容]\n"
        for s in learn_results:
            ts = s.get("timestamp", "")[:16].replace("T", " ")
            input_preview  = s.get("input",  "")[:150].replace("\n", " ")
            report_preview = s.get("report", "")[:200].replace("\n", " ")
            learn_context += (
                f"- [{ts}｜{s.get('model','')}]\n"
                f"  原始資料：{input_preview}\n"
                f"  學習報告：{report_preview}\n"
            )

    try:

        import datetime as dt
        today = dt.datetime.now().strftime("%Y-%m-%d")

        # 列出器官庫給立AI 知道
        # 優先用技能描述系統
        organ_context = ""
        if _SKILL_SYSTEM:
            reg = get_registry()
            if reg and reg.all():
                organ_context = "\n[工坊器官技能庫]\n"
                for s in reg.all()[:8]:
                    needs = "（需要參數）" if s.get("needs_args") else ""
                    organ_context += f"  🔩 {s['name']}{needs}：{s['description']}\n"
        else:
            organs = _get_organs()
            if organs:
                organ_context = "\n[工坊器官庫]\n"
                for o in organs[:8]:
                    organ_context += f"  🔩 {o['name']} → {o['filename']}\n"

        system_prompt = f"""你是「立」，顏立桓的本地AI助理，今天是 {today}。
你可以管理知識庫和工坊器官，方法是在回答中插入以下 JSON 指令（每個獨立一行）：

知識庫：
搜尋：{{"tool":"search","query":"關鍵字"}}
新增：{{"tool":"add","title":"標題","content":"內容","tags":["標籤"],"importance":5}}
修改：{{"tool":"update","id":ID,"title":"新標題","content":"新內容","tags":["標籤"],"category":"分類","importance":5}}
刪除：{{"tool":"delete","id":ID}}
列出：{{"tool":"list","category":"","limit":20,"date":"YYYY-MM-DD"}}

工坊器官（工坊產出的程式）：
列出器官：{{"tool":"organ_list"}}
執行器官：{{"tool":"organ_run","filename":"器官檔名.py","args":"參數1 參數2"}}
查看器官：{{"tool":"organ_info","filename":"器官檔名.py"}}
製作新器官：{{"tool":"workshop_create","name":"器官名稱","requirement":"需求描述"}}

回答時的參考優先順序：
1. 自學紀錄（你曾經深度學習過的內容，最優先）
2. 知識庫條目（立桓存入的資料）
3. 工坊器官庫（可執行的程式模組）
4. 你自身的知識

規則：
- 使用者純問候（你好、嗨、哈囉等）→ 直接回應，不要呼叫任何工具
- 使用者問「今天上傳了什麼」→ 插入 {{"tool":"list","date":"{today}"}}
- 使用者說「04-20」「4/20」等不完整日期 → 補全成 2026-XX-XX 格式再帶入 date
- 使用者問「搜尋/找XXX」→ 插入 {{"tool":"search","query":"XXX"}}
- 使用者問「有哪些/有幾筆/上傳多少」→ 插入 {{"tool":"list","limit":20}}
- 使用者問某日期上傳了什麼 → 插入 {{"tool":"list","date":"YYYY-MM-DD"}}
- 使用者問「有什麼器官/零件/工坊產出」→ 插入 {{"tool":"organ_list"}}
- 使用者說「執行/啟動/跑XXX」→ 插入 {{"tool":"organ_run","filename":"XXX.py"}}
- 使用者說「看看/預覽XXX的程式」→ 插入 {{"tool":"organ_info","filename":"XXX.py"}}
- 不確定要操作哪一筆時，先 search 或 organ_list 確認再操作
- 使用者要求某個功能但器官庫沒有對應技能 → 用 workshop_create 自動製作新器官
- 直接行動，不要反問使用者
- 所有回答用繁體中文"""

        prompt = f"""使用者說：{message}
{kb_context}{learn_context}{organ_context}
請直接回應並在需要時插入工具 JSON："""

        chat_model = _pick_model(_CHAT_MODELS) or "gemma3:4b"
        raw_reply = _ollama_chat(
            model=chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.3, num_predict=600, timeout=120,
        )

        if not raw_reply:
            return jsonify({"reply": "你好！有什麼我可以幫你的嗎？", "source": "立 AI"})

        final_reply, tool_results = _execute_tools(raw_reply)

        refs = []
        if kb_results:     refs.append("知識庫")
        if learn_results:  refs.append("自學紀錄")
        ref_str = "＋".join(refs) if refs else "自身知識"
        source = f"立 AI（{chat_model}｜參考：{ref_str}）"
        if tool_results:
            source = f"立 AI 已執行（{chat_model}）"

        # saveable=True 代表這是一則推理回答，可以讓使用者決定是否存入知識庫
        # 工具執行結果（新增/刪除等）不需要再存
        saveable = not bool(tool_results)

        return jsonify({
            "reply":    final_reply,
            "source":   source,
            "actions":  tool_results,
            "question": message,      # 原始問題，存入知識庫時當標題用
            "saveable": saveable,
        })

    except Exception as e:
        logger.error(f"[Chat] api_chat 錯誤：{traceback.format_exc()}")
        reply_parts = []
        if kb_results:
            part = "根據知識庫找到以下相關內容：\n"
            for r in kb_results:
                part += f"\n• [{r['id']}] {r['title']}：{r['content'][:100] or r['ai_summary']}"
            reply_parts.append(part)
        if learn_results:
            part = "\n根據自學紀錄找到以下相關內容：\n"
            for s in learn_results:
                ts = s.get("timestamp", "")[:16].replace("T", " ")
                part += f"\n• [{ts}] {s.get('report','')[:120]}"
            reply_parts.append(part)
        if reply_parts:
            return jsonify({"reply": "\n".join(reply_parts), "source": "立 AI（離線模式）"})
        return jsonify({"reply": f"發生錯誤：{e}", "source": "立 AI"})


# ── 程式碼規範庫 API ──────────────────────────────────────────────────────────

def _now_str():
    return datetime.datetime.now().isoformat(timespec="seconds")

@app.route("/api/code_rules")
def api_code_rules():
    cat = request.args.get("category", "")
    with _code_conn() as conn:
        if cat and cat != "all":
            rows = conn.execute(
                "SELECT * FROM code_rules WHERE category=? ORDER BY priority ASC, updated_at DESC",
                (cat,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM code_rules ORDER BY priority ASC, updated_at DESC"
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['tags'] = json.loads(d.get('tags') or '[]')
        result.append(d)
    return jsonify(result)

@app.route("/api/code_rules/<int:rule_id>")
def api_code_rule(rule_id):
    with _code_conn() as conn:
        row = conn.execute("SELECT * FROM code_rules WHERE id=?", (rule_id,)).fetchone()
    if not row: return jsonify({"error": "not found"}), 404
    d = dict(row); d['tags'] = json.loads(d.get('tags') or '[]')
    return jsonify(d)

@app.route("/api/code_rules", methods=["POST"])
def api_add_code_rule():
    data = request.get_json(silent=True) or {}
    title    = str(data.get("title","")).strip()
    content  = str(data.get("content","")).strip()
    category = str(data.get("category","coding"))
    priority = int(data.get("priority", 2))
    if not title or not content:
        return jsonify({"error": "標題和內容不能為空"}), 400
    now = _now_str()
    with _code_conn() as conn:
        cur = conn.execute(
            "INSERT INTO code_rules (category,title,content,priority,tags,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (category, title, content, priority, "[]", now, now)
        )
        return jsonify({"id": cur.lastrowid})

@app.route("/api/code_rules/<int:rule_id>", methods=["PUT"])
def api_update_code_rule(rule_id):
    data = request.get_json(silent=True) or {}
    title    = str(data.get("title","")).strip()
    content  = str(data.get("content","")).strip()
    category = str(data.get("category","coding"))
    priority = int(data.get("priority", 2))
    now = _now_str()
    with _code_conn() as conn:
        conn.execute(
            "UPDATE code_rules SET title=?,content=?,category=?,priority=?,updated_at=? WHERE id=?",
            (title, content, category, priority, now, rule_id)
        )
    return jsonify({"ok": True})

@app.route("/api/code_rules/<int:rule_id>", methods=["DELETE"])
def api_delete_code_rule(rule_id):
    with _code_conn() as conn:
        conn.execute("DELETE FROM code_rules WHERE id=?", (rule_id,))
    return jsonify({"ok": True})

@app.route("/api/code_rules/export")
def api_export_code_rules():
    """匯出所有規則為純文字（給 gpt-oss 讀取用）"""
    with _code_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM code_rules ORDER BY priority ASC, category ASC"
        ).fetchall()
    lines = ["# 程式碼規範庫\n"]
    cat_map = {"coding":"程式碼規則","arch":"架構方向","module":"模組規則","bug":"已知Bug與解法","ai_rules":"AI行為準則"}
    pri_map = {1:"[必須遵守]",2:"[建議]",3:"[參考]"}
    cur_cat = None
    for r in rows:
        if r["category"] != cur_cat:
            cur_cat = r["category"]
            lines.append(f"\n## {cat_map.get(cur_cat, cur_cat)}\n")
        lines.append(f"### {pri_map.get(r['priority'],'')} {r['title']}")
        lines.append(r["content"])
        lines.append("")
    from flask import Response
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=code_rules.md"})

# ── WebSocket 事件 ────────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    pass  # 連線時不需要特別處理

# ── 自學紀錄 API ──────────────────────────────────────────────────────────────

@app.route("/api/learn_sessions")
def api_learn_sessions():
    """列出所有自學紀錄（最新在前）。"""
    sessions = []
    for p in sorted(_LEARN_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "session_id":  d.get("session_id"),
                "timestamp":   d.get("timestamp"),
                "model":       d.get("model"),
                "source_type": d.get("source_type"),
                "focus":       d.get("focus", ""),
                "input_preview": d.get("input", "")[:120],
                "report_preview": d.get("report", "")[:120],
            })
        except Exception:
            continue
    return jsonify(sessions)

@app.route("/api/learn_sessions/<session_id>")
def api_learn_session(session_id):
    """取得單筆自學紀錄完整內容。"""
    # 防止路徑穿越
    session_id = pathlib.Path(session_id).name
    path = _LEARN_DIR / f"{session_id}.json"
    if not path.exists():
        return jsonify({"error": "找不到紀錄"}), 404
    try:
        return jsonify(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/learn_sessions/<session_id>", methods=["DELETE"])
def api_delete_learn_session(session_id):
    """刪除單筆自學紀錄。"""
    session_id = pathlib.Path(session_id).name
    path = _LEARN_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
    return jsonify({"ok": True})

@app.route("/api/models")
def api_models():
    """列出可用模型，供前端診斷用。"""
    models = _get_available_models()
    learn_model  = _pick_model(_LEARN_MODELS)
    chat_model   = _pick_model(_CHAT_MODELS)
    vision_model = _pick_model(_VISION_MODELS)
    return jsonify({
        "available": models,
        "selected": {
            "learn":  learn_model,
            "chat":   chat_model,
            "vision": vision_model,
        }
    })

# ── 啟動 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("📚 知識庫啟動中（即時同步模式）...")
    print("   電腦：http://localhost:7861")
    print("   手機：http://100.91.148.59:7861")

    # 補舊紀錄的 tags（背景執行，不阻擋啟動）
    def _backfill_tags():
        patched = 0
        for p in _LEARN_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if d.get("tags"):
                    continue   # 已有標籤，跳過
                combined = f"{d.get('focus','')} {d.get('input','')} {d.get('report','')}"
                d["tags"] = _extract_tags_from_text(combined, max_tags=15)
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                patched += 1
            except Exception:
                continue
        if patched:
            logger.info(f"[Backfill] 已為 {patched} 筆舊紀錄補上標籤")

    import threading
    threading.Thread(target=_backfill_tags, daemon=True).start()

    # 啟動時偵測 Ollama 模型
    try:
        models = _get_available_models()
        if models:
            learn  = _pick_model(_LEARN_MODELS)
            chat   = _pick_model(_CHAT_MODELS)
            print(f"   🧠 自學模型：{learn or '❌ 找不到'}")
            print(f"   💬 對話模型：{chat  or '❌ 找不到'}")
        else:
            print("   ⚠️  Ollama 無回應或沒有安裝任何模型")
            print("      請先執行：ollama pull gemma3:4b")
    except Exception:
        print("   ⚠️  無法連線 Ollama（localhost:11434）")
    print("   Ctrl+C 停止")
    socketio.run(app, host="0.0.0.0", port=7861, debug=False, allow_unsafe_werkzeug=True)
