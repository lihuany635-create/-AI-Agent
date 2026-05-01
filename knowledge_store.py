# knowledge_store.py — 知識庫核心模組
# 功能：SQLite 儲存、關鍵字搜尋、標籤過濾、圖片OCR、影片關鍵畫面、AI自動分類
# 依賴：pip install pillow pytesseract opencv-python requests
# 使用方式：from knowledge_store import KnowledgeStore; ks = KnowledgeStore()

import sqlite3
import json
import pathlib
import datetime
import hashlib
import shutil
import base64
import logging
from typing import Optional

logger = logging.getLogger("knowledge_store")

# ── 設定 ─────────────────────────────────────────────────────────────────────

BASE_DIR    = pathlib.Path("knowledge_data")
DB_PATH     = BASE_DIR / "knowledge.db"
FILES_DIR   = BASE_DIR / "files"
THUMBS_DIR  = BASE_DIR / "thumbs"
OLLAMA_URL  = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"

for d in [BASE_DIR, FILES_DIR, THUMBS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ── 資料庫初始化 ──────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                content     TEXT DEFAULT '',
                category    TEXT DEFAULT '未分類',
                importance  INTEGER DEFAULT 5,
                entry_type  TEXT DEFAULT 'text',   -- text / image / video / group
                file_path   TEXT DEFAULT '',
                thumb_path  TEXT DEFAULT '',
                ocr_text    TEXT DEFAULT '',
                ai_summary  TEXT DEFAULT '',
                tags        TEXT DEFAULT '[]',      -- JSON array
                group_id    INTEGER DEFAULT NULL,   -- 所屬群組 ID
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            -- 為舊資料庫補欄位（如果不存在）
            CREATE TABLE IF NOT EXISTS _dummy(x);
            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts
                USING fts5(title, content, ocr_text, ai_summary, tags, content=entries, content_rowid=id);
            CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                INSERT INTO entries_fts(rowid, title, content, ocr_text, ai_summary, tags)
                VALUES (new.id, new.title, new.content, new.ocr_text, new.ai_summary, new.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, title, content, ocr_text, ai_summary, tags)
                VALUES ('delete', old.id, old.title, old.content, old.ocr_text, old.ai_summary, old.tags);
                INSERT INTO entries_fts(rowid, title, content, ocr_text, ai_summary, tags)
                VALUES (new.id, new.title, new.content, new.ocr_text, new.ai_summary, new.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, title, content, ocr_text, ai_summary, tags)
                VALUES ('delete', old.id, old.title, old.content, old.ocr_text, old.ai_summary, old.tags);
            END;
        """)

init_db()

# 為舊資料庫補 group_id 欄位
try:
    with _get_conn() as conn:
        conn.execute("ALTER TABLE entries ADD COLUMN group_id INTEGER DEFAULT NULL")
except Exception:
    pass  # 欄位已存在，忽略

# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")

def _file_hash(path: pathlib.Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]

def _row_to_dict(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


# ── AI 自動分類 ───────────────────────────────────────────────────────────────

CATEGORIES = [
    "技術/程式", "AI/機器學習", "筆記/學習", "工作/專案",
    "影片/媒體", "圖片/視覺", "參考資料", "個人/日記", "未分類"
]

# 視覺模型（llava 或 llava:13b）
VISION_MODEL = "llava"

def _extract_json(text: str) -> dict:
    """從 Ollama 回傳文字中安全擷取 JSON"""
    import re
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}

def _keyword_tags(text: str, max_tags: int = 3) -> list[str]:
    """
    快速關鍵字擷取：從文字中找出最有代表性的詞彙
    作為 Ollama 語義分析的補充
    """
    import re
    # 常見停用詞
    stop = {"的", "了", "是", "在", "和", "與", "或", "有", "要", "會",
            "這", "那", "我", "你", "他", "她", "它", "都", "也", "很",
            "就", "但", "如果", "因為", "所以", "一個", "可以", "使用",
            "方法", "內容", "相關", "進行", "需要", "如何", "什麼"}

    # 抽取中英文詞彙
    words = re.findall(r'[a-zA-Z0-9_\.]{2,}|[\u4e00-\u9fff]{2,4}', text)
    freq = {}
    for w in words:
        w = w.strip()
        if w.lower() not in stop and len(w) >= 2:
            freq[w] = freq.get(w, 0) + 1

    # 按頻率排序，取前 max_tags 個
    sorted_words = sorted(freq, key=lambda x: freq[x], reverse=True)
    return sorted_words[:max_tags]


def _ai_classify(title: str, content: str) -> tuple[str, list[str], str]:
    """
    文字內容分類：關鍵字擷取 + Ollama 語義分析，合併產生 1~3 個標籤
    回傳：(category, tags, summary)
    """
    import requests as req

    # 1. 關鍵字快速擷取
    kw_tags = _keyword_tags(f"{title} {content}", max_tags=3)

    # 2. Ollama 語義分析
    ollama_tags = []
    category = "未分類"
    summary = ""
    try:
        prompt = f"""你是知識庫分類助手。根據以下內容，回傳 JSON。

標題：{title[:80]}
內容：{content[:250]}

可選分類：{', '.join(CATEGORIES)}

規則：
- tags 只能有 1~3 個，選最能代表內容本質的詞
- 標籤用繁體中文或英文專有名詞
- summary 20字以內

只回傳 JSON：
{{"category": "分類名稱", "tags": ["標籤1", "標籤2"], "summary": "摘要"}}"""

        r = req.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 150}
        }, timeout=30)

        data = _extract_json(r.json().get("response", ""))
        cat = data.get("category", "未分類")
        category = cat if cat in CATEGORIES else "未分類"
        ollama_tags = [t for t in data.get("tags", []) if isinstance(t, str)][:3]
        summary = data.get("summary", "")

    except Exception as e:
        logger.warning(f"Ollama 文字分類失敗：{e}")

    # 3. 合併：Ollama 標籤優先，關鍵字補足，去重，最多 3 個
    merged = list(dict.fromkeys(ollama_tags + kw_tags))[:3]
    return category, merged, summary


def _ai_classify_image(image_path: pathlib.Path,
                        ocr_text: str = "") -> tuple[str, list[str], str]:
    """
    圖片分類：用 llava 視覺模型分析圖片元素，產生 1~3 個標籤
    回傳：(category, tags, summary)
    """
    import requests as req, base64

    # 準備 base64 圖片
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        logger.warning(f"圖片讀取失敗：{e}")
        # fallback：只用 OCR 文字分類
        return _ai_classify(image_path.stem, ocr_text)

    # OCR 文字作為輔助提示
    ocr_hint = f"\n圖片中的文字（OCR）：{ocr_text[:150]}" if ocr_text else ""

    prompt = f"""請分析這張圖片的內容元素，回傳 JSON。{ocr_hint}

可選分類：{', '.join(CATEGORIES)}

規則：
- tags 只能有 1~3 個，描述圖片中最主要的視覺元素或主題
- 標籤用繁體中文或英文專有名詞（例如：螢幕截圖、程式碼、風景、人物、圖表）
- summary 描述圖片內容，20字以內

只回傳 JSON：
{{"category": "分類名稱", "tags": ["標籤1", "標籤2"], "summary": "圖片描述"}}"""

    try:
        r = req.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 150}
        }, timeout=60)

        data = _extract_json(r.json().get("response", ""))
        cat = data.get("category", "圖片/視覺")
        category = cat if cat in CATEGORIES else "圖片/視覺"
        tags = [t for t in data.get("tags", []) if isinstance(t, str)][:3]
        summary = data.get("summary", "")

        # 若 llava 沒給標籤，用 OCR 關鍵字補
        if not tags and ocr_text:
            tags = _keyword_tags(ocr_text, max_tags=3)

        logger.info(f"llava 圖片分析：{tags} / {summary}")
        return category, tags, summary

    except Exception as e:
        logger.warning(f"llava 視覺分析失敗：{e}，改用 OCR 文字分類")
        # fallback：OCR 文字 + 一般分類
        if ocr_text:
            return _ai_classify(image_path.stem, ocr_text)
        return "圖片/視覺", _keyword_tags(image_path.stem, 2), ""


# ── OCR 圖片文字擷取 ──────────────────────────────────────────────────────────

def _ocr_image(path: pathlib.Path) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang="chi_tra+eng")
        return text.strip()
    except Exception as e:
        logger.warning(f"OCR 失敗：{e}")
        return ""


# ── 影片關鍵畫面擷取 ──────────────────────────────────────────────────────────

def _extract_video_frames(video_path: pathlib.Path, max_frames: int = 5) -> list[pathlib.Path]:
    """擷取影片關鍵畫面，回傳縮圖路徑列表"""
    thumbs = []
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30
        duration = total / fps

        # 均勻取幀
        intervals = [int(total * i / max_frames) for i in range(max_frames)]
        stem = video_path.stem

        for idx, frame_no in enumerate(intervals):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = cap.read()
            if not ret:
                continue
            thumb_path = THUMBS_DIR / f"{stem}_frame{idx}.jpg"
            cv2.imwrite(str(thumb_path), frame)
            thumbs.append(thumb_path)

        cap.release()
        logger.info(f"影片擷取 {len(thumbs)} 張關鍵畫面")
    except Exception as e:
        logger.warning(f"影片擷取失敗：{e}")
    return thumbs


def _make_image_thumb(img_path: pathlib.Path) -> pathlib.Path:
    try:
        from PIL import Image
        img = Image.open(img_path)
        img.thumbnail((1200, 1200))  # 提高縮圖解析度
        thumb_path = THUMBS_DIR / f"{img_path.stem}_thumb.jpg"
        img.convert("RGB").save(thumb_path, "JPEG", quality=90)
        return thumb_path
    except Exception as e:
        logger.warning(f"縮圖失敗：{e}")
        return img_path


# ── 核心 API ──────────────────────────────────────────────────────────────────

class KnowledgeStore:

    # ── 新增文字知識 ──────────────────────────────────────────────────────────

    def add_text(self, title: str, content: str,
                 importance: int = 5, tags: list = None) -> int:
        """新增文字筆記，AI 自動分類"""
        category, ai_tags, summary = _ai_classify(title, content)
        all_tags = list(set((tags or []) + ai_tags))
        now = _now()
        with _get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO entries (title, content, category, importance, entry_type,
                                     ai_summary, tags, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (title, content, category, importance, "text",
                  summary, json.dumps(all_tags, ensure_ascii=False), now, now))
            return cur.lastrowid

    # ── 上傳圖片 ──────────────────────────────────────────────────────────────

    def add_image(self, src_path: str, title: str = "",
                  importance: int = 5, tags: list = None,
                  group_id: int = None) -> int:
        """上傳圖片，OCR 擷取文字，AI 自動分類
        檔名衝突時自動建立分類子資料夾，所有檔案加上傳時間戳記
        """
        p = pathlib.Path(src_path)
        if not p.exists():
            raise FileNotFoundError(f"找不到檔案：{src_path}")

        # 時間戳記（加在檔名前）
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stamped_name = f"{ts}_{p.name}"

        # 先試直接放 FILES_DIR
        dest = FILES_DIR / stamped_name

        # 衝突偵測：同原始檔名（不含時間戳）是否已存在
        existing_same_name = list(FILES_DIR.rglob(f"*_{p.name}"))
        if existing_same_name:
            # 有衝突 → 先取得（或建立）分類子資料夾
            # 先做 AI 分類才知道資料夾名
            tmp_title = title or p.stem
            # 衝突時先用文字分類取得資料夾名，等檔案複製後再做視覺分析
            category, ai_tags, summary = _ai_classify(tmp_title, tmp_title)
            _conflict_classify = True  # 標記需要視覺重新分析
            # 資料夾名稱：用分類，斜線換成底線
            folder_name = category.replace("/", "_")
            cat_dir = FILES_DIR / folder_name
            cat_dir.mkdir(exist_ok=True)

            # 把既有同名檔也移進去（如果還在 FILES_DIR 根目錄）
            for old_file in existing_same_name:
                if old_file.parent == FILES_DIR:
                    new_old = cat_dir / old_file.name
                    old_file.rename(new_old)
                    # 更新資料庫裡的 file_path
                    with _get_conn() as conn:
                        conn.execute(
                            "UPDATE entries SET file_path=?, updated_at=? WHERE file_path=?",
                            (str(new_old), _now(), str(old_file))
                        )
                    logger.info(f"衝突：已移動 {old_file.name} → {folder_name}/")

            dest = cat_dir / stamped_name
        else:
            category, ai_tags, summary = "未分類", [], ""
            _conflict_classify = False

        shutil.copy2(p, dest)
        logger.info(f"圖片儲存：{dest}")

        # 縮圖
        thumb = _make_image_thumb(dest)

        # OCR
        ocr_text = _ocr_image(dest)

        # 視覺模型分析圖片元素（含 OCR 輔助），產生最終標籤
        category, ai_tags, summary = _ai_classify_image(dest, ocr_text)

        # 標題（加上傳時間）
        if not title:
            title = p.stem
        title_with_ts = f"{title}（{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:]}）"

        all_tags = list(dict.fromkeys((tags or []) + ai_tags))[:3]
        now = _now()

        with _get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO entries (title, content, category, importance, entry_type,
                                     file_path, thumb_path, ocr_text, ai_summary,
                                     tags, group_id, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (title_with_ts, "", category, importance, "image",
                  str(dest), str(thumb), ocr_text, summary,
                  json.dumps(all_tags, ensure_ascii=False), group_id, now, now))
            return cur.lastrowid

    # ── 上傳影片 ──────────────────────────────────────────────────────────────

    def add_video(self, src_path: str, title: str = "",
                  importance: int = 5, tags: list = None) -> int:
        """上傳影片，擷取關鍵畫面並 OCR"""
        p = pathlib.Path(src_path)
        if not p.exists():
            raise FileNotFoundError(f"找不到檔案：{src_path}")

        dest = FILES_DIR / f"{_file_hash(p)}{p.suffix}"
        shutil.copy2(p, dest)

        # 擷取關鍵畫面
        frames = _extract_video_frames(dest)

        # 對關鍵畫面做 OCR
        ocr_texts = []
        for frame in frames:
            t = _ocr_image(frame)
            if t:
                ocr_texts.append(t)
        ocr_text = "\n".join(ocr_texts)

        # 第一張畫面當縮圖
        thumb_path = str(frames[0]) if frames else ""

        if not title:
            title = p.stem

        category, ai_tags, summary = _ai_classify(title, ocr_text or title)
        all_tags = list(set((tags or []) + ai_tags))
        now = _now()

        with _get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO entries (title, content, category, importance, entry_type,
                                     file_path, thumb_path, ocr_text, ai_summary,
                                     tags, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (title, "", category, importance, "video",
                  str(dest), thumb_path, ocr_text, summary,
                  json.dumps(all_tags, ensure_ascii=False), now, now))
            return cur.lastrowid

    # ── 搜尋 ──────────────────────────────────────────────────────────────────

    def search(self, query: str = "", category: str = "", tags: list = None,
               sort: str = "importance", limit: int = 50) -> list[dict]:
        """
        搜尋知識庫
        sort: importance / time / relevance
        """
        conditions = []
        params = []

        with _get_conn() as conn:
            if query:
                # FTS 安全轉義：把整個查詢用雙引號包起來，避免 -/+/* 等運算子炸掉
                # 同時把查詢中的雙引號跳脫
                fts_query = '"' + query.replace('"', '""') + '"'
                try:
                    ids = [row[0] for row in conn.execute(
                        "SELECT rowid FROM entries_fts WHERE entries_fts MATCH ? LIMIT 200",
                        (fts_query,)
                    )]
                except Exception:
                    # FTS 仍然失敗時，改用 LIKE 模糊搜尋當備援
                    like = f"%{query}%"
                    ids = [row[0] for row in conn.execute(
                        "SELECT id FROM entries WHERE title LIKE ? OR content LIKE ? OR ocr_text LIKE ? LIMIT 200",
                        (like, like, like)
                    )]
                if not ids:
                    return []
                conditions.append(f"id IN ({','.join('?'*len(ids))})")
                params.extend(ids)

            if category:
                conditions.append("category = ?")
                params.append(category)

            if tags:
                for tag in tags:
                    conditions.append("tags LIKE ?")
                    params.append(f'%"{tag}"%')

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            order = {
                "importance": "importance DESC, updated_at DESC",
                "time":       "updated_at DESC",
                "relevance":  "importance DESC",
            }.get(sort, "updated_at DESC")

            rows = conn.execute(
                f"SELECT * FROM entries {where} ORDER BY {order} LIMIT ?",
                params + [limit]
            ).fetchall()

            return [_row_to_dict(r) for r in rows]

    # ── 取得單筆 ──────────────────────────────────────────────────────────────

    def get(self, entry_id: int) -> Optional[dict]:
        with _get_conn() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            return _row_to_dict(row) if row else None

    # ── 更新 ──────────────────────────────────────────────────────────────────

    def update(self, entry_id: int, **kwargs) -> bool:
        allowed = {"title", "content", "category", "importance", "tags", "ai_summary"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        if "tags" in updates:
            updates["tags"] = json.dumps(updates["tags"], ensure_ascii=False)
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k}=?" for k in updates)
        with _get_conn() as conn:
            conn.execute(f"UPDATE entries SET {sets} WHERE id=?",
                         list(updates.values()) + [entry_id])
        return True

    # ── 刪除 ──────────────────────────────────────────────────────────────────

    def delete(self, entry_id: int) -> bool:
        with _get_conn() as conn:
            conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
        return True

    # ── 取得所有分類 ──────────────────────────────────────────────────────────

    def get_categories(self) -> list[dict]:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT category, COUNT(*) as count
                FROM entries GROUP BY category ORDER BY count DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # ── 取得所有標籤 ──────────────────────────────────────────────────────────

    def get_tags(self) -> list[str]:
        with _get_conn() as conn:
            rows = conn.execute("SELECT DISTINCT tags FROM entries").fetchall()
        all_tags = set()
        for row in rows:
            try:
                for t in json.loads(row[0]):
                    all_tags.add(t)
            except Exception:
                pass
        return sorted(all_tags)

    # ── 統計 ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with _get_conn() as conn:
            total  = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            texts  = conn.execute("SELECT COUNT(*) FROM entries WHERE entry_type='text'").fetchone()[0]
            images = conn.execute("SELECT COUNT(*) FROM entries WHERE entry_type='image'").fetchone()[0]
            videos = conn.execute("SELECT COUNT(*) FROM entries WHERE entry_type='video'").fetchone()[0]
        db_size = DB_PATH.stat().st_size / 1024 / 1024
        return {
            "total": total, "texts": texts,
            "images": images, "videos": videos,
            "db_size_mb": round(db_size, 2)
        }

    # ── 群組管理 ──────────────────────────────────────────────────────────────

    def create_group(self, name: str) -> int:
        """建立新群組，回傳 group_id"""
        now = _now()
        with _get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO groups (name, created_at) VALUES (?,?)", (name, now))
            return cur.lastrowid

    def get_groups(self) -> list[dict]:
        """取得所有群組及其圖片數量"""
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT g.id, g.name, g.created_at,
                       COUNT(e.id) as count,
                       MIN(e.thumb_path) as thumb
                FROM groups g
                LEFT JOIN entries e ON e.group_id = g.id
                GROUP BY g.id ORDER BY g.created_at DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def get_group(self, group_id: int) -> Optional[dict]:
        """取得群組資訊"""
        with _get_conn() as conn:
            row = conn.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
            return dict(row) if row else None

    def get_group_images(self, group_id: int) -> list[dict]:
        """取得群組內所有圖片"""
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM entries WHERE group_id=? ORDER BY created_at ASC",
                (group_id,)
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def add_to_group(self, entry_id: int, group_id: int) -> bool:
        """將圖片加入群組"""
        with _get_conn() as conn:
            conn.execute(
                "UPDATE entries SET group_id=?, updated_at=? WHERE id=?",
                (group_id, _now(), entry_id)
            )
        return True

    def delete_group(self, group_id: int):
        """刪除群組（圖片不刪，只解除群組關聯）"""
        with _get_conn() as conn:
            conn.execute("UPDATE entries SET group_id=NULL WHERE group_id=?", (group_id,))
            conn.execute("DELETE FROM groups WHERE id=?", (group_id,))

    # ── 圖片 base64（給前端顯示用）────────────────────────────────────────────

    def get_thumb_base64(self, entry_id: int) -> str:
        entry = self.get(entry_id)
        if not entry:
            return ""
        path = pathlib.Path(entry.get("thumb_path", ""))
        if not path.exists():
            return ""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()


# 單例
_store = None
def get_store() -> KnowledgeStore:
    global _store
    if _store is None:
        _store = KnowledgeStore()
    return _store
