import log_util
from task_helpers.constants import MARCH_SAME_TARGET
from task_helpers.formation import _is_formation_visible
from task_helpers.navigation import _is_wild_visible, _return_home_or_wild
from task_helpers.screen import (
    _asset,
    _click_base,
    _click_templates,
    _find_templates,
    _region_from_ratio,
    _sleep_while_running,
)
from task_helpers.stamina import (
    _handle_stamina_shortage,
    _is_stamina_dialog_visible,
    _looks_like_modal_dialog,
)


def _is_same_target_prompt_visible(executor):
    _, _, found = _find_templates(
        executor,
        [_asset("same_target_prompt.png")],
        threshold=0.78,
        region=_region_from_ratio(executor.emulator_executor, 0.08, 0.34, 0.92, 0.56),
    )
    return found


def _cancel_same_target_prompt(executor):
    log_util.log.print(f"[{executor.emulator_name}] 检测到同目标出征提示，取消当前目标并重新寻找")
    if not _click_templates(
        executor,
        [_asset("cancel_button.png")],
        threshold=0.78,
        region=_region_from_ratio(executor.emulator_executor, 0.06, 0.54, 0.50, 0.70),
        wait_seconds=1.0,
    ):
        _click_base(executor, 130, 493, wait_seconds=1.0)
    return True


def _wait_after_march(
        executor,
        use_stamina_can,
        stamina_can_reserve_count,
        use_diamond_for_stamina,
        stamina_retry_count,
):
    _sleep_while_running(executor, 2.0)
    if _is_wild_visible(executor):
        log_util.log.print(f"[{executor.emulator_name}] 已出征并返回野外")
        return True

    if _is_same_target_prompt_visible(executor):
        _cancel_same_target_prompt(executor)
        _return_home_or_wild(executor)
        return MARCH_SAME_TARGET

    stamina_dialog_visible = _is_stamina_dialog_visible(executor) or _looks_like_modal_dialog(executor)
    if stamina_dialog_visible and stamina_retry_count >= 6:
        path = executor.emulator_executor.save_debug_screenshot("stamina_retry_limit")
        log_util.log.print(f"[{executor.emulator_name}] 已多次处理体力不足仍无法出征，截图: {path}")
        _return_home_or_wild(executor)
        return False

    if stamina_dialog_visible:
        handled = _handle_stamina_shortage(
            executor,
            use_stamina_can,
            stamina_can_reserve_count,
            use_diamond_for_stamina,
            try_free_stamina=stamina_retry_count == 0,
        )
        if not handled:
            return False
        if not _is_formation_visible(executor):
            _sleep_while_running(executor, 1.0)
        if _is_formation_visible(executor):
            return _click_march(
                executor,
                use_stamina_can,
                stamina_can_reserve_count,
                use_diamond_for_stamina,
                stamina_retry_count=stamina_retry_count + 1,
            )
        if _is_wild_visible(executor):
            return True

    if _is_formation_visible(executor):
        path = executor.emulator_executor.save_debug_screenshot("march_still_on_formation")
        log_util.log.print(f"[{executor.emulator_name}] 点击出征后仍停留在编队页，截图: {path}")
        return False

    if _is_wild_visible(executor):
        return True

    path = executor.emulator_executor.save_debug_screenshot("march_unknown_result")
    log_util.log.print(f"[{executor.emulator_name}] 出征结果未确认，截图: {path}")
    return False


def _click_march(
        executor,
        use_stamina_can=False,
        stamina_can_reserve_count=0,
        use_diamond_for_stamina=False,
        stamina_retry_count=0,
):
    if not _click_templates(
        executor,
        [_asset("march_button.png")],
        threshold=0.74,
        region=_region_from_ratio(executor.emulator_executor, 0.50, 0.86, 1.0, 1.0),
        wait_seconds=1.0,
    ):
        _click_base(executor, 343, 758, wait_seconds=1.0)
    log_util.log.print(f"[{executor.emulator_name}] 已点击出征")
    return _wait_after_march(
        executor,
        use_stamina_can,
        stamina_can_reserve_count,
        use_diamond_for_stamina,
        stamina_retry_count,
    )
