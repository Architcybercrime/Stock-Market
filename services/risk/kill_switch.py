"""Kill switch: stop all new orders, regardless of strategy or risk.

Two activation paths:
1. File-based: presence of `KILL_SWITCH` file in the data root. Survives
   restarts; ops can stop trading without code access.
2. In-process: programmatic via .engage()/.release(). Useful for tests and
   for the API endpoint.

Both are checked on every order submission — never cached.
"""

from __future__ import annotations

from pathlib import Path

from libs.common.logging import get_logger

log = get_logger(__name__)


class KillSwitch:
    def __init__(self, kill_file: Path) -> None:
        self.kill_file = Path(kill_file)
        self._in_process: bool = False
        self._reason: str = ""

    def is_engaged(self) -> bool:
        return self._in_process or self.kill_file.exists()

    def engage(self, reason: str, actor: str = "system") -> None:
        self._in_process = True
        self._reason = reason
        try:
            self.kill_file.parent.mkdir(parents=True, exist_ok=True)
            self.kill_file.write_text(f"{actor}: {reason}\n")
        except Exception as exc:
            log.error("kill_switch.write_failed", exc_info=exc)
        log.critical("kill_switch.engaged", actor=actor, reason=reason)

    def release(self, actor: str = "system") -> None:
        self._in_process = False
        try:
            if self.kill_file.exists():
                self.kill_file.unlink()
        except Exception as exc:
            log.error("kill_switch.release_failed", exc_info=exc)
        log.warning("kill_switch.released", actor=actor)

    @property
    def reason(self) -> str:
        if self._reason:
            return self._reason
        if self.kill_file.exists():
            try:
                return self.kill_file.read_text().strip()
            except Exception:
                return "unknown"
        return ""
