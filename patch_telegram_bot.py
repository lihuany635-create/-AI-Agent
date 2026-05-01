"""
patch_telegram_bot.py
直接修改專案裡的 telegram_bot.py，補充缺少的 callback handler
執行：python patch_telegram_bot.py
"""
import pathlib

dst = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent\telegram_bot.py")
content = dst.read_text(encoding="utf-8")

OLD = '''    VALID = {"dev_confirm", "dev_cancel", "dev_rollback", "dev_stop", "dev_back_models"}
    if call.data not in VALID:
        bot.answer_callback_query(call.id, "")
        return'''

NEW = '''    # mode_* 模式切換
    if call.data.startswith("mode_"):
        mode_id = call.data.replace("mode_", "")
        _set_mode(cid, mode_id)
        mode_names = {
            "chat": "💬 對話模式", "terminal": "⌨️ 終端模式",
            "dev": "🤖 自主開發模式", "teach": "📚 教學模式",
            "database": "🗄 資料庫模式", "desktop": "🖥 桌面模式",
        }
        bot.answer_callback_query(call.id, mode_names.get(mode_id, mode_id))
        try:
            bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.send_message(cid, f"已切換到 {mode_names.get(mode_id, mode_id)}")
        return

    # show_modes
    if call.data == "show_modes":
        bot.answer_callback_query(call.id, "")
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("💬 對話",    callback_data="mode_chat"),
            InlineKeyboardButton("⌨️ 終端",    callback_data="mode_terminal"),
            InlineKeyboardButton("🤖 自主開發", callback_data="mode_dev"),
            InlineKeyboardButton("📚 教學",    callback_data="mode_teach"),
            InlineKeyboardButton("🗄 資料庫",  callback_data="mode_database"),
            InlineKeyboardButton("🖥 桌面",    callback_data="mode_desktop"),
        )
        bot.send_message(cid, "請選擇模式：", reply_markup=kb)
        return

    # dt_* dev_tool callback
    if call.data.startswith("dt_"):
        bot.answer_callback_query(call.id, "⏳ 處理中...")
        try:
            from dev_tool import get_tool
            handled = get_tool().handle_callback(call.data)
            if not handled:
                bot.send_message(cid, f"❌ 未知指令：{call.data}")
        except Exception as e:
            bot.send_message(cid, f"❌ 執行失敗：{e}")
        try:
            bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        return

    # devmode_*
    if call.data.startswith("devmode_"):
        mode = call.data.replace("devmode_", "")
        try:
            bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        if mode == "solo":
            bot.answer_callback_query(call.id, "立AI自己開發")
            bot.send_message(cid, "立AI自己開發模式\n\n請直接輸入需求：")
        else:
            bot.answer_callback_query(call.id, "與Claude共同開發")
            bot.send_message(cid, "與 Claude 共同開發模式\n\n請直接輸入需求：")
        return

    # mem_*
    if call.data.startswith("mem_"):
        if call.data == "mem_save":
            bot.answer_callback_query(call.id, "已存入記憶")
            bot.edit_message_text("已存入記憶", chat_id=cid, message_id=call.message.message_id)
        elif call.data == "mem_skip":
            bot.answer_callback_query(call.id, "已跳過")
            bot.edit_message_text("已跳過", chat_id=cid, message_id=call.message.message_id)
        return

    # act_* 功能按鈕
    if call.data.startswith("act_"):
        import threading, subprocess
        bot.answer_callback_query(call.id, "⏳ 執行中...")
        act = call.data
        if act == "act_memory":
            try:
                from long_term_memory import get_memory
                items = sorted(get_memory()._memories, key=lambda m: m["accessed_at"], reverse=True)[:8]
                lines = ["🧠 最近記憶："] + [f"★ {m['content'][:60]}" for m in items]
                bot.send_message(cid, "\n".join(lines))
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_capabilities":
            bot.send_message(cid,
                "⚡ 立 AI 能力：\n\n💬 對話、⌨️ 終端、🤖 開發\n"
                "📚 教學、🖥 桌面、🌐 YouTube\n🤝 Claude/ChatGPT 橋接"
            )
        elif act == "act_ck_stats":
            try:
                from claude_knowledge import get_knowledge
                bot.send_message(cid, get_knowledge().get_stats())
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_gpt_knowledge":
            try:
                from chatgpt_knowledge import get_knowledge
                bot.send_message(cid, get_knowledge().get_stats())
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_repair":
            def _repair():
                try:
                    r = subprocess.run(
                        ["python", "-c", "from repair_engine import RepairEngine; r=RepairEngine(); print(r.run_diagnosis())"],
                        capture_output=True, text=True, timeout=30, encoding="utf-8", errors="ignore"
                    )
                    bot.send_message(cid, r.stdout[:4000] or "完成")
                except Exception as e:
                    bot.send_message(cid, f"❌ {e}")
            threading.Thread(target=_repair, daemon=True).start()
        elif act == "act_screenshot":
            def _ss():
                try:
                    r = subprocess.run(
                        ["python", "-c",
                         "import pyautogui,datetime,pathlib;"
                         "p=pathlib.Path('memory/screenshots');p.mkdir(exist_ok=True);"
                         "f=p/('ss_'+datetime.datetime.now().strftime('%H%M%S')+'.png');"
                         "pyautogui.screenshot(str(f));print('截圖：'+str(f))"],
                        capture_output=True, text=True, timeout=15, encoding="utf-8", errors="ignore"
                    )
                    bot.send_message(cid, r.stdout or "截圖完成")
                except Exception as e:
                    bot.send_message(cid, f"❌ {e}")
            threading.Thread(target=_ss, daemon=True).start()
        elif act == "act_list_windows":
            try:
                import pygetwindow as gw
                wins = [w.title for w in gw.getAllWindows() if w.title][:15]
                bot.send_message(cid, "🪟 目前視窗：\n" + "\n".join(wins))
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_ls_desktop":
            try:
                import pathlib
                desktop = pathlib.Path.home() / "OneDrive" / "桌面"
                if not desktop.exists():
                    desktop = pathlib.Path.home() / "Desktop"
                files = [f.name for f in desktop.iterdir()][:20]
                bot.send_message(cid, "📁 桌面：\n" + "\n".join(files))
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_sysinfo":
            try:
                import psutil
                cpu = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                bot.send_message(cid,
                    f"💻 系統資訊\nCPU：{cpu}%\n"
                    f"記憶體：{mem.percent}% ({mem.used//1024//1024}MB/{mem.total//1024//1024}MB)\n"
                    f"磁碟：{disk.percent}%"
                )
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_dev_history":
            try:
                import json, pathlib
                hf = pathlib.Path("memory/dev_history.json")
                if hf.exists():
                    history = json.loads(hf.read_text(encoding="utf-8"))
                    lines = ["💻 最近開發歷史："] + [f"✓ {h.get('file','?')} — {h.get('goal','?')[:40]}" for h in history[-5:]]
                    bot.send_message(cid, "\n".join(lines))
                else:
                    bot.send_message(cid, "尚無開發歷史")
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act == "act_logs":
            try:
                import pathlib
                log_file = pathlib.Path("memory/agent.log")
                if log_file.exists():
                    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                    bot.send_message(cid, "\n".join(lines[-30:])[:4000])
                else:
                    bot.send_message(cid, "找不到日誌檔案")
            except Exception as e:
                bot.send_message(cid, f"❌ {e}")
        elif act in ("act_ask_claude", "act_ask_chatgpt", "act_analyze", "act_module_explain", "act_add_knowledge"):
            prompts = {
                "act_ask_claude": "請輸入要問 Claude 的問題：",
                "act_ask_chatgpt": "請輸入要問 ChatGPT 的問題：",
                "act_analyze": "請輸入要分析的檔名：",
                "act_module_explain": "請輸入要查詢的檔名：",
                "act_add_knowledge": "請輸入要存入知識庫的內容：",
            }
            bot.send_message(cid, prompts[act])
        return

    VALID = {"dev_confirm", "dev_cancel", "dev_rollback", "dev_stop", "dev_back_models"}
    if call.data not in VALID and not call.data.startswith("dev_model_") and not call.data.startswith("dev_start_"):
        bot.answer_callback_query(call.id, "")
        return'''

if OLD not in content:
    print("❌ 找不到要替換的內容，可能已經更新過了")
    exit(1)

# 備份
bak = dst.with_suffix(".py.bak2")
bak.write_text(content, encoding="utf-8")
print(f"✅ 已備份到：{bak}")

new_content = content.replace(OLD, NEW)
dst.write_text(new_content, encoding="utf-8")

old_lines = content.count("\n")
new_lines = new_content.count("\n")
print(f"✅ 完成！從 {old_lines} 行增加到 {new_lines} 行（新增 {new_lines - old_lines} 行 callback）")
