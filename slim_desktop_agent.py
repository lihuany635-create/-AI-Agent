"""
slim_desktop_agent.py
把 desktop_agent.py 裡的 _start_telegram_bot 換成三行呼叫 telegram_bot.py
執行：python slim_desktop_agent.py
"""
import pathlib

src = pathlib.Path(r"C:\Users\ACER\OneDrive\桌面\AI-Agent\desktop_agent.py")
content = src.read_text(encoding="utf-8")

# 找到 _start_telegram_bot 開頭
start_marker = "    def _start_telegram_bot(self):"
# 找到下一個同層級的 def（4個空格開頭）
end_marker = "    def _build_ui(self):"

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker)

if start_idx == -1:
    print("❌ 找不到 _start_telegram_bot")
    exit(1)
if end_idx == -1:
    print("❌ 找不到 _build_ui")
    exit(1)

old_block = content[start_idx:end_idx]

new_block = '''    def _start_telegram_bot(self):
        """啟動 Telegram Bot（統一由 telegram_bot.py 管理）"""
        import threading
        try:
            from telegram_bot import start_bot
            threading.Thread(target=start_bot, kwargs={"background": False}, daemon=True).start()
            self._log(f"[{self._ts()}] [系統] Telegram Bot 啟動中...")
        except Exception as e:
            self._log(f"[{self._ts()}] [系統] Telegram Bot 啟動失敗：{e}")

'''

new_content = content.replace(old_block, new_block)

if new_content == content:
    print("❌ 替換失敗，內容沒有變化")
    exit(1)

# 備份原始檔案
backup = src.with_suffix(".py.bak")
backup.write_text(content, encoding="utf-8")
print(f"✅ 已備份到：{backup}")

src.write_text(new_content, encoding="utf-8")

original_lines = content.count("\n")
new_lines = new_content.count("\n")
print(f"✅ 完成！從 {original_lines} 行縮減到 {new_lines} 行（減少 {original_lines - new_lines} 行）")
