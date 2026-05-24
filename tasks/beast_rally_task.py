import log_util
from task_helpers.constants import MARCH_SAME_TARGET
from task_helpers.formation import _select_next_formation
from task_helpers.march import _click_march
from task_helpers.march_queue import _should_skip_for_active_marches
from task_helpers.navigation import (
    _click_search_button,
    _ensure_game_open,
    _ensure_wild,
    _open_search_panel,
    _reset_search_category_to_first,
    _return_home_or_wild,
    _set_search_level,
)
from task_helpers.params import _bool_param, _formation_indices_param, _int_param
from task_helpers.screen import (
    _asset,
    _click_base,
    _click_templates,
    _region_from_ratio,
    _sleep_while_running,
    _wait_templates,
)
from task_runtime import register_task


def _select_beast_category(executor):
    _reset_search_category_to_first(executor)
    if _click_templates(
        executor,
        [_asset("beast_category.png")],
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.0, 0.62, 0.55, 0.82),
        wait_seconds=0.4,
    ):
        return
    _click_base(executor, 157, 584, wait_seconds=0.4)


def _search_beast_once(executor, level, attempt, max_attempts):
    if not executor.run_status:
        return False
    if not _open_search_panel(executor):
        path = executor.emulator_executor.save_debug_screenshot("search_panel_not_found")
        log_util.log.print(f"[{executor.emulator_name}] 未能打开搜索面板，截图: {path}")
        return False

    _select_beast_category(executor)
    _set_search_level(executor, level)
    log_util.log.print(f"[{executor.emulator_name}] 搜索 {level} 级冰原巨兽，第 {attempt}/{max_attempts} 次")
    _click_search_button(executor)

    _, _, rally_found = _wait_templates(
        executor,
        [_asset("rally_button.png")],
        timeout=4,
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.20, 0.22, 0.80, 0.48),
    )
    if rally_found:
        return True

    if _click_templates(executor, [_asset("ok_button.png"), _asset("confirm_button.png")], threshold=0.76):
        pass
    return False


def _search_beast(executor, level, max_attempts, retry_interval):
    for attempt in range(1, max_attempts + 1):
        if _search_beast_once(executor, level, attempt, max_attempts):
            return True
        if attempt < max_attempts:
            log_util.log.print(f"[{executor.emulator_name}] 未找到可集结目标，{retry_interval} 秒后重试")
            _sleep_while_running(executor, retry_interval)

    log_util.log.print(f"[{executor.emulator_name}] 未找到 {level} 级冰原巨兽，结束本轮")
    _return_home_or_wild(executor)
    return False


def _choose_rally_duration(executor, duration_minutes):
    duration_positions = {
        5: (81, 373),
        15: (248, 373),
        30: (81, 421),
        60: (248, 421),
    }
    if duration_minutes not in duration_positions:
        log_util.log.print(f"[{executor.emulator_name}] 不支持 {duration_minutes} 分钟集结时长，改用 5 分钟")
        duration_minutes = 5

    _click_base(executor, *duration_positions[duration_minutes], wait_seconds=0.3)


def _start_rally_and_open_formation(executor, duration_minutes):
    if not _click_templates(
        executor,
        [_asset("rally_button.png")],
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.20, 0.22, 0.80, 0.48),
        wait_seconds=1.0,
    ):
        path = executor.emulator_executor.save_debug_screenshot("rally_button_not_found")
        log_util.log.print(f"[{executor.emulator_name}] 未找到集结按钮，截图: {path}")
        return False

    _, _, dialog_found = _wait_templates(
        executor,
        [_asset("start_rally_button.png"), _asset("close_x.png")],
        timeout=4,
        threshold=0.74,
    )
    if not dialog_found:
        path = executor.emulator_executor.save_debug_screenshot("rally_duration_dialog_not_found")
        log_util.log.print(f"[{executor.emulator_name}] 未找到集结时长弹窗，截图: {path}")
        return False

    _choose_rally_duration(executor, duration_minutes)
    if not _click_templates(
        executor,
        [_asset("start_rally_button.png")],
        threshold=0.74,
        region=_region_from_ratio(executor.emulator_executor, 0.20, 0.55, 0.80, 0.75),
        wait_seconds=1.2,
    ):
        _click_base(executor, 226, 523, wait_seconds=1.2)

    _, _, formation_found = _wait_templates(
        executor,
        [_asset("march_button.png"), _asset("formation_anchor.png")],
        timeout=6,
        threshold=0.74,
    )
    if not formation_found:
        path = executor.emulator_executor.save_debug_screenshot("formation_not_found")
        log_util.log.print(f"[{executor.emulator_name}] 未进入编队页面，截图: {path}")
        return False
    return True


