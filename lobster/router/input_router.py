# lobster/router/input_router.py
import re
import threading

try:
    from agent_logger import get_logger
    logger = get_logger("lobster.router")
except ImportError:
    import logging
    logger = logging.getLogger("lobster.router")

try:
    from terminal_engine import get_terminal
    _USE_TERMINAL = True
except ImportError:
    _USE_TERMINAL = False

try:
    from dev_tool import get_tool as get_dev_tool
    _USE_DEV_TOOL = True
except ImportError:
    _USE_DEV_TOOL = False

try:
    from self_healer import get_healer
    _USE_HEALER = True
except ImportError:
    _USE_HEALER = False

try:
    from model_selector import get_selector
    _USE_SELECTOR = True
except ImportError:
    _USE_SELECTOR = False

try:
    from claude_desktop_bridge import get_bridge as get_claude_bridge
    _USE_CLAUDE_BRIDGE = True
except ImportError:
    _USE_CLAUDE_BRIDGE = False

try:
    import sys as _sys_dc
    _PKG_DC = r"C:\Users\ACER\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    if _PKG_DC not in _sys_dc.path:
        _sys_dc.path.insert(0, _PKG_DC)
    from desktop_control import get_control
    _USE_DESKTOP = True
except Exception:
    _USE_DESKTOP = False

from lobster.integration.push import push_to_phone


