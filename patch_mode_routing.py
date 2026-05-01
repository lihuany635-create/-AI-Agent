import pathlib, ast, shutil, datetime
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')

TARGET = pathlib.Path("Lobster_Core.py")
backup = TARGET.with_suffix(f".py.{datetime.datetime.now().strftime('%H%M%S')}.bak")
shutil.copy2(TARGET, backup)

src = TARGET.read_text(encoding="utf-8", errors="replace")

# 在 process_input 最開頭加入模式路由
# 從 desktop_agent 傳入 mode 參數
old_sig = "    def process_input(self, text: str, reflex, router) -> str:"
new_sig = "    def process_input(self, text: str, reflex, router, mode: str = 'chat') -> str:"

src = src.replace(old_sig, new_sig)

# 在 process_input 記錄 log 後加入模式路由
old_log = '        logger.info(f"[process_input] 收到：{text[:60]}")\n\n        # 1. 反射記憶快取'

new_log = '''        logger.info(f"[process_input] [{mode}] 收到：{text[:60]}")

        # ── 模式路由：依照模式決定走哪些攔截器 ──────────────────────────────

        # 桌面模式：只走桌面控制和檔案管理
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
            # 桌面模式也可以執行終端指令
            if _USE_TERMINAL:
                result = get_terminal().handle(text)
                if result is not None:
                    return result
            return "\u627e\u4e0d\u5230\u5c0d\u61c9\u7684\u684c\u9762\u6307\u4ee4\uff0c\u8acb\u8aee\u554f\uff1a\u622a\u5716\u3001\u5217\u51fa\u8996\u7a97\u3001\u67e5\u770b\u8cc7\u6599\u593e"

        # 改程式模式：只走開發相關攔截器
        if mode == "dev":
            t = text.strip()
            if _USE_DEV:
                eng = get_dev_engine()
                if t in ["\u78ba\u8a8d", "\u597d", "\u57f7\u884c", "yes", "ok", "\u662f", "\u5c0d"] and eng.has_pending():
                    return eng.confirm()
                if t in ["\u53d6\u6d88", "\u4e0d", "\u7b97\u4e86", "no", "cancel", "\u4e0d\u8981"] and eng.has_pending():
                    return eng.cancel()
                if eng._is_dev_request(text) if hasattr(eng, '_is_dev_request') else True:
                    return eng.handle(text)
            if _USE_TERMINAL:
                result = get_terminal().handle(text)
                if result is not None:
                    return result
            return self._think(text)

        # 教學模式：直接存記憶（desktop_agent 已處理，這裡不應走到）
        if mode == "teach":
            return self._think(text)

        # 1. 反射記憶快取'''

src = src.replace(old_log, new_log)

# 同時修改 AgentWorker 的 _call，傳入 mode
# 找到 _call 方法
old_call = """    def _call(self):
        if _lobster and _reflex and _router:
            return _lobster.process_input(self.text, _reflex, _router)
        if _lobster:
            return _lobster.run(self.text)"""

new_call = """    def _call(self):
        mode = getattr(self, 'mode', 'chat')
        if _lobster and _reflex and _router:
            return _lobster.process_input(self.text, _reflex, _router, mode=mode)
        if _lobster:
            return _lobster.run(self.text)"""

src = src.replace(old_call, new_call)

try:
    ast.parse(src)
    TARGET.write_text(src, encoding="utf-8")
    print("OK - Lobster_Core 模式路由完成")
except SyntaxError as e:
    print(f"Error L{e.lineno}: {e.msg}")
    lines = src.splitlines()
    for i in range(max(0,e.lineno-3), min(len(lines),e.lineno+3)):
        print(f"{i+1}: {repr(lines[i])}")
    shutil.copy2(backup, TARGET)
    print("已還原")