@register_task("自动集结冰原巨兽", param_defs=[
    {"name": "beast_level", "type": "int", "default": 1, "desc": "冰原巨兽等级"},
    {"name": "formation_index", "type": "int", "default": 1, "desc": "编队编号(1-8)"},
    {"name": "formation_indices", "type": "str", "default": "", "desc": "编队列表(逗号分隔，空则使用编队编号)"},
    {"name": "require_hero_for_march", "type": "bool", "default": True, "desc": "当前编队有英雄才出征"},
    {"name": "rally_duration_minutes", "type": "int", "default": 5, "desc": "集结时长/分钟(5/15/30/60)"},
    {"name": "max_search_attempts", "type": "int", "default": 1, "desc": "本轮搜索次数"},
    {"name": "search_retry_interval_sec", "type": "int", "default": 3, "desc": "搜索重试间隔/秒"},
    {"name": "use_stamina_can", "type": "bool", "default": False, "desc": "体力不足是否使用背包体力罐头"},
    {"name": "stamina_can_reserve_count", "type": "int", "default": 0, "desc": "背包体力罐头保留数量"},
    {"name": "use_diamond_for_stamina", "type": "bool", "default": False, "desc": "体力不足是否允许钻石购买"},
], initial_state="wild")
def rally_icefield_beast(executor, params):
    level = _int_param(params, "beast_level", 1, minimum=1)
    formation_indices = _formation_indices_param(params)
    require_hero_for_march = _bool_param(params, "require_hero_for_march", True)
    duration_minutes = _int_param(params, "rally_duration_minutes", 5, minimum=1)
    max_attempts = _int_param(params, "max_search_attempts", 1, minimum=1)
    retry_interval = _int_param(params, "search_retry_interval_sec", 3, minimum=0)
    use_stamina_can = _bool_param(params, "use_stamina_can", False)
    stamina_can_reserve_count = _int_param(params, "stamina_can_reserve_count", 0, minimum=0)
    use_diamond_for_stamina = _bool_param(params, "use_diamond_for_stamina", False)

    log_util.log.print(
        f"[{executor.emulator_name}] 开始自动集结冰原巨兽: 等级={level}, 编队={formation_indices}, "
        f"时长={duration_minutes}分钟, 搜索次数={max_attempts}, 使用背包体力罐头={use_stamina_can}, "
        f"罐头保留数量={stamina_can_reserve_count}, 允许钻石购买={use_diamond_for_stamina}, "
        f"有英雄才出征={require_hero_for_march}"
    )

    if not _ensure_game_open(executor):
        return False
    if not _ensure_wild(executor):
        return False
    if _should_skip_for_active_marches(executor, formation_indices):
        return True

    attempt = 1
    same_target_retries = 0
    same_target_retry_limit = max_attempts
    while attempt <= max_attempts:
        if not _search_beast_once(executor, level, attempt, max_attempts):
            if attempt < max_attempts:
                log_util.log.print(f"[{executor.emulator_name}] 未找到可集结目标，{retry_interval} 秒后重试")
                _sleep_while_running(executor, retry_interval)
                attempt += 1
                continue
            log_util.log.print(f"[{executor.emulator_name}] 未找到 {level} 级冰原巨兽，结束本轮")
            _return_home_or_wild(executor)
            return False

        if not _start_rally_and_open_formation(executor, duration_minutes):
            _return_home_or_wild(executor)
            return False

        selected_formation = _select_next_formation(executor, formation_indices, require_hero_for_march)
        if selected_formation is None:
            _return_home_or_wild(executor)
            return True

        march_result = _click_march(
            executor,
            use_stamina_can=use_stamina_can,
            stamina_can_reserve_count=stamina_can_reserve_count,
            use_diamond_for_stamina=use_diamond_for_stamina,
        )
        if march_result == MARCH_SAME_TARGET:
            if same_target_retries < same_target_retry_limit:
                same_target_retries += 1
                log_util.log.print(
                    f"[{executor.emulator_name}] 当前巨兽已有其他队伍出征，"
                    f"{retry_interval} 秒后重新寻找({same_target_retries}/{same_target_retry_limit})"
                )
                _sleep_while_running(executor, retry_interval)
                continue
            log_util.log.print(f"[{executor.emulator_name}] 当前巨兽已有其他队伍出征，已达到同目标重搜次数，结束本轮")
            return False
        return march_result

    return False