def route(core, text: str, reflex, mode: str = "chat") -> str:
    logger.info(f"[router] [{mode}] 收到：{text[:60]}")

    if mode == "terminal":
        if _USE_TERMINAL:
            terminal = get_terminal()
            t = text.strip()
            if t in ["確認", "好", "執行", "yes", "ok", "是"] and terminal.has_pending():
                return terminal.confirm()
            if t in ["取消", "不", "算了", "no", "cancel"] and terminal.has_pending():
                return terminal.cancel()
            if t in ["指令歷史", "歷史"]:
                return terminal.get_history()
            result = terminal.handle(text)
            if result is not None:
                return result
            return f"無法執行指令：{text[:50]}"
        return "終端模式未載入"

    if mode == "dev":
        if _USE_DEV_TOOL:
            tool = get_dev_tool()
            t = text.strip()
            if any(kw in t for kw in ["繼續作業", "繼續上次", "繼續開發", "接著做", "繼續做", "我要繼續", "繼續專案"]):
                if tool.state.request and (tool.state.active or tool.state.remaining_groups()):
                    tool.state.active = True
                    tool.state.paused = False
                    tool.state.save()
                    done = len(tool.state.completed_groups)
                    total = len(tool.state.groups)
                    remaining = tool.state.remaining_groups()
                    threading.Thread(target=tool._push_mindmap, daemon=True).start()
                    return (
                        f"🔄 繼續上次的專案：{tool.state.request[:40]}\n"
                        f"已完成 {done}/{total} 個模組，剩餘 {len(remaining)} 個\n"
                        "請在手機選擇要繼續哪個模組"
                    )
                return "目前沒有進行中的專案，請輸入新的需求開始開發。"
            handled = tool.handle_callback(f"dt_input_{t}")
            if not handled:
                threading.Thread(target=tool.start, args=(t,), daemon=True).start()
                return "🤖 開始規劃，請稍候，完成後會推送到手機..."

    if mode == "desktop":
        if _USE_DESKTOP:
            result = get_control().handle(text)
            if result is not None:
                return result
        return "找不到對應的桌面指令，請嘗試：截圖、列出視窗、查看資料夾"

    if mode == "teach":
        try:
            from long_term_memory import get_memory
            get_memory().store(text, tags=["user_teach"], importance=8, source="teach_mode")
            return f"✅ 已學習：{text[:60]}"
        except Exception as e:
            return f"存入記憶庫失敗：{e}"

    if mode == "database":
        try:
            from claude_knowledge import get_knowledge
            results = get_knowledge().search(text, top_k=3)
            if results:
                lines = ["📚 找到 " + str(len(results)) + " 筆相關知識："]
                for r in results:
                    lines.append("\n【" + r['category'] + "】" + r['content'][:150])
                return "\n".join(lines)
            return f"知識庫中找不到「{text[:40]}」的相關資料"
        except Exception as e:
            return f"知識庫查詢失敗：{e}"

    # chat 模式
    _claude_match = (
        re.match(r"^問\s*Claude[：:]\s*(.+)", text, re.IGNORECASE) or
        re.match(r"^去找\s*Claude\s*學習[：:]\s*(.+)", text, re.IGNORECASE) or
        re.match(r"^請問\s*Claude[：:]\s*(.+)", text, re.IGNORECASE)
    )
    _loop_match = re.match(r"^(去找\s*Claude\s*對話學習|Claude\s*對話學習)[：:]\s*(.+)", text, re.IGNORECASE)

    if _USE_CLAUDE_BRIDGE and _loop_match:
        question = _loop_match.group(2).strip()
        worker_ref = getattr(core, "_worker_ref", None)
        def _show_bar(show):
            if worker_ref:
                try: worker_ref.claude_bar_sig.emit(show)
                except Exception: pass
        def _notify(msg):
            if worker_ref:
                try: worker_ref.claude_reply_sig.emit(msg)
                except Exception: pass
            push_to_phone("Claude", msg)
        def _run_loop():
            try:
                _show_bar(True)
                result = get_claude_bridge().chat_loop(question, max_rounds=20, notify_fn=_notify, ui_ref=None)
                _notify("✅ 對話學習完成：" + result)
            except Exception as e:
                logger.warning(f"[router] 對話循環失敗：{e}")
            finally:
                _show_bar(False)
        threading.Thread(target=_run_loop, daemon=True).start()
        return "🔄 開始與 Claude 對話學習：" + question + "\n隨時可以按停止按鈕結束"

    if _USE_CLAUDE_BRIDGE and _claude_match:
        question = _claude_match.group(1).strip()
        def _run_single():
            try:
                get_claude_bridge().chat_loop(question, max_rounds=20, notify_fn=push_to_phone, ui_ref=getattr(core, "_ui_ref", None))
            except Exception as e:
                logger.warning(f"[router] Claude 循環失敗：{e}")
        threading.Thread(target=_run_single, daemon=True).start()
        return "🔄 開始與 Claude 對話，隨時可按停止按鈕結束"

    if any(kw in text for kw in ["Claude知識庫", "claude知識庫", "知識庫統計", "查看知識庫"]):
        try:
            from claude_knowledge import get_knowledge
            return get_knowledge().get_stats()
        except Exception as e:
            return f"Claude 知識庫未載入：{e}"

    mem = core.reflex_memory.get(text)
    if mem:
        return mem

    r = reflex.analyze(text)
    if r:
        return r

    if _USE_HEALER:
        t = text.strip()
        if any(k in t for k in ["自我診斷", "掃描自己", "健康檢查", "自動修復自己"]):
            def _heal():
                get_healer().scan_and_heal(notify_fn=lambda msg: push_to_phone("自我診斷", msg))
            threading.Thread(target=_heal, daemon=True).start()
            return "開始自我診斷，完成後通知你。"
        if any(k in t for k in ["診斷報告", "上次診斷", "健康報告"]):
            return get_healer().get_last_report()

    if _USE_SELECTOR:
        t = text.strip()
        if any(k in t for k in ["目前模型", "用什麼模型", "哪個模型", "模型狀態"]):
            return get_selector().status()
        if "模型" in t and ("切換" in t or "換成" in t):
            _m = re.search(r"[\w.:]{3,}", t.replace("切換模型", "").replace("切換", "").strip())
            if _m:
                result = get_selector().force_switch(_m.group(0))
                core.model = get_selector().current()
                return result

    from lobster.engine.infer_engine import think
    return think(core, text)
