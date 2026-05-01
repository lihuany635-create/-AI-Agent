import pathlib, ast, shutil, datetime, re
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)
src = TARGET.read_text(encoding="utf-8", errors="replace")

print("=== 目前 process_input 攔截順序 ===")
lines = src.splitlines()
in_fn = False
for i, line in enumerate(lines, 1):
    if "def process_input" in line:
        in_fn = True
    if in_fn and line.strip().startswith("# "):
        print(f"L{i}: {line.strip()}")
    if in_fn and "return self._think" in line:
        print(f"L{i}: {line.strip()}")
        break
    if i > 400:
        break

print("\n=== 開始修補 ===")

# 修補1：終端引擎攔截 - 只有明確的終端指令格式才觸發
# 找到終端攔截區塊
terminal_pos = src.find("# 5. 終端指令攔截")
if terminal_pos == -1:
    terminal_pos = src.find("# 4. 終端指令攔截")
if terminal_pos == -1:
    terminal_pos = src.find("終端指令攔截")
    
if terminal_pos != -1:
    # 在終端攔截前加上嚴格條件
    line_start = src.rfind("\n", 0, terminal_pos) + 1
    indent = len(src[line_start:terminal_pos]) - len(src[line_start:terminal_pos].lstrip())
    spaces = " " * indent
    
    # 找到 if _USE_TERMINAL: 這行
    terminal_if = src.find("if _USE_TERMINAL:", terminal_pos)
    if terminal_if != -1:
        # 在這行後面的邏輯加上嚴格條件
        # 找到 terminal.handle(text) 的呼叫
        handle_pos = src.find("terminal.handle(text)", terminal_if)
        if handle_pos != -1:
            # 在 handle 前加上條件
            line_before = src.rfind("\n", 0, handle_pos) + 1
            
            # 加入嚴格條件：只有以 python/dir/cd 等開頭，或包含 .exe/.bat 才走終端
            old_terminal_section = src[terminal_if:handle_pos + len("terminal.handle(text)")]
            
            # 找到整個終端攔截區塊並替換
            old_if = "        if _USE_TERMINAL:"
            new_if = """        # 終端指令：只有明確的終端格式才觸發
        # 例如：python xxx.py、dir、cd、ipconfig 等
        _terminal_prefixes = ["python ", "py ", "dir", "cd ", "pip ", "git ",
                               "ipconfig", "systeminfo", "tasklist", "netstat",
                               "ping ", "curl ", "wget ", "npm ", "node "]
        _is_terminal_cmd = (
            any(text.strip().lower().startswith(p) for p in _terminal_prefixes)
            or (text.strip().startswith("./") or text.strip().startswith(".\\\\"))
        )
        if _USE_TERMINAL and _is_terminal_cmd:"""
            
            if old_if in src[terminal_pos:terminal_pos+500]:
                src = src[:terminal_pos] + src[terminal_pos:].replace(old_if, new_if, 1)
                print("修補終端攔截：加入嚴格前綴條件")
            else:
                print(f"找不到 'if _USE_TERMINAL:' 在終端區塊附近")
else:
    print("找不到終端攔截區塊")

# 修補2：self_dev_engine 攔截 - 只有包含 .py 檔名才觸發
dev_pos = src.find("自主開發指令攔截")
if dev_pos != -1:
    # 找到附近的 if _USE_DEV:
    dev_if_pos = src.find("if _USE_DEV", dev_pos - 200)
    if dev_if_pos != -1 and dev_if_pos < dev_pos + 100:
        old_dev_if_line_end = src.find("\n", dev_if_pos)
        old_dev_if = src[dev_if_pos:old_dev_if_line_end]
        
        new_dev_if = (
            "import re as _re_dev2\n"
            "        _has_py = bool(_re_dev2.search(r'\\\\w+\\\\.py', text))\n"
            "        if _USE_DEV and _has_py"
        )
        
        src = src[:dev_if_pos] + new_dev_if + src[old_dev_if_line_end:]
        print("修補 self_dev_engine 攔截：只有 .py 檔名才觸發")
else:
    print("找不到 self_dev_engine 攔截區塊")

# 修補3：dev 模式下沒有 .py 時直接走 LLM
old_step3 = "        # 3. 自我診斷指令攔截"
if old_step3 in src:
    new_step3 = """        # 2.5 dev 模式保護：沒有 .py 檔名時直接走 LLM
        if mode == "dev":
            import re as _re_dev
            if not bool(_re_dev.search(r'\\w+\\.py', text)):
                return self._think(text)

        # 3. 自我診斷指令攔截"""
    src = src.replace(old_step3, new_step3)
    print("加入 dev 模式保護")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("\nOK - 請重啟 desktop_agent.py")
except SyntaxError as e:
    print(f"\nError L{e.lineno}: {e.msg}")
    lines2 = src.splitlines()
    for i in range(max(0,e.lineno-3), min(len(lines2),e.lineno+3)):
        print(f"{i+1}: {repr(lines2[i])}")
    shutil.copy2(backup, TARGET)
    print("已還原")
