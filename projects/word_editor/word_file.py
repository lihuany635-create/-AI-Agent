# word_file.py — 文字編輯器檔案管理
# 支援開啟、儲存、另存新檔（.txt .html）

import pathlib
from PyQt6.QtWidgets import QFileDialog, QMessageBox


class FileManager:

    OPEN_FILTER = "文字檔 (*.txt);;HTML 檔 (*.html);;Markdown (*.md);;所有檔案 (*.*)"
    SAVE_FILTER = "文字檔 (*.txt);;HTML 檔 (*.html);;所有檔案 (*.*)"

    @staticmethod
    def open_dialog(parent=None) -> str:
        """開啟檔案對話框，回傳選擇的路徑（取消回傳空字串）"""
        path, _ = QFileDialog.getOpenFileName(
            parent, "開啟檔案", "", FileManager.OPEN_FILTER
        )
        return path

    @staticmethod
    def save_dialog(parent=None, current_path: str = "") -> str:
        """另存新檔對話框，回傳選擇的路徑（取消回傳空字串）"""
        path, _ = QFileDialog.getSaveFileName(
            parent, "另存新檔", current_path, FileManager.SAVE_FILTER
        )
        return path

    @staticmethod
    def read(path: str) -> tuple[str, str]:
        """
        讀取檔案，回傳 (內容, 格式)
        格式：'html' 或 'plain'
        """
        p = pathlib.Path(path)
        content = p.read_text(encoding="utf-8", errors="ignore")
        fmt = "html" if p.suffix.lower() == ".html" else "plain"
        return content, fmt

    @staticmethod
    def write(path: str, content: str) -> bool:
        """
        寫入檔案，回傳是否成功
        """
        try:
            pathlib.Path(path).write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            return False

    @staticmethod
    def ask_save(parent=None) -> str:
        """
        詢問是否儲存未儲存的變更
        回傳：'save' / 'discard' / 'cancel'
        """
        reply = QMessageBox.question(
            parent, "未儲存的變更",
            "文件有未儲存的變更，是否儲存？",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Save:
            return "save"
        elif reply == QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"


if __name__ == "__main__":
    print("FileManager 模組載入成功")
    print(f"支援格式：{FileManager.OPEN_FILTER}")
