"""
health_monitor.py
系統健康監控工具 - 基本架構與核心模組
採集、評估、輸出三層分離設計
"""
import platform
import psutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
# ── 標準資料格式 ──────────────────────────────────────────
@dataclass
class HealthSnapshot:
    """系統健康快照的標準資料格式,各層之間統一使用此型別傳遞"""
    timestamp: str
    metrics: dict[str, Any] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)
# ── 主要監控類別 ──────────────────────────────────────────
class HealthMonitor:
    """
    系統健康監控器骨架
    - init 載入設定、暖身 CPU 採集、自動偵測磁碟路徑
    - 採集函式只回傳 dict,不做任何輸出或儲存
    - evaluate_alerts 負責比對門檻產生警報訊息
    """
    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化監控器
        載入門檻設定,並執行 cpu_percent 暖身避免第一次回傳 0.0
        """
    ...(已截斷)