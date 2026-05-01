import os
import ast
import hashlib
import json

HASH_FILE = ".lobster_hashes.json"


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_hashes():
    if not os.path.exists(HASH_FILE):
        return {}
    with open(HASH_FILE, "r") as f:
        return json.load(f)


def save_hashes(hashes):
    with open(HASH_FILE, "w") as f:
        json.dump(hashes, f, indent=2)


def scan_project(path=None):

    if path is None:
        path = os.path.abspath(os.getcwd())

    python_files = []
    ast_map = {}
    new_hashes = {}

    old_hashes = load_hashes()

    exclude_dirs = {
        '.git',
        'venv',
        '.venv',
        'sandbox',
        '__pycache__',
        'memory',
        'graph'
    }

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            if not file.endswith(".py"):
                continue

            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, path)

            if rel_path == "Lobster_Orchestrator.py":
                continue

            python_files.append(rel_path)

            # === HASH ===
            h = file_hash(full_path)
            new_hashes[rel_path] = h

            # === AST ===
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                ast_map[rel_path] = tree
            except Exception as e:
                ast_map[rel_path] = f"AST_ERROR: {str(e)}"

    save_hashes(new_hashes)

    changed_files = [
        f for f in new_hashes
        if old_hashes.get(f) != new_hashes[f]
    ]

    state = {
        "files": python_files,
        "changed": changed_files,
        "ast": ast_map
    }

    return state