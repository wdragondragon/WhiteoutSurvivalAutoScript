import time

import log_util
from task_helpers.screen import (
    _asset,
    _click_base,
    _click_templates,
    _find_templates,
    _region_from_ratio,
    _sleep_while_running,
    _swipe_base,
    _wait_templates,
)


def _is_wild_visible(executor):
    emulator = executor.emulator_executor
    search_region = _region_from_ratio(emulator, 0.0, 0.60, 0.18, 0.75)
    _, _, search_icon = _find_templates(
        executor,
        [_asset("search_icon.png")],
        threshold=0.58,
        region=search_region,
    )
    return search_icon


def _is_wild_or_search_visible(executor):
    if _is_wild_visible(executor):
        return True

    emulator = executor.emulator_executor
    bottom_region = _region_from_ratio(emulator, 0.0, 0.62, 1.0, 1.0)
    _, _, search_panel = _find_templates(
        executor,
        [_asset("search_button.png"), _asset("beast_category.png")],
        threshold=0.76,
        region=bottom_region,
    )
    return search_panel


def _is_search_panel_visible(executor):
    bottom_region = _region_from_ratio(executor.emulator_executor, 0.0, 0.62, 1.0, 1.0)
    _, _, found = _find_templates(
        executor,
        [_asset("search_button.png"), _asset("beast_category.png")],
        threshold=0.76,
        region=bottom_region,
    )
    return found


def _is_exit_confirm_visible(executor):
    _, _, found = _find_templates(
        executor,
        [_asset("exit_confirm_title.png"), _asset("cancel_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.05, 0.25, 0.95, 0.72),
    )
    return found


def _cancel_exit_confirm(executor):
    if not _is_exit_confirm_visible(executor):
        return False
    log_util.log.print(f"[{executor.emulator_name}] 检测到退出确认弹窗，点击取消")
    if not _click_templates(
        executor,
        [_asset("cancel_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.05, 0.52, 0.50, 0.72),
        wait_seconds=0.8,
    ):
        _click_base(executor, 130, 493, wait_seconds=0.8)
    return True


def _click_city_wild_button(executor):
    return _click_templates(
        executor,
        [_asset("city_wild_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.78, 0.84, 1.0, 1.0),
        wait_seconds=1.2,
    )


def _clear_known_overlays(executor, max_rounds=6):
    close_templates = [
        _asset("close_x.png"),
        _asset("stamina_close_x.png"),
        _asset("dialog_close.png"),
        _asset("ok_button.png"),
        _asset("confirm_button.png"),
        _asset("cancel_button.png"),
        "buttons/back.png",
        "buttons/back2.png",
        "buttons/back3.png",
    ]

    for _ in range(max_rounds):
        if not executor.run_status:
            return False
        if _cancel_exit_confirm(executor):
            continue
        if _is_wild_visible(executor):
            return True
        if _click_templates(executor, ["buttons/relogin.png"], threshold=0.78, wait_seconds=3.0):
            continue
        if _click_templates(executor, close_templates, threshold=0.76, wait_seconds=0.8):
            continue
        return False
    return _is_wild_or_search_visible(executor)


def _return_home_or_wild(executor):
    emulator = executor.emulator_executor
    back_templates = [
        _asset("back_arrow.png"),
        _asset("close_x.png"),
        _asset("stamina_close_x.png"),
        _asset("cancel_button.png"),
        "buttons/back.png",
        "buttons/back2.png",
        "buttons/back3.png",
    ]

    for _ in range(8):
        if not executor.run_status:
            return False
        if _cancel_exit_confirm(executor):
            continue
        if _is_wild_visible(executor):
            return True
        if _click_city_wild_button(executor):
            if _is_wild_visible(executor):
                return True
            continue
        if _click_templates(executor, back_templates, threshold=0.74, wait_seconds=0.8):
            continue
        if not _is_exit_confirm_visible(executor):
            emulator.press_back()
        _sleep_while_running(executor, 0.8)

    if not _click_city_wild_button(executor):
        _click_base(executor, 416, 758, wait_seconds=1.2)
    return _is_wild_visible(executor)


def _ensure_game_open(executor):
    emulator = executor.emulator_executor
    x, y, found = emulator.find_img("buttons/button1.png", threshold=0.76, log_missing=False)
    if not found:
        return True

    log_util.log.print(f"[{executor.emulator_name}] 识别到游戏未打开，打开游戏")
    emulator.click(x, y)
    end_time = time.time() + 70
    while executor.run_status and time.time() < end_time:
        _, _, icon_still_visible = emulator.find_img("buttons/button1.png", threshold=0.76, log_missing=False)
        if not icon_still_visible:
            return True
        time.sleep(1)
    path = emulator.save_debug_screenshot("open_game_timeout")
    log_util.log.print(f"[{executor.emulator_name}] 等待游戏打开超时，截图: {path}")
    return False


def _ensure_wild(executor):
    if _is_wild_or_search_visible(executor):
        return True

    if _clear_known_overlays(executor) and _is_wild_or_search_visible(executor):
        return True

    if _return_home_or_wild(executor):
        return True

    path = executor.emulator_executor.save_debug_screenshot("wild_not_found")
    log_util.log.print(f"[{executor.emulator_name}] 未能确认野外页面，截图: {path}")
    return False


def _open_search_panel(executor):
    if _is_search_panel_visible(executor):
        return True

    search_region = _region_from_ratio(executor.emulator_executor, 0.0, 0.60, 0.18, 0.75)
    if not _click_templates(
        executor,
        [_asset("search_icon.png")],
        threshold=0.58,
        region=search_region,
        wait_seconds=0.8,
    ):
        _click_base(executor, 27, 548, wait_seconds=0.8)

    _, _, visible = _wait_templates(
        executor,
        [_asset("search_button.png"), _asset("beast_category.png")],
        timeout=4,
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.0, 0.62, 1.0, 1.0),
    )
    return visible


def _reset_search_category_to_first(executor):
    for _ in range(3):
        _swipe_base(executor, 120, 580, 420, 580, duration_ms=260, wait_seconds=0.25)


def _set_search_level(executor, level):
    _click_base(executor, 380, 660, wait_seconds=0.3)
    executor.emulator_executor.clear_text(count=4)
    executor.emulator_executor.input_text(str(level))
    _sleep_while_running(executor, 0.2)
    _click_base(executor, 388, 760, wait_seconds=0.5)


def _click_search_button(executor):
    if _click_templates(
        executor,
        [_asset("search_button.png")],
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.20, 0.88, 0.80, 1.0),
        wait_seconds=1.2,
    ):
        return True
    _click_base(executor, 225, 758, wait_seconds=1.2)
    return True
