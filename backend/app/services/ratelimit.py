"""登录限流（内存实现）。

用于阻断口令暴力破解：同一 IP + 用户名组合在窗口内失败次数超限后暂时拒绝。
单进程内存实现，多实例部署时应替换为 Redis 计数器。
"""
import time
from collections import defaultdict

WINDOW_SECONDS = 300      # 统计窗口 5 分钟
MAX_FAILURES = 5          # 窗口内允许的失败次数
LOCK_SECONDS = 300        # 超限后的锁定时长

_failures: dict[str, list[float]] = defaultdict(list)


def _key(ip: str, username: str) -> str:
    return f"{ip}|{(username or '').lower()}"


def is_locked(ip: str, username: str) -> tuple[bool, int]:
    """返回 (是否锁定, 剩余秒数)。"""
    k = _key(ip, username)
    now = time.time()
    stamps = [t for t in _failures.get(k, []) if now - t < WINDOW_SECONDS]
    _failures[k] = stamps
    if len(stamps) < MAX_FAILURES:
        return False, 0
    remaining = int(LOCK_SECONDS - (now - stamps[-1]))
    if remaining <= 0:
        _failures.pop(k, None)
        return False, 0
    return True, remaining


def record_failure(ip: str, username: str) -> int:
    """记录一次失败，返回窗口内累计失败次数。"""
    k = _key(ip, username)
    now = time.time()
    _failures[k].append(now)
    _failures[k] = [t for t in _failures[k] if now - t < WINDOW_SECONDS]
    return len(_failures[k])


def clear(ip: str, username: str) -> None:
    _failures.pop(_key(ip, username), None)
