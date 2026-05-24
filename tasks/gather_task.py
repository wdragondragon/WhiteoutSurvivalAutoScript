import log_util
from task_helpers.constants import GATHER_RESOURCE_CONFIG, GATHER_RESOURCE_OPTIONS, MARCH_SAME_TARGET
from task_helpers.formation import (
    _first_gather_hero_present,
    _keep_only_blue_gather_heroes,
)
from task_helpers.march import _click_march
from task_helpers.march_queue import _should_skip_for_active_limit
from task_helpers.navigation import (
    _click_search_button,
    _ensure_game_open,
    _ensure_wild,
    _open_search_panel,
    _return_home_or_wild,
    _set_search_level,
)
from task_helpers.params import (
    _bool_param,
    _gather_queue_configs,
    _int_param,
    _next_gather_queue,
)
from task_helpers.screen import (
    _asset,
    _click_base,
    _click_templates,
    _existing_templates,
    _find_templates,
    _gather_asset,
    _region_from_ratio,
    _sleep_while_running,
    _wait_templates,
)
from task_runtime import register_task


def _select_gather_resource_category(executor, resource_type):
    config = GATHER_RESOURCE_CONFIG.get(resource_type)
    if not config:
        return False

    templates = [_gather_asset(asset_name) for asset_name in config["category_assets"]]
    if _click_templates(
        executor,
        templates,
        threshold=0.74,
        region=_region_from_ratio(executor.emulator_executor, 0.0, 0.58, 1.0, 0.84),
        wait_seconds=0.4,
    ):
        return True

    x, y = config["fallback"]
    log_util.log.print(f"[{executor.emulator_name}] 未找到 {config['label']} 搜索入口模板，使用预设坐标")
    _click_base(executor, x, y, wait_seconds=0.4)
    return True


def _set_full_resource_only(executor, enabled):
    if not enabled:
        return True

    checked_templates = [
        _gather_asset("full_resource_checked.png"),
        _gather_asset("full_resource_switch_on.png"),
    ]
    unchecked_templates = [
        _gather_asset("full_resource_unchecked.png"),
        _gather_asset("full_resource_switch_off.png"),
    ]
    full_region = _region_from_ratio(executor.emulator_executor, 0.05, 0.66, 0.72, 0.88)

    _, _, already_enabled = _find_templates(executor, checked_templates, threshold=0.72, region=full_region)
    if already_enabled:
        return True

    if _click_templates(executor, unchecked_templates, threshold=0.72, region=full_region, wait_seconds=0.2):
        return True

    path = executor.emulator_executor.save_debug_screenshot("full_resource_filter_not_found")
    log_util.log.print(f"[{executor.emulator_name}] 未能确认满资源筛选控件，截图: {path}")
    return False


def _search_gather_resource_once(executor, queue, attempt, max_attempts):
    resource_type = queue["resource_type"]
    config = GATHER_RESOURCE_CONFIG[resource_type]
    if not executor.run_status:
        return False
    if not _open_search_panel(executor):
        path = executor.emulator_executor.save_debug_screenshot("gather_search_panel_not_found")
        log_util.log.print(f"[{executor.emulator_name}] 未能打开资源搜索面板，截图: {path}")
        return False

    _select_gather_resource_category(executor, resource_type)
    if config["has_level"]:
        _set_search_level(executor, queue["level"])
        level_text = f"{queue['level']}级"
    else:
        level_text = "联盟矿"

    if not _set_full_resource_only(executor, queue["full_only"]):
        return False

    log_util.log.print(
        f"[{executor.emulator_name}] 搜索采集资源: 队列={queue['queue_index']}, "
        f"类型={resource_type}, 等级={level_text}, 只找满资源={queue['full_only']}, "
        f"第 {attempt}/{max_attempts} 次"
    )
    _click_search_button(executor)

    gather_templates = [
        _gather_asset("gather_button.png"),
        _gather_asset("collect_button.png"),
        _gather_asset("occupy_button.png"),
    ]
    if not _existing_templates(gather_templates):
        _sleep_while_running(executor, 1.5)
        return True

    _, _, gather_found = _wait_templates(
        executor,
        gather_templates,
        timeout=4,
        threshold=0.74,
        region=_region_from_ratio(executor.emulator_executor, 0.18, 0.20, 0.84, 0.54),
    )
    if gather_found:
        return True

    if _click_templates(executor, [_asset("ok_button.png"), _asset("confirm_button.png")], threshold=0.76):
        pass
    return False


