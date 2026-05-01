import shutil
import ast
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
VAULT_DIR = BASE_DIR / "code_vault"


def validate_ast(file_path):
    try:
        code = Path(file_path).read_text(encoding="utf-8")
        ast.parse(code)
        return True
    except Exception:
        return False


def backup_file(file_path):
    path = Path(file_path)

    if not path.exists():
        return {
            "status": "failed",
            "reason": "file_not_exist"
        }

    VAULT_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{path.name}.{timestamp}.bak"
    backup_path = VAULT_DIR / backup_name

    shutil.copy2(path, backup_path)

    return {
        "status": "success",
        "backup": str(backup_path)
    }


def restore_file(file_path):
    path = Path(file_path)

    backups = sorted(
        VAULT_DIR.glob(f"{path.name}.*.bak"),
        reverse=True
    )

    if not backups:
        return {
            "status": "failed",
            "reason": "no_backup"
        }

    latest_backup = backups[0]

    shutil.copy2(latest_backup, path)

    if not validate_ast(file_path):
        return {
            "status": "failed",
            "reason": "rollback_ast_invalid"
        }

    return {
        "status": "restored",
        "from": str(latest_backup)
    }


def rollback(project_state):
    """
    未來：可擴充整體系統回滾
    """
    changed = project_state.get("changed", [])

    results = []

    for file in changed:
        r = restore_file(file)
        results.append(r)

    return results


def list_backups(file_path):
    path = Path(file_path)

    backups = sorted(
        VAULT_DIR.glob(f"{path.name}.*.bak"),
        reverse=True
    )

    return [str(b) for b in backups]