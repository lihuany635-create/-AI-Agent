import os
import shutil
import ast
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = BASE_DIR / "memory" / "backups"


def validate_ast(code):
    try:
        ast.parse(code)
        return True
    except Exception:
        return False


def atomic_write(file_path, content, encoding="utf-8"):
    path = Path(file_path)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding=encoding) as f:
            f.write(content)

        os.replace(temp_path, path)

        return True

    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        return False


def backup_file(file_path):
    path = Path(file_path)

    if not path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{path.name}.{timestamp}.bak"

    shutil.copy(path, backup_path)

    return str(backup_path)


def safe_apply_patch(file_path, new_code, risk="medium"):
    """
    AI 修復免疫層
    """

    # 1️⃣ AST 檢查
    if not validate_ast(new_code):
        return {
            "status": "blocked",
            "reason": "AST_INVALID"
        }

    # 2️⃣ 高風險阻擋
    if risk == "high":
        return {
            "status": "blocked",
            "reason": "HIGH_RISK"
        }

    # 3️⃣ 備份
    backup_path = backup_file(file_path)

    # 4️⃣ 寫入
    ok = atomic_write(file_path, new_code)

    if not ok:
        return {
            "status": "failed",
            "backup": backup_path
        }

    return {
        "status": "success",
        "backup": backup_path
    }