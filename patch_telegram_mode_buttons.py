"""
patch_telegram_mode_buttons.py
修復切換模式後功能按鈕消失的問題
執行：python patch_telegram_mode_buttons.py
"""
import pathlib

dst = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent\telegram_bot.py")
content = dst.read_text(encoding="utf-8")

OLD = '        bot.send_message(cid, f"已切換到 {mode_names.get(mode_id, mode_id)}")\n        return\n\n    # ── show_modes'

NEW = '''        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        actions = {
            "chat":     [("🤖 問 Claude", "act_ask_claude"), ("💬 問 ChatGPT", "act_ask_chatgpt")],
            "terminal": [("⚡ 查看能力", "act_capabilities"), ("🔧 自動修復", "act_repair"), ("🔍 分析模組", "act_analyze")],
            "dev":      [("💻 開發歷史", "act_dev_history"), ("🔧 自動修復", "act_repair"), ("✅ 確認步驟", "dev_confirm"), ("❌ 取消步驟", "dev_cancel")],
            "teach":    [("➕ 新增知識", "act_add_knowledge"), ("🤖 問 Claude", "act_ask_claude")],
            "database": [("🧠 查看記憶庫", "act_memory"), ("🎓 Claude知識庫", "act_ck_stats"), ("💬 ChatGPT知識庫", "act_gpt_knowledge"), ("📖 模組說明", "act_module_explain")],
            "desktop":  [("📸 截圖", "act_screenshot"), ("🪟 列出視窗", "act_list_windows"), ("📁 查看桌面", "act_ls_desktop"), ("💻 系統資訊", "act_sysinfo")],
        }
        btns = actions.get(mode_id, [])
        if btns:
            kb = InlineKeyboardMarkup(row_width=2)
            for label, cb in btns:
                kb.add(InlineKeyboardButton(label, callback_data=cb))
            kb.add(InlineKeyboardButton("⬅️ 返回模式選單", callback_data="show_modes"))
            bot.send_message(cid, f"✅ 已切換到 {mode_names.get(mode_id, mode_id)}", reply_markup=kb)
        else:
            bot.send_message(cid, f"✅ 已切換到 {mode_names.get(mode_id, mode_id)}")
        return

    # ── show_modes'''

if OLD not in content:
    print("❌ 找不到目標內容，可能已經更新過了")
    exit(1)

bak = dst.with_suffix(".py.bak3")
bak.write_text(content, encoding="utf-8")
print(f"✅ 已備份到：{bak}")

new_content = content.replace(OLD, NEW)
dst.write_text(new_content, encoding="utf-8")
print("✅ 完成！切換模式後會顯示功能按鈕了")
