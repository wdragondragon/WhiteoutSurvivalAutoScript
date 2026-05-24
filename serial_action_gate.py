import threading
import time


class SerialActionGate:
    def __init__(self, enabled=False, interval_sec=1.0):
        self.enabled = bool(enabled)
        self.interval_sec = max(0.0, float(interval_sec or 0.0))
        self._lock = threading.Lock()
        self._last_action_at = 0.0

    def wait_before_action(self, emulator_name=None, action_name=None):
        if not self.enabled or self.interval_sec <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait_seconds = self.interval_sec - (now - self._last_action_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_action_at = time.monotonic()
