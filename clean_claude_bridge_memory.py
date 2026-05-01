# clean_claude_bridge_memory.py — 清理 claude_bridge 存入的無效記憶
# 使用：python clean_claude_bridge_memory.py

import json
import pathlib

MEMORY_FILE = pathlib.Path("memory/long_term_memory.json")

invalid_signs = [
    "{立}", "OCR", "載入失敗", "無法讀取", "超時",
    "Good evening", "Good morning", "Good afternoon",
    "How can I help", "Connect your tools",
    "Artifacts", "Youtube telegram", "Word editor",
    "Desktop agent", "Word toolbar", "Youtube bridge",
    "11S 2600", "IU",
]

def clean():
    if not MEMORY_FILE.exists():
        print("找不到記憶庫檔案")
        return

    data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    before = len(data)

    cleaned = []
    removed = []
    for mem in data:
        content = mem.get("content", "")
        source  = mem.get("source", "")

        # 只清理 claude_bridge 來源的記憶
        if source != "claude_bridge":
            cleaned.append(mem)
            continue

        # 判斷是否為無效記憶
        is_invalid = any(sign in content for sign in invalid_signs)
        is_too_short = len(content.strip()) < 10

        if is_invalid or is_too_short:
            removed.append(content[:60])
        else:
            cleaned.append(mem)

    MEMORY_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"清理完成：{before} 筆 → {len(cleaned)} 筆")
    print(f"已刪除 {len(removed)} 筆：")
    for r in removed:
        print(f"  - {r}")

if __name__ == "__main__":
    clean()