def _open_gather_formation(executor):
    clicked = _click_templates(
        executor,
        [_gather_asset("gather_button.png"), _gather_asset("collect_button.png"), _gather_asset("occupy_button.png")],
        threshold=0.74,
        region=_region_from_ratio(executor.emulator_executor, 0.18, 0.20, 0.84, 0.54),
        wait_seconds=1.2,
    )
    if not clicked:
        log_util.log.print(f"[{executor.emulator_name}] 未找到采集按钮模板，尝试使用预设坐标")
        _click_base(executor, 225, 352, wait_seconds=1.2)

    _, _, formation_found = _wait_templates(
        executor,
        [_asset("march_button.png"), _asset("formation_anchor.png")],
        timeout=6,
        threshold=0.74,
    )
    if not formation_found:
        path = executor.emulator_executor.save_debug_screenshot("gather_formation_not_found")
        log_util.log.print(f"[{executor.emulator_name}] 未进入采集编队页面，截图: {path}")
        return False
    return True


def _build_gather_param_defs():
    param_defs = [
        {"name": "max_search_attempts", "type": "int", "default": 1, "desc": "每个队列常规搜索次数"},
        {"name": "search_retry_interval_sec", "type": "int", "default": 3, "desc": "搜索重试间隔/秒"},
        {"name": "keep_only_blue_gather_heroes", "type": "bool", "default": True, "desc": "只保留蓝色挖矿英雄"},
        {"name": "require_first_hero_for_gather", "type": "bool", "default": True, "desc": "首英雄有英雄才出征"},
    ]
    for index in range(1, 7):
        param_defs.extend([
            {"name": f"queue{index}_enabled", "type": "bool", "default": index == 1, "desc": f"队列{index}启用"},
            {
                "name": f"queue{index}_resource_type",
                "type": "choice",
                "default": "生肉",
                "options": GATHER_RESOURCE_OPTIONS,
                "desc": f"队列{index}资源类型",
            },
            {"name": f"queue{index}_resource_level", "type": "int", "default": 1, "desc": f"队列{index}资源等级(联盟矿忽略)"},
            {"name": f"queue{index}_full_only", "type": "bool", "default": False, "desc": f"队列{index}只搜索满资源"},
        ])
    return param_defs


@register_task("自动挖矿", param_defs=_build_gather_param_defs(), initial_state="wild")
def auto_gather_resources(executor, params):
    queues = _gather_queue_configs(params)
    max_attempts = _int_param(params, "max_search_attempts", 1, minimum=1)
    retry_interval = _int_param(params, "search_retry_interval_sec", 3, minimum=0)
    keep_only_blue_heroes = _bool_param(params, "keep_only_blue_gather_heroes", True)
    require_first_hero = _bool_param(params, "require_first_hero_for_gather", True)

    if not queues:
        log_util.log.print(f"[{executor.emulator_name}] 自动挖矿未配置启用队列，跳过")
        return True

    log_util.log.print(
        f"[{executor.emulator_name}] 开始自动挖矿: 队列数={len(queues)}, 搜索次数={max_attempts}, "
        f"只保留蓝色英雄={keep_only_blue_heroes}, 首英雄必需={require_first_hero}"
    )

    if not _ensure_game_open(executor):
        return False
    if not _ensure_wild(executor):
        return False
    if _should_skip_for_active_limit(executor, len(queues), "挖矿", queue_type="gather"):
        return True

    queue = _next_gather_queue(executor, queues)
    if not queue:
        return True

    attempt = 1
    same_target_retries = 0
    same_target_retry_limit = max_attempts
    while attempt <= max_attempts:
        if not _search_gather_resource_once(executor, queue, attempt, max_attempts):
            if attempt < max_attempts:
                log_util.log.print(f"[{executor.emulator_name}] 未找到采集资源点，{retry_interval} 秒后重试")
                _sleep_while_running(executor, retry_interval)
                attempt += 1
                continue
            log_util.log.print(f"[{executor.emulator_name}] 未找到可采集资源点，结束本轮")
            _return_home_or_wild(executor)
            return False

        if not _open_gather_formation(executor):
            _return_home_or_wild(executor)
            if attempt < max_attempts:
                log_util.log.print(f"[{executor.emulator_name}] 未进入采集编队页，{retry_interval} 秒后重新搜索")
                _sleep_while_running(executor, retry_interval)
                attempt += 1
                continue
            return False

        if keep_only_blue_heroes:
            _keep_only_blue_gather_heroes(executor)

        if require_first_hero and not _first_gather_hero_present(executor):
            log_util.log.print(f"[{executor.emulator_name}] 采集首英雄未识别到英雄，取消本轮出征")
            _return_home_or_wild(executor)
            return True

        march_result = _click_march(executor)
        if march_result == MARCH_SAME_TARGET:
            if same_target_retries < same_target_retry_limit:
                same_target_retries += 1
                log_util.log.print(
                    f"[{executor.emulator_name}] 当前资源点已有其他队伍出征，"
                    f"{retry_interval} 秒后重新寻找({same_target_retries}/{same_target_retry_limit})"
                )
                _sleep_while_running(executor, retry_interval)
                continue
            log_util.log.print(f"[{executor.emulator_name}] 当前资源点已有其他队伍出征，已达到同目标重搜次数，结束本轮")
            return False
        return march_result

    return False
