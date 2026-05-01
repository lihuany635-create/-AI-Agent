# youtube_handler.py — YouTube 字幕抓取核心
# 使用 yt-dlp 下載字幕，清除時間戳記，回傳純文字
# 依賴：pip install yt-dlp

import subprocess
import pathlib
import tempfile
import re
import os

try:
    from agent_logger import get_logger
    logger = get_logger("youtube_handler")
except ImportError:
    import logging
    logger = logging.getLogger("youtube_handler")


def get_transcript(url: str) -> str | None:
    """
    從 YouTube URL 抓取字幕，回傳純文字。
    失敗回傳 None。
    """
    if not url or ("youtube.com" not in url and "youtu.be" not in url):
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # 嘗試下載繁中 → 簡中 → 英文字幕
            for lang in ["zh-Hant", "zh-Hans", "en"]:
                result = subprocess.run(
                    [
                        "yt-dlp",
                        "--write-auto-sub",
                        "--sub-lang", lang,
                        "--skip-download",
                        "--output", str(pathlib.Path(tmpdir) / "%(id)s"),
                        "--no-playlist",
                        url,
                    ],
                    capture_output=True, text=True, timeout=60,
                    encoding="utf-8", errors="ignore"
                )

                # 找下載的字幕檔
                vtt_files = list(pathlib.Path(tmpdir).glob("*.vtt"))
                srt_files = list(pathlib.Path(tmpdir).glob("*.srt"))
                sub_files = vtt_files + srt_files

                if sub_files:
                    raw = sub_files[0].read_text(encoding="utf-8", errors="ignore")
                    cleaned = _clean_subtitle(raw)
                    if cleaned.strip():
                        logger.info(f"[YouTubeHandler] 成功取得字幕（{lang}）：{len(cleaned)} 字")
                        return cleaned

            logger.warning(f"[YouTubeHandler] 找不到任何字幕：{url}")
            return None

    except subprocess.TimeoutExpired:
        logger.error("[YouTubeHandler] yt-dlp 超時")
        return None
    except Exception as e:
        logger.error(f"[YouTubeHandler] 錯誤：{e}")
        return None


def _clean_subtitle(raw: str) -> str:
    """清除字幕時間戳記和標籤，只保留純文字"""
    # 移除 VTT 標頭
    raw = re.sub(r"WEBVTT.*?\n\n", "", raw, flags=re.DOTALL)
    # 移除時間戳記行（00:00:00.000 --> 00:00:00.000）
    raw = re.sub(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*?\n", "", raw)
    # 移除 SRT 序號
    raw = re.sub(r"^\d+\s*\n", "", raw, flags=re.MULTILINE)
    # 移除 HTML 標籤
    raw = re.sub(r"<[^>]+>", "", raw)
    # 移除空行和重複行
    lines = []
    seen = set()
    for line in raw.splitlines():
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return " ".join(lines)


def get_video_info(url: str) -> dict:
    """取得影片基本資訊（標題、時長）"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="ignore"
        )
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            return {
                "title":    info.get("title", "未知標題"),
                "duration": info.get("duration_string", "未知時長"),
                "uploader": info.get("uploader", "未知頻道"),
            }
    except Exception:
        pass
    return {}


if __name__ == "__main__":
    # 測試
    test_url = input("輸入 YouTube URL：").strip()
    transcript = get_transcript(test_url)
    if transcript:
        print(f"字幕（前 300 字）：\n{transcript[:300]}")
    else:
        print("無法取得字幕")
