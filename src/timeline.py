"""
轻量级调用链时序追踪器
记录每个阶段的耗时，在响应中返回，无需 Prometheus/Grafana
"""
import time
from typing import List, Dict, Any


class Timeline:
    """调用链时序追踪"""

    def __init__(self):
        self._marks: List[Dict[str, Any]] = []
        self._start()

    def _start(self):
        self._marks.append({
            "phase": "start",
            "timestamp": time.time(),
            "elapsed": 0.0,
        })

    def mark(self, phase: str):
        """记录一个时间点"""
        now = time.time()
        elapsed = now - self._marks[0]["timestamp"]
        last = self._marks[-1]["timestamp"]
        since_last = now - last
        self._marks.append({
            "phase": phase,
            "timestamp": now,
            "elapsed": round(elapsed, 3),
            "since_last": round(since_last, 3),
        })

    def report(self) -> List[Dict[str, Any]]:
        """获取时序报告"""
        return [{"phase": m["phase"], "elapsed_s": m.get("elapsed", 0),
                 "since_last_s": m.get("since_last", 0)} for m in self._marks]

    def total(self) -> float:
        """总耗时"""
        if len(self._marks) < 2:
            return 0.0
        return round(self._marks[-1]["timestamp"] - self._marks[0]["timestamp"], 3)

    def summary(self) -> str:
        """简要摘要"""
        parts = []
        for m in self._marks[1:]:
            phase = m["phase"]
            sl = m.get("since_last", 0)
            if sl > 0.1:
                parts.append(f"{phase}={sl:.1f}s")
        total = self.total()
        parts.append(f"total={total:.1f}s")
        return " | ".join(parts)
