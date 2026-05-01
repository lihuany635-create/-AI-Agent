# lobster/tools/file_tool.py
import re
import pathlib

def try_read_file(text: str) -> str:
    file_match = re.search(r'([\w\u4e00-\u9fff\-_.]+\.\w{1,5})', text)
    if not file_match:
        return ""
    filename = file_match.group(1)
    search_paths = [
        pathlib.Path("."),
        pathlib.Path("learn_inbox"),
        pathlib.Path("memory"),
        pathlib.Path("projects"),
    ]
    target = None
    for base in search_paths:
        candidate = base / filename
        if candidate.exists():
            target = candidate
            break
    if not target:
        return ""
    try:
        ext = target.suffix.lower()
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(target))
                content = ""
                for page in reader.pages[:10]:
                    page_text = page.extract_text()
                    if page_text:
                        content += page_text + "\n"
                return content[:3000]
            except Exception:
                return ""
        content = target.read_text(encoding="utf-8", errors="ignore")
        return content[:3000]
    except Exception:
        return ""
