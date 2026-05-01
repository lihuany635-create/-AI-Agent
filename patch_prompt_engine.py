import pathlib, ast, shutil, datetime
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("prompt_engine.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

new_content = '''from cognition_state_manager import get_current_context


class PromptEngine:

    def build_prompt(self, text, episodic):

        context = get_current_context()

        # 情節記憶（最近對話）
        recent = episodic.search_recent(3)
        mem = ""
        for e in recent:
            mem += f"\\n過去經驗：{e[\'input\']} \\u2192 {e[\'response\']}"

        # 長期記憶（知識庫搜尋）
        long_mem = ""
        try:
            from long_term_memory import get_memory
            lm = get_memory()
            results = lm.search(text, top_k=3)
            if results:
                long_mem = "\\n[相關知識]"
                for r in results:
                    long_mem += f"\\n- {r[\'content\'][:150]}"
        except Exception:
            pass

        return f"""
{long_mem}

{mem}

[當前上下文]
{context}

[輸入]
{text}
"""
'''

TARGET.write_text(new_content, encoding="utf-8")
print("OK - prompt_engine.py 已更新，長期記憶已注入")
print("請重啟 desktop_agent.py")

