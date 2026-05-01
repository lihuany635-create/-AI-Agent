import pathlib, ast, shutil, datetime
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)
src = TARGET.read_text(encoding="utf-8", errors="replace")

# 找到模式路由區塊並完整替換
old_mode_routing = "        # \u6a21\u5f0f\u8def\u7531\uff1a\u4f9d\u7167\u6a21\u5f0f\u6c7a\u5b9a\u8d70\u54ea\u4e9b\u6deb\u6212\u5668"

# 找到這段結尾（到 # 1. 反射記憶快取 前）
start_pos = src.find(old_mode_routing)
end_marker = "        # 1. \u53cd\u5c04\u8a18\u61b6\u5feb\u53d6"
end_pos = src.find(end_marker, start_pos if start_pos != -1 else 0)

if start_pos != -1 and end_pos != -1:
    old_block = src[start_pos:end_pos]
    
    new_block = """        # \u6a21\u5f0f\u8def\u7531\uff1a\u4f9d\u7167\u6a21\u5f0f\u6c7a\u5b9a\u8d70\u54ea\u4e9b\u6deb\u6212\u5668

        # \u7d42\u7aef\u6a21\u5f0f\uff1a\u76f4\u63a5\u57f7\u884c\u7d42\u7aef\u6307\u4ee4
        if mode == "terminal":
            if _USE_TERMINAL:
                terminal = get_terminal()
                t = text.strip()
                if t in ["\u78ba\u8a8d", "\u597d", "\u57f7\u884c", "yes", "ok"] and terminal.has_pending():
                    return terminal.confirm()
                if t in ["\u53d6\u6d88", "\u4e0d", "\u7b97\u4e86", "cancel"] and terminal.has_pending():
                    return terminal.cancel()
                result = terminal.handle(text)
                if result is not None:
                    return result
            return self._think(text)

        # \u81ea\u4e3b\u958b\u767c\u6a21\u5f0f\uff1a\u8aaa\u9700\u6c42\uff0c\u7acb\u81ea\u5df1\u5b8c\u6210
        if mode == "dev":
            if _USE_DEV:
                eng = get_dev_engine()
                t = text.strip()
                if t in ["\u78ba\u8a8d", "\u597d", "\u57f7\u884c", "yes", "ok"] and eng.has_pending():
                    return eng.confirm()
                if t in ["\u53d6\u6d88", "\u4e0d", "\u7b97\u4e86", "cancel"] and eng.has_pending():
                    return eng.cancel()
                # \u4efb\u4f55\u6587\u5b57\u90fd\u7576\u6210\u958b\u767c\u9700\u6c42
                return eng.handle(text)
            return self._think(text)

        # \u6559\u5b78\u6a21\u5f0f\uff1a\u5df2\u5728 desktop_agent \u8655\u7406\uff0c\u4e0d\u61c9\u8d70\u5230\u9019\u88e1
        if mode == "teach":
            return self._think(text)

        # \u684c\u9762\u6a21\u5f0f\uff1a\u53ea\u8d70\u684c\u9762\u63a7\u5236\u548c\u6a94\u6848\u7ba1\u7406
        if mode == "desktop":
            if _USE_DESKTOP:
                result = get_control().handle(text)
                if result is not None:
                    return result
            if _USE_FM:
                _c = ["\u5217\u51fa\u6a94\u6848","\u67e5\u770b\u8cc7\u6599\u593e",
                      "\u8cc7\u6599\u593e","\u5efa\u7acb\u8cc7\u6599\u593e","\u522a\u9664\u6a94\u6848",
                      "\u91cd\u547d\u540d","\u641c\u5c0b\u6a94\u6848","\u958b\u555f\u6a94\u6848",
                      "\u58d3\u7e2e","\u89e3\u58d3\u7e2e","\u6a94\u6848\u8cc7\u8a0a","\u76ee\u524d\u4f4d\u7f6e"]
                if any(k in text for k in _c):
                    result = get_fm().handle(text)
                    if result is not None:
                        return result
            if _USE_TERMINAL:
                result = get_terminal().handle(text)
                if result is not None:
                    return result
            return "\u627e\u4e0d\u5230\u5c0d\u61c9\u7684\u684c\u9762\u6307\u4ee4"

        # \u5c0d\u8a71\u6a21\u5f0f\uff08chat\uff09\uff1a\u4e0d\u8d70\u7d42\u7aef\u548c\u958b\u767c\u6deb\u6212\uff0c\u76f4\u63a5\u5230 LLM

"""
    
    src = src[:start_pos] + new_block + src[end_pos:]
    print("模式路由替換成功")
else:
    print(f"找不到模式路由區塊 (start={start_pos}, end={end_pos})")
    # 在 process_input 開頭加入新的模式路由
    old_log_line = '        logger.info(f"[process_input]'
    log_pos = src.find(old_log_line)
    if log_pos != -1:
        log_end = src.find("\n", log_pos) + 1
        new_routing = log_pos  # 在 log 之後插入
        
        insert_code = """
        # \u7d42\u7aef\u6a21\u5f0f
        if mode == "terminal":
            if _USE_TERMINAL:
                result = get_terminal().handle(text)
                if result is not None:
                    return result
            return self._think(text)

        # \u81ea\u4e3b\u958b\u767c\u6a21\u5f0f
        if mode == "dev":
            if _USE_DEV:
                eng = get_dev_engine()
                t = text.strip()
                if t in ["\u78ba\u8a8d", "\u597d", "\u57f7\u884c"] and eng.has_pending():
                    return eng.confirm()
                if t in ["\u53d6\u6d88", "\u4e0d", "\u7b97\u4e86"] and eng.has_pending():
                    return eng.cancel()
                return eng.handle(text)
            return self._think(text)

        # \u684c\u9762\u6a21\u5f0f
        if mode == "desktop":
            if _USE_DESKTOP:
                result = get_control().handle(text)
                if result is not None:
                    return result
            return "\u627e\u4e0d\u5230\u5c0d\u61c9\u6307\u4ee4"

"""
        src = src[:log_end] + insert_code + src[log_end:]
        print("在 log 後插入模式路由")

# 同時移除 chat 模式下的終端和 self_dev 攔截（只在對應模式才觸發）
# 找到終端攔截並加上模式限制
old_terminal_guard = '        if _USE_TERMINAL:'
terminal_count = src.count(old_terminal_guard)
print(f"找到 {terminal_count} 個 _USE_TERMINAL 攔截")

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK - 請重啟")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    lines = src.splitlines()
    for i in range(max(0,e.lineno-3), min(len(lines),e.lineno+3)):
        print(f"{i+1}: {repr(lines[i])}")
    shutil.copy2(backup, TARGET)
    print("已還原")
