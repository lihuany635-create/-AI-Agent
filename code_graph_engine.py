import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GRAPH_DIR = BASE_DIR / "graph"
GRAPH_FILE = GRAPH_DIR / "code_graph.json"


def build_code_graph(project_state):
    """
    建立系統認知知識圖
    """

    graph = {}

    files = project_state["files"]
    ast_map = project_state["ast"]
    changed = project_state["changed"]

    for file in files:

        node_info = {
            "changed": file in changed,
            "functions": [],
            "classes": [],
            "imports": []
        }

        tree = ast_map.get(file)

        if isinstance(tree, str):
            node_info["error"] = tree
            graph[file] = node_info
            continue

        import ast

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                node_info["functions"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                node_info["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    node_info["imports"].append(n.name)
            elif isinstance(node, ast.ImportFrom):
                node_info["imports"].append(node.module)

        graph[file] = node_info

    GRAPH_DIR.mkdir(exist_ok=True)

    with open(GRAPH_FILE, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)

    return graph


def load_code_graph():
    if not GRAPH_FILE.exists():
        return {}

    with open(GRAPH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)