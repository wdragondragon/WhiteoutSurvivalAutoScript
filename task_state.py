import time

import log_util
from task_helpers.navigation import (
    _cancel_exit_confirm,
    _ensure_game_open,
    _ensure_wild,
)


def prepare_task_state(executor, initial_state):
    initial_state = initial_state or "wild"
    if initial_state == "any":
        return True
    if initial_state == "wild":
        return _ensure_game_open(executor) and _ensure_wild(executor)
    if initial_state == "home":
        return _ensure_home(executor)
    if initial_state == "manual":
        key = f"manual_initial_state_logged:{executor.current_task_name}"
        if not executor.state.get(key):
            log_util.log.print(f"[{executor.emulator_name}] 任务 {executor.current_task_name} 需要用户预先进入可识别页面")
            executor.state[key] = True
        return True

    log_util.log.print(f"[{executor.emulator_name}] 未知初始页面状态 {initial_state}，按野外页处理")
    return _ensure_game_open(executor) and _ensure_wild(executor)


def _ensure_home(executor):
    if not _ensure_game_open(executor):
        return False

    back_image_path = [
        "buttons/back.png",
        "buttons/back2.png",
        "buttons/back3.png",
        "buttons/back4.png",
        "buttons/back5.png",
    ]
    for _ in range(10):
        if not executor.run_status:
            return False
        if _cancel_exit_confirm(executor):
            continue
        x, y, found = executor.emulator_executor.find_img(back_image_path, log_missing=False)
        if not found:
            return True
        log_util.log.print(f"[{executor.emulator_name}] 恢复任务初始状态：点击返回")
        executor.emulator_executor.click(x, y)
        time.sleep(0.5)
    return True
