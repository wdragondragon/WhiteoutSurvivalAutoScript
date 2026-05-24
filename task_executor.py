import os
import time

import cv2
import numpy as np

import log_util
from emulator_executor import EmulatorExecutor

TASK_REGISTRY = {}

BEAST_RALLY_ASSET_DIR = os.path.join("buttons", "beast_rally")
GATHER_ASSET_DIR = os.path.join("buttons", "gather")
MARCH_QUEUE_ASSET_DIR = os.path.join("buttons", "march_queue")
BASE_SCREEN_WIDTH = 450
BASE_SCREEN_HEIGHT = 800
MARCH_SAME_TARGET = "same_target"
MAX_ACTIVE_MARCHES = 6

GATHER_RESOURCE_OPTIONS = [
    "生肉",
    "木材",
    "煤矿",
    "铁矿",
    "联盟生肉",
    "联盟木材",
    "联盟煤矿",
    "联盟铁矿",
]

GATHER_RESOURCE_ALIASES = {
    "肉": "生肉",
    "粮食": "生肉",
    "meat": "生肉",
    "food": "生肉",
    "wood": "木材",
    "coal": "煤矿",
    "iron": "铁矿",
    "联盟肉": "联盟生肉",
    "联盟粮食": "联盟生肉",
    "联盟meat": "联盟生肉",
    "联盟food": "联盟生肉",
    "联盟wood": "联盟木材",
    "联盟coal": "联盟煤矿",
    "联盟iron": "联盟铁矿",
}

GATHER_RESOURCE_CONFIG = {
    "生肉": {
        "label": "生肉",
        "category_assets": ["meat_category.png"],
        "fallback": (73, 584),
        "has_level": True,
    },
    "木材": {
        "label": "木材",
        "category_assets": ["wood_category.png"],
        "fallback": (130, 584),
        "has_level": True,
    },
    "煤矿": {
        "label": "煤矿",
        "category_assets": ["coal_category.png"],
        "fallback": (187, 584),
        "has_level": True,
    },
    "铁矿": {
        "label": "铁矿",
        "category_assets": ["iron_category.png"],
        "fallback": (244, 584),
        "has_level": True,
    },
    "联盟生肉": {
        "label": "联盟生肉",
        "category_assets": ["alliance_meat_category.png"],
        "fallback": (301, 584),
        "has_level": False,
    },
    "联盟木材": {
        "label": "联盟木材",
        "category_assets": ["alliance_wood_category.png"],
        "fallback": (73, 648),
        "has_level": False,
    },
    "联盟煤矿": {
        "label": "联盟煤矿",
        "category_assets": ["alliance_coal_category.png"],
        "fallback": (130, 648),
        "has_level": False,
    },
    "联盟铁矿": {
        "label": "联盟铁矿",
        "category_assets": ["alliance_iron_category.png"],
        "fallback": (187, 648),
        "has_level": False,
    },
}

GATHER_HERO_SLOT_REGIONS = [
    (0.05, 0.18, 0.34, 0.48),
    (0.35, 0.18, 0.64, 0.48),
    (0.65, 0.18, 0.94, 0.48),
]

MARCH_QUEUE_ROW_BASE_Y = [212, 258, 304, 350, 396, 442]


def register_task(name, param_defs=None, pre_task=None, after_task=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                executor: TaskExecutor = args[0]
                if pre_task:
                    for task in pre_task:
                        if type(task) == dict:
                            executor.execute_task(task.get("name"), task.get("param"))
                        else:
                            executor.execute_task(task, {})
                result = func(*args, **kwargs)
                if after_task:
                    for task in after_task:
                        if type(task) == dict:
                            executor.execute_task(task.get("name"), task.get("param"))
                        else:
                            executor.execute_task(task, {})
            except Exception as e:
                log_util.log.print(f"任务 {name} 执行出错：{e}")
                raise
            return result

        TASK_REGISTRY[name] = {
            "func": wrapper,
            "param_defs": param_defs or []
        }
        return wrapper

    return decorator


class TaskExecutor:

    def __init__(self, emulator_name=None, emulator_executor: EmulatorExecutor = None):
        self.run_status = True
        self.state = {}
        if emulator_name is None:
            self.emulator_name = emulator_executor.name
        else:
            self.emulator_name = emulator_name
        self.emulator_executor = emulator_executor

    def execute_task(self, task_name, params):
        if not params:
            params = {}
        task_info = TASK_REGISTRY.get(task_name)
        if not task_info:
            log_util.log.print(f"任务 {task_name} 未注册")
            return False
        func = task_info["func"]
        try:
            return func(self, params)
        except Exception as e:
            log_util.log.print(f"执行任务 {task_name} 出错: {e}")
            return False

    def execute_task_config(self, task_config):
        shared_limit = _configured_shared_march_limit(task_config)
        if shared_limit:
            self.state["active_march_shared_limit"] = shared_limit
        else:
            self.state.pop("active_march_shared_limit", None)

        for task in task_config.get("tasks", []):
            name = task["name"]
            params = task.get("params", {})
            if not self.execute_task(name, params):
                log_util.log.print(f"任务 {name} 执行失败，停止后续任务")
                break

    def close(self):
        self.run_status = False

    def get_run_status(self):
        return self.run_status


def _asset(name):
    return os.path.join(BEAST_RALLY_ASSET_DIR, name)


def _gather_asset(name):
    return os.path.join(GATHER_ASSET_DIR, name)


def _march_queue_asset(name):
    return os.path.join(MARCH_QUEUE_ASSET_DIR, name)


def _march_queue_templates(*names):
    paths = []
    for name in names:
        path = _march_queue_asset(name)
        if os.path.exists(path):
            paths.append(path)
    return paths


def _existing_templates(*paths):
    result = []
    for path in paths:
        if isinstance(path, (list, tuple)):
            result.extend(_existing_templates(*path))
        elif path and os.path.exists(path):
            result.append(path)
    return result


def _int_param(params, name, default, minimum=None, maximum=None):
    try:
        value = int(params.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _bool_param(params, name, default=False):
    value = params.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是", "使用"}
    return bool(value)


def _formation_indices_param(params):
    raw = params.get("formation_indices")
    if raw in (None, ""):
        return [_int_param(params, "formation_index", 1, minimum=1, maximum=8)]
    if isinstance(raw, int):
        values = [raw]
    elif isinstance(raw, (list, tuple)):
        values = raw
    else:
        normalized = str(raw).replace("，", ",").replace(" ", "")
        values = [item for item in normalized.split(",") if item]

    result = []
    for value in values:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= 8 and index not in result:
            result.append(index)
    return result or [_int_param(params, "formation_index", 1, minimum=1, maximum=8)]


def _normalize_gather_resource_type(value):
    normalized = str(value or "").strip()
    if not normalized:
        return None
    normalized = normalized.replace(" ", "")
    normalized = GATHER_RESOURCE_ALIASES.get(normalized, normalized)
    if normalized in GATHER_RESOURCE_CONFIG:
        return normalized
    return None


def _gather_queue_configs(params):
    queues = []
    for index in range(1, 7):
        enabled = _bool_param(params, f"queue{index}_enabled", index == 1)
        if not enabled:
            continue

        resource_type = _normalize_gather_resource_type(params.get(f"queue{index}_resource_type", "生肉"))
        if not resource_type:
            log_util.log.print(f"采集队列 {index} 的资源类型无效，已跳过")
            continue

        queues.append({
            "queue_index": index,
            "resource_type": resource_type,
            "level": _int_param(params, f"queue{index}_resource_level", 1, minimum=1),
            "full_only": _bool_param(params, f"queue{index}_full_only", False),
        })
    return queues


def _next_gather_queue(executor: TaskExecutor, queues):
    if not queues:
        return None
    key = "gather_queue_cursor"
    cursor = int(executor.state.get(key, 0)) % len(queues)
    queue = queues[cursor]
    executor.state[key] = (cursor + 1) % len(queues)
    return queue


def _configured_task_march_slot_count(task):
    name = task.get("name")
    params = task.get("params", {}) or {}
    if name == "自动集结冰原巨兽":
        return len(_formation_indices_param(params))
    if name == "自动挖矿":
        return len(_gather_queue_configs(params))
    return 0


def _configured_shared_march_limit(task_config):
    total = 0
    for task in task_config.get("tasks", []):
        total += _configured_task_march_slot_count(task)
    if total <= 0:
        return None
    return min(total, MAX_ACTIVE_MARCHES)


def _sleep_while_running(executor: TaskExecutor, seconds):
    end_time = time.time() + seconds
    while executor.run_status and time.time() < end_time:
        time.sleep(min(0.2, end_time - time.time()))


def _base_to_ratio(x, y):
    return x / BASE_SCREEN_WIDTH, y / BASE_SCREEN_HEIGHT


def _click_base(executor: TaskExecutor, x, y, wait_seconds=0.5):
    x_ratio, y_ratio = _base_to_ratio(x, y)
    executor.emulator_executor.click_ratio(x_ratio, y_ratio)
    _sleep_while_running(executor, wait_seconds)


def _swipe_base(executor: TaskExecutor, x1, y1, x2, y2, duration_ms=300, wait_seconds=0.4):
    width, height = executor.emulator_executor.get_screen_size()
    executor.emulator_executor.swipe(
        int(width * x1 / BASE_SCREEN_WIDTH),
        int(height * y1 / BASE_SCREEN_HEIGHT),
        int(width * x2 / BASE_SCREEN_WIDTH),
        int(height * y2 / BASE_SCREEN_HEIGHT),
        duration_ms,
    )
    _sleep_while_running(executor, wait_seconds)


def _region_from_ratio(emulator_executor: EmulatorExecutor, left, top, right, bottom):
    width, height = emulator_executor.get_screen_size()
    return (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )


def _region_from_base(emulator_executor: EmulatorExecutor, left, top, right, bottom):
    width, height = emulator_executor.get_screen_size()
    return (
        int(width * left / BASE_SCREEN_WIDTH),
        int(height * top / BASE_SCREEN_HEIGHT),
        int(width * right / BASE_SCREEN_WIDTH),
        int(height * bottom / BASE_SCREEN_HEIGHT),
    )


def _find_templates(executor: TaskExecutor, templates, threshold=0.82, region=None):
    paths = _existing_templates(*templates)
    if not paths:
        return None, None, False
    return executor.emulator_executor.find_img(paths, threshold=threshold, region=region, log_missing=False)


def _click_templates(executor: TaskExecutor, templates, threshold=0.82, region=None, wait_seconds=0.5):
    paths = _existing_templates(*templates)
    if not paths:
        return False
    clicked = executor.emulator_executor.click_template(
        paths,
        threshold=threshold,
        region=region,
        wait_seconds=0,
    )
    if clicked:
        _sleep_while_running(executor, wait_seconds)
    return clicked


def _wait_templates(executor: TaskExecutor, templates, timeout=5.0, threshold=0.82, region=None):
    paths = _existing_templates(*templates)
    if not paths:
        return None, None, False
    return executor.emulator_executor.wait_until_found(
        paths,
        timeout=timeout,
        threshold=threshold,
        region=region,
    )


def _is_wild_visible(executor: TaskExecutor):
    emulator = executor.emulator_executor
    search_region = _region_from_ratio(emulator, 0.0, 0.60, 0.18, 0.75)
    _, _, search_icon = _find_templates(
        executor,
        [_asset("search_icon.png")],
        threshold=0.58,
        region=search_region,
    )
    return search_icon


def _is_wild_or_search_visible(executor: TaskExecutor):
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


def _is_search_panel_visible(executor: TaskExecutor):
    bottom_region = _region_from_ratio(executor.emulator_executor, 0.0, 0.62, 1.0, 1.0)
    _, _, found = _find_templates(
        executor,
        [_asset("search_button.png"), _asset("beast_category.png")],
        threshold=0.76,
        region=bottom_region,
    )
    return found


def _is_exit_confirm_visible(executor: TaskExecutor):
    _, _, found = _find_templates(
        executor,
        [_asset("exit_confirm_title.png"), _asset("cancel_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.05, 0.25, 0.95, 0.72),
    )
    return found


def _cancel_exit_confirm(executor: TaskExecutor):
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


def _click_city_wild_button(executor: TaskExecutor):
    return _click_templates(
        executor,
        [_asset("city_wild_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.78, 0.84, 1.0, 1.0),
        wait_seconds=1.2,
    )


def _clear_known_overlays(executor: TaskExecutor, max_rounds=6):
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


def _return_home_or_wild(executor: TaskExecutor):
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


def _ensure_game_open(executor: TaskExecutor):
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


def _ensure_wild(executor: TaskExecutor):
    if _is_wild_or_search_visible(executor):
        return True

    if _clear_known_overlays(executor) and _is_wild_or_search_visible(executor):
        return True

    if _return_home_or_wild(executor):
        return True

    path = executor.emulator_executor.save_debug_screenshot("wild_not_found")
    log_util.log.print(f"[{executor.emulator_name}] 未能确认野外页面，截图: {path}")
    return False


def _open_search_panel(executor: TaskExecutor):
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


def _reset_search_category_to_first(executor: TaskExecutor):
    for _ in range(3):
        _swipe_base(executor, 120, 580, 420, 580, duration_ms=260, wait_seconds=0.25)


def _select_beast_category(executor: TaskExecutor):
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


def _set_search_level(executor: TaskExecutor, level):
    _click_base(executor, 380, 660, wait_seconds=0.3)
    executor.emulator_executor.clear_text(count=4)
    executor.emulator_executor.input_text(str(level))
    _sleep_while_running(executor, 0.2)
    _click_base(executor, 388, 760, wait_seconds=0.5)


def _click_search_button(executor: TaskExecutor):
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


def _search_beast_once(executor: TaskExecutor, level, attempt, max_attempts):
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


def _search_beast(executor: TaskExecutor, level, max_attempts, retry_interval):
    for attempt in range(1, max_attempts + 1):
        if _search_beast_once(executor, level, attempt, max_attempts):
            return True
        if attempt < max_attempts:
            log_util.log.print(f"[{executor.emulator_name}] 未找到可集结目标，{retry_interval} 秒后重试")
            _sleep_while_running(executor, retry_interval)

    log_util.log.print(f"[{executor.emulator_name}] 未找到 {level} 级冰原巨兽，结束本轮")
    _return_home_or_wild(executor)
    return False


def _select_gather_resource_category(executor: TaskExecutor, resource_type):
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


def _set_full_resource_only(executor: TaskExecutor, enabled):
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


def _search_gather_resource_once(executor: TaskExecutor, queue, attempt, max_attempts):
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


def _open_gather_formation(executor: TaskExecutor):
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


def _slot_region_from_ratio(executor: TaskExecutor, slot_index):
    left, top, right, bottom = GATHER_HERO_SLOT_REGIONS[slot_index]
    return _region_from_ratio(executor.emulator_executor, left, top, right, bottom)


def _hero_slot_has_hero(executor: TaskExecutor, slot_index):
    region = _slot_region_from_ratio(executor, slot_index)
    _, _, remove_icon_found = _find_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.70,
        region=region,
    )
    if remove_icon_found:
        return True

    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = region
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturated_pixels = int(((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)).sum())
    return saturated_pixels > 1200


def _hero_slot_is_blue(executor: TaskExecutor, slot_index):
    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = _slot_region_from_ratio(executor, slot_index)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_pixels = int(((hsv[:, :, 0] >= 88) & (hsv[:, :, 0] <= 122) &
                       (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)).sum())
    purple_or_gold_pixels = int((
        (((hsv[:, :, 0] >= 125) & (hsv[:, :, 0] <= 165)) |
         ((hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 34))) &
        (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)
    ).sum())
    return blue_pixels >= max(80, purple_or_gold_pixels * 1.2)


def _remove_hero_slot(executor: TaskExecutor, slot_index):
    region = _slot_region_from_ratio(executor, slot_index)
    if _click_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.70,
        region=region,
        wait_seconds=0.4,
    ):
        return True

    x1, y1, x2, _ = region
    executor.emulator_executor.click(x2 - 12, y1 + 12)
    _sleep_while_running(executor, 0.4)
    return True


def _keep_only_blue_gather_heroes(executor: TaskExecutor):
    removed = 0
    for slot_index in range(len(GATHER_HERO_SLOT_REGIONS)):
        if not _hero_slot_has_hero(executor, slot_index):
            continue
        if _hero_slot_is_blue(executor, slot_index):
            continue
        _remove_hero_slot(executor, slot_index)
        removed += 1
    if removed:
        log_util.log.print(f"[{executor.emulator_name}] 已移除 {removed} 个非蓝色采集英雄")
    return True


def _first_gather_hero_present(executor: TaskExecutor):
    return _hero_slot_has_hero(executor, 0)


def _choose_rally_duration(executor: TaskExecutor, duration_minutes):
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


def _start_rally_and_open_formation(executor: TaskExecutor, duration_minutes):
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


def _get_active_march_count(executor: TaskExecutor):
    image = executor.emulator_executor.screenshot()
    height, width = image.shape[:2]
    roi = image[int(height * 0.11):int(height * 0.32), 0:int(width * 0.40)]
    if roi.size == 0:
        return 0

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = (((hsv[:, :, 0] > 45) & (hsv[:, :, 0] < 85) &
             (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 120)).astype("uint8")) * 255
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    count = 0
    for index in range(1, num_labels):
        _, _, component_width, component_height, area = stats[index]
        if component_width >= 20 and component_height >= 4 and area >= 60:
            count += 1
    return count


def _template_matches_image(image, templates, threshold=0.76):
    paths = _existing_templates(templates)
    if not paths or image.size == 0:
        return False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    for path in paths:
        template = cv2.imread(path)
        if template is None:
            continue
        if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
            continue
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        if max_val >= threshold:
            return True
    return False


def _show_wild_march_queue_panel(executor: TaskExecutor):
    for _ in range(2):
        _, _, visible = _find_templates(
            executor,
            [_march_queue_asset("wild_queue_panel_anchor.png")],
            threshold=0.76,
            region=_region_from_ratio(executor.emulator_executor, 0.0, 0.16, 0.68, 0.32),
        )
        if visible:
            return True

        _click_base(executor, 8, 348, wait_seconds=0.4)
        _click_base(executor, 207, 168, wait_seconds=0.5)

    _, _, visible = _find_templates(
        executor,
        [_march_queue_asset("wild_queue_panel_anchor.png")],
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.0, 0.16, 0.68, 0.32),
    )
    return visible


def _close_march_queue_panel(executor: TaskExecutor):
    _click_base(executor, 292, 346, wait_seconds=0.3)


def _classify_march_queue_row(row_image):
    icon_region = row_image[6:38, 4:42]
    if _template_matches_image(
            row_image,
            _march_queue_templates("rally_icon.png"),
            threshold=0.72,
    ):
        return "beast"

    if _template_matches_image(
            row_image,
            _march_queue_templates("rally_status_icon.png", "rally_status_text.png", "rally_text.png"),
            threshold=0.84,
    ):
        return "beast"

    if _template_matches_image(
            icon_region,
            _march_queue_templates(
                "gather_meat_icon.png",
                "gather_wood_icon.png",
                "gather_coal_icon.png",
                "gather_iron_icon.png",
                "gather_alliance_meat_icon.png",
                "gather_alliance_wood_icon.png",
                "gather_alliance_coal_icon.png",
                "gather_alliance_iron_icon.png",
            ),
            threshold=0.70,
    ):
        return "gather"

    if _template_matches_image(
            row_image,
            _march_queue_templates("gather_status_text.png"),
            threshold=0.84,
    ):
        return "gather"

    return "unknown"


def _summarize_march_queue_image(image):
    summary = {"total": 0, "gather": 0, "beast": 0, "unknown": 0}
    height, width = image.shape[:2]
    for base_y in MARCH_QUEUE_ROW_BASE_Y:
        y1 = int(height * base_y / BASE_SCREEN_HEIGHT)
        y2 = int(height * (base_y + 44) / BASE_SCREEN_HEIGHT)
        x1 = int(width * 6 / BASE_SCREEN_WIDTH)
        x2 = int(width * 276 / BASE_SCREEN_WIDTH)
        row = image[y1:y2, x1:x2]
        if row.size == 0:
            continue

        hsv = cv2.cvtColor(row, cv2.COLOR_BGR2HSV)
        green_pixels = int(((hsv[:, :, 0] > 45) & (hsv[:, :, 0] < 85) &
                            (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 100)).sum())
        if green_pixels < 25:
            continue

        queue_type = _classify_march_queue_row(row)
        summary["total"] += 1
        summary[queue_type] += 1
    return summary


def _get_march_queue_summary(executor: TaskExecutor):
    if not _show_wild_march_queue_panel(executor):
        fallback_count = _get_active_march_count(executor)
        return {"total": fallback_count, "gather": 0, "beast": 0, "unknown": fallback_count}

    image = executor.emulator_executor.screenshot()
    summary = _summarize_march_queue_image(image)
    _close_march_queue_panel(executor)
    return summary


def _should_skip_for_active_limit(executor: TaskExecutor, limit, label, queue_type=None):
    queue_summary = _get_march_queue_summary(executor)
    active_count = queue_summary["total"]
    summary_detail = (
        f"挖矿={queue_summary.get('gather', 0)}, "
        f"巨兽={queue_summary.get('beast', 0)}, "
        f"未识别={queue_summary.get('unknown', 0)}"
    )

    if queue_type is not None:
        if active_count >= MAX_ACTIVE_MARCHES:
            log_util.log.print(
                f"[{executor.emulator_name}] 当前出征队列 {active_count}/{MAX_ACTIVE_MARCHES} "
                f"已达到游戏行军上限，跳过本轮（{summary_detail}）"
            )
            return True
        typed_count = queue_summary.get(queue_type, 0)
        typed_label = label
        if queue_type == "beast" and queue_summary.get("unknown", 0):
            typed_count += queue_summary["unknown"]
            typed_label = f"{label}(含未识别)"
        if typed_count >= limit:
            log_util.log.print(
                f"[{executor.emulator_name}] 当前{typed_label}队列 {typed_count}/{limit} "
                f"已达到配置数量，跳过本轮（{summary_detail}）"
            )
            return True
        log_util.log.print(
            f"[{executor.emulator_name}] 当前出征队列 {active_count}/{MAX_ACTIVE_MARCHES}，"
            f"{typed_label}队列 {typed_count}/{limit}，继续尝试{label}（{summary_detail}）"
        )
        return False

    shared_limit = executor.state.get("active_march_shared_limit")
    active_limit = int(shared_limit) if shared_limit else limit
    active_limit = max(1, min(active_limit, MAX_ACTIVE_MARCHES))
    limit_label = "共享行军上限" if shared_limit else f"配置{label}数量"

    if active_count >= active_limit:
        log_util.log.print(f"[{executor.emulator_name}] 当前出征队列 {active_count}/{active_limit} 已达到{limit_label}，跳过本轮")
        return True

    log_util.log.print(f"[{executor.emulator_name}] 当前出征队列 {active_count}/{active_limit}，继续尝试{label}")
    return False


def _should_skip_for_active_marches(executor: TaskExecutor, formation_indices):
    return _should_skip_for_active_limit(executor, len(formation_indices), "巨兽", queue_type="beast")


def _select_formation(executor: TaskExecutor, formation_index):
    if formation_index < 1:
        formation_index = 1
    if formation_index > 8:
        log_util.log.print(f"[{executor.emulator_name}] 当前只支持直接选择 1-8 号编队，改用 8 号")
        formation_index = 8

    x = 38 + (formation_index - 1) * 45
    _click_base(executor, x, 75, wait_seconds=0.8)
    log_util.log.print(f"[{executor.emulator_name}] 已选择 {formation_index} 号编队")
    return formation_index


def _select_next_formation(executor: TaskExecutor, formation_indices, require_hero_for_march):
    key = f"formation_cursor:{','.join(str(index) for index in formation_indices)}"
    cursor = int(executor.state.get(key, 0)) % len(formation_indices)

    for offset in range(len(formation_indices)):
        list_index = (cursor + offset) % len(formation_indices)
        formation_index = formation_indices[list_index]
        _select_formation(executor, formation_index)

        if require_hero_for_march and not _has_hero(executor):
            log_util.log.print(f"[{executor.emulator_name}] {formation_index} 号编队未识别到英雄，跳过该编队")
            continue

        executor.state[key] = (list_index + 1) % len(formation_indices)
        return formation_index

    log_util.log.print(f"[{executor.emulator_name}] 配置的编队均未识别到英雄，结束本轮")
    return None


def _has_hero(executor: TaskExecutor):
    hero_region = _region_from_ratio(executor.emulator_executor, 0.08, 0.20, 0.92, 0.48)
    _, _, remove_icon_found = _find_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.74,
        region=hero_region,
    )
    if remove_icon_found:
        return True

    image = executor.emulator_executor.screenshot()
    height, width = image.shape[:2]
    x1, y1, x2, y2 = (
        int(width * 0.08),
        int(height * 0.20),
        int(width * 0.92),
        int(height * 0.48),
    )
    crop = image[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mean_saturation = float(hsv[:, :, 1].mean())
    orange_pixels = int(((hsv[:, :, 0] > 5) & (hsv[:, :, 0] < 35) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 120)).sum())
    return mean_saturation > 80 or orange_pixels > 5000


def _is_formation_visible(executor: TaskExecutor):
    _, _, found = _find_templates(
        executor,
        [_asset("march_button.png"), _asset("formation_anchor.png")],
        threshold=0.74,
    )
    return found


def _is_stamina_dialog_visible(executor: TaskExecutor):
    _, _, found = _find_templates(
        executor,
        [
            _asset("stamina_not_enough_title.png"),
            _asset("stamina_can_item.png"),
            _asset("use_stamina_can_button.png"),
        ],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.08, 0.18, 0.92, 0.86),
    )
    return found


def _is_same_target_prompt_visible(executor: TaskExecutor):
    _, _, found = _find_templates(
        executor,
        [_asset("same_target_prompt.png")],
        threshold=0.78,
        region=_region_from_ratio(executor.emulator_executor, 0.08, 0.34, 0.92, 0.56),
    )
    return found


def _cancel_same_target_prompt(executor: TaskExecutor):
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


def _looks_like_modal_dialog(executor: TaskExecutor):
    image = executor.emulator_executor.screenshot()
    height, width = image.shape[:2]
    x1, y1, x2, y2 = (
        int(width * 0.08),
        int(height * 0.20),
        int(width * 0.92),
        int(height * 0.82),
    )
    crop = image[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_pixels = int(((hsv[:, :, 0] > 85) & (hsv[:, :, 0] < 120) & (hsv[:, :, 1] > 35) & (hsv[:, :, 2] > 80)).sum())
    bright_pixels = int((hsv[:, :, 2] > 170).sum())
    return blue_pixels > 8000 and bright_pixels > 15000


BUILTIN_DIGIT_PATTERNS = {
    "0": [
        ".####.",
        "######",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        "######",
        ".####.",
    ],
    "1": [
        "..##..",
        ".###..",
        "..##..",
        "..##..",
        "..##..",
        "..##..",
        ".####.",
        ".####.",
    ],
    "2": [
        ".####.",
        "######",
        "#...##",
        "...###",
        "..###.",
        ".###..",
        "#####.",
        "######",
    ],
    "3": [
        "#####.",
        "######",
        "....##",
        "..####",
        "..####",
        "....##",
        "######",
        "#####.",
    ],
    "4": [
        "....#.",
        "..###.",
        "..###.",
        ".####.",
        "##..#.",
        "######",
        "######",
        "...###",
    ],
    "5": [
        "######",
        "######",
        "##....",
        "#####.",
        ".#####",
        "....##",
        "######",
        "#####.",
    ],
    "6": [
        ".####.",
        "#####.",
        "##....",
        "#####.",
        "######",
        "##..##",
        "######",
        ".####.",
    ],
    "7": [
        "####.",
        "#####",
        "...##",
        "...#.",
        "..##.",
        "..##.",
        ".##..",
        ".##..",
    ],
    "8": [
        "..##..",
        ".####.",
        "##..#.",
        "#####.",
        "#####.",
        "##..##",
        "##..##",
        "#####.",
    ],
    "9": [
        "##....",
        "####..",
        "##..##",
        "##..##",
        "######",
        "....##",
        "#.####",
        "#####.",
    ],
}


def _normalize_digit_mask(mask, size=(16, 20)):
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    digit = mask[y:y + h, x:x + w]
    return cv2.resize(digit, size, interpolation=cv2.INTER_NEAREST)


def _digit_pattern_to_mask(pattern):
    height = len(pattern)
    width = max(len(row) for row in pattern)
    mask = np.zeros((height, width), dtype="uint8")
    for y, row in enumerate(pattern):
        for x, value in enumerate(row):
            if value != ".":
                mask[y, x] = 255
    return mask


def _load_digit_templates():
    digit_dir = os.path.join(BEAST_RALLY_ASSET_DIR, "digits")
    templates = {digit: [] for digit in "0123456789"}
    if os.path.isdir(digit_dir):
        for digit in "0123456789":
            path = os.path.join(digit_dir, f"{digit}.png")
            if not os.path.exists(path):
                continue
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            _, mask = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
            normalized = _normalize_digit_mask(mask)
            if normalized is not None:
                templates[digit].append(normalized)

    for digit, pattern in BUILTIN_DIGIT_PATTERNS.items():
        normalized = _normalize_digit_mask(_digit_pattern_to_mask(pattern))
        if normalized is not None:
            templates[digit].append(normalized)

    return {digit: masks for digit, masks in templates.items() if masks}


def _split_digit_group(mask, start, end):
    group_width = end - start
    if group_width <= 7:
        return [(start, end)]

    column_counts = (mask[:, start:end] > 0).sum(axis=0)
    midpoint = group_width // 2
    left = max(3, midpoint - 3)
    right = min(group_width - 3, midpoint + 3)
    if left > right:
        return [(start, end)]

    split_candidates = range(left, right + 1)
    split_at = min(split_candidates, key=lambda index: column_counts[index])
    absolute_split = start + split_at
    if column_counts[split_at] <= 1:
        left_group = (start, absolute_split)
        right_group = (absolute_split + 1, end)
    else:
        left_group = (start, absolute_split)
        right_group = (absolute_split, end)

    result = []
    for group_start, group_end in (left_group, right_group):
        if group_end - group_start <= 0:
            continue
        result.extend(_split_digit_group(mask, group_start, group_end))
    return result


def _segment_digit_groups(mask):
    column_has_digit = mask.sum(axis=0) > 0
    groups = []
    start = None
    for index, active in enumerate(column_has_digit):
        if active and start is None:
            start = index
        elif not active and start is not None:
            groups.extend(_split_digit_group(mask, start, index))
            start = None
    if start is not None:
        groups.extend(_split_digit_group(mask, start, len(column_has_digit)))
    return groups


def _read_stamina_can_count(executor: TaskExecutor):
    templates = _load_digit_templates()
    if not templates:
        return None

    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = _region_from_base(executor.emulator_executor, 66, 335, 96, 352)
    roi = image[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi = cv2.resize(roi, (30, 17), interpolation=cv2.INTER_AREA)
    blue, green, red = cv2.split(roi)
    mask = (((blue > 170) & (green > 170) & (red > 170)).astype("uint8")) * 255
    groups = _segment_digit_groups(mask)

    digits = []
    for start, end in groups:
        candidate = mask[:, start:end]
        points = cv2.findNonZero(candidate)
        if points is None:
            continue
        _, y, w, h = cv2.boundingRect(points)
        area = int((candidate > 0).sum())
        if w < 3 or h < 6 or area < 12:
            continue

        normalized = _normalize_digit_mask(candidate)
        if normalized is None:
            continue

        best_digit = None
        best_score = 0.0
        for digit, digit_templates in templates.items():
            for template in digit_templates:
                intersection = int(((normalized > 0) & (template > 0)).sum())
                union = int(((normalized > 0) | (template > 0)).sum())
                score = intersection / union if union else 0.0
                if score > best_score:
                    best_digit = digit
                    best_score = score
        if best_digit is None or best_score < 0.28:
            return None
        digits.append(best_digit)

    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def _close_stamina_dialog(executor: TaskExecutor):
    if _is_stamina_dialog_visible(executor) or _looks_like_modal_dialog(executor):
        if not _click_templates(
            executor,
            [_asset("stamina_close_x.png"), _asset("close_x.png")],
            threshold=0.72,
            region=_region_from_ratio(executor.emulator_executor, 0.82, 0.06, 1.0, 0.16),
            wait_seconds=1.0,
        ):
            _click_base(executor, 416, 84, wait_seconds=1.0)


def _claim_free_stamina(executor: TaskExecutor):
    log_util.log.print(f"[{executor.emulator_name}] 优先尝试领取免费体力")
    if not _click_templates(
        executor,
        [_asset("free_stamina_claim_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.60, 0.24, 0.96, 0.38),
        wait_seconds=1.0,
    ):
        _click_base(executor, 362, 248, wait_seconds=1.0)
    _close_stamina_dialog(executor)
    return True


def _handle_stamina_shortage(
        executor: TaskExecutor,
        use_stamina_can,
        stamina_can_reserve_count,
        use_diamond_for_stamina,
        try_free_stamina,
):
    if not (_is_stamina_dialog_visible(executor) or _looks_like_modal_dialog(executor)):
        return False

    if try_free_stamina:
        return _claim_free_stamina(executor)

    stamina_can_blocked = False
    stamina_can_block_reason = None
    if use_stamina_can:
        can_count = _read_stamina_can_count(executor)
        if can_count is None and stamina_can_reserve_count > 0:
            path = executor.emulator_executor.save_debug_screenshot("stamina_can_count_unknown")
            stamina_can_block_reason = "未能识别背包体力罐头数量，已配置保留数量，停止使用罐头"
            log_util.log.print(f"[{executor.emulator_name}] {stamina_can_block_reason}，截图: {path}")
            stamina_can_blocked = True
        elif can_count is not None and can_count <= stamina_can_reserve_count:
            stamina_can_block_reason = (
                f"背包体力罐头数量 {can_count} 小于等于保留数量 {stamina_can_reserve_count}，不再使用"
            )
            log_util.log.print(f"[{executor.emulator_name}] {stamina_can_block_reason}")
            stamina_can_blocked = True
        else:
            log_util.log.print(f"[{executor.emulator_name}] 体力不足，尝试使用背包体力罐头")
            if not _click_templates(
                executor,
                [_asset("use_stamina_can_button.png")],
                threshold=0.72,
                region=_region_from_ratio(executor.emulator_executor, 0.60, 0.30, 0.96, 0.48),
                wait_seconds=1.0,
            ):
                _click_base(executor, 362, 327, wait_seconds=1.0)
            _close_stamina_dialog(executor)
            return True

    if use_diamond_for_stamina:
        log_util.log.print(f"[{executor.emulator_name}] 体力不足，允许钻石购买体力，尝试购买")
        if not _click_templates(
            executor,
            [_asset("buy_stamina_with_diamond_button.png")],
            threshold=0.72,
            region=_region_from_ratio(executor.emulator_executor, 0.60, 0.42, 0.96, 0.62),
            wait_seconds=1.0,
        ):
            _click_base(executor, 362, 417, wait_seconds=1.0)
        if _looks_like_modal_dialog(executor):
            if not _click_templates(
                executor,
                [_asset("confirm_button.png"), _asset("ok_button.png")],
                threshold=0.72,
                region=_region_from_ratio(executor.emulator_executor, 0.42, 0.55, 0.95, 0.82),
                wait_seconds=1.0,
            ):
                _click_base(executor, 318, 493, wait_seconds=1.0)
        _close_stamina_dialog(executor)
        return True

    if stamina_can_blocked or not use_stamina_can:
        path = executor.emulator_executor.save_debug_screenshot("stamina_not_enough")
        if stamina_can_block_reason:
            message = f"体力不足，{stamina_can_block_reason}，且未允许钻石购买"
        elif not use_stamina_can:
            message = "体力不足，未启用背包体力罐头，且未允许钻石购买"
        else:
            message = "体力不足，背包体力罐头未能使用，且未允许钻石购买"
        log_util.log.print(f"[{executor.emulator_name}] {message}，截图: {path}")
        _return_home_or_wild(executor)
        return False
    return False


def _wait_after_march(
        executor: TaskExecutor,
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
        executor: TaskExecutor,
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


@register_task("自动打开游戏", param_defs=[])
def check_open(executor: TaskExecutor, params):
    x, y, find = executor.emulator_executor.find_img("buttons/button1.png")
    if find:
        log_util.log.print(f"[{executor.emulator_name}] 识别到游戏未打开，打开游戏")
        executor.emulator_executor.click(x, y)
    return True


@register_task("重新登录", param_defs=[{
    "name": "interval", "type": "int", "default": 0, "desc": "重上等待时间/秒"
}])
def re_login(executor: TaskExecutor, params):
    x, y, find = executor.emulator_executor.find_img("buttons/relogin.png")
    if find:
        inv = params.get("interval", 0)
        log_util.log.print(f"[{executor.emulator_name}] 识别到游戏未登录，等待{inv}秒后重新登录")
        time.sleep(inv)
        log_util.log.print(f"[{executor.emulator_name}] 执行游戏重新登录")
        executor.emulator_executor.click(x, y)
    return True


@register_task("返回主页", pre_task=["自动打开游戏", "重新登录"])
def back_home(executor: TaskExecutor, params):
    back_image_path = ["buttons/back.png", "buttons/back2.png", "buttons/back3.png"]
    x, y, find = executor.emulator_executor.find_img(back_image_path)
    while find:
        log_util.log.print(f"[{executor.emulator_name}] 点击返回")
        executor.emulator_executor.click(x, y)
        time.sleep(0.5)
        x, y, find = executor.emulator_executor.find_img(back_image_path)
    return True


@register_task("打开联盟", pre_task=["自动打开游戏", "重新登录"])
def click_lm(executor: TaskExecutor, params):
    x, y, find = executor.emulator_executor.find_img("buttons/lm.png")
    if find:
        log_util.log.print(f"[{executor.emulator_name}] 进入联盟页")
        executor.emulator_executor.click(x, y)
    return True


@register_task("自动洗练")
def pet_page(executor: TaskExecutor, params):
    region = (290, 225, 324, 250)
    i = 0
    while executor.run_status:
        _, _, up = executor.emulator_executor.find_img("buttons/up.png", region=region, threshold=0.75)
        _, _, down = executor.emulator_executor.find_img("buttons/down.png", region=region, threshold=0.65)
        _, _, zero = executor.emulator_executor.find_img("buttons/add_zero.png", region=(261, 231, 294, 250),
                                                         threshold=0.60)
        if up:
            log_util.log.print(f"[{executor.emulator_name}] 洗练替换")
            executor.emulator_executor.find_and_click_button("buttons/replaced.png")
        elif down or zero:
            log_util.log.print(f"[{executor.emulator_name}] 洗练重洗")
            executor.emulator_executor.find_and_click_button("buttons/re_baptize.png")
            time.sleep(0.2)
        else:
            executor.emulator_executor.find_and_click_button("buttons/baptize.png")
        i += 1
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


@register_task("自动挖矿", param_defs=_build_gather_param_defs())
def auto_gather_resources(executor: TaskExecutor, params):
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
])
def rally_icefield_beast(executor: TaskExecutor, params):
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


if __name__ == '__main__':
    emulatorExecutor: TaskExecutor = TaskExecutor('123')
    emulatorExecutor.execute_task_config({
        "tasks": [
            {
                "name": "点击按钮",
                "params": {
                    "template_path": "buttons/button1.png",
                    "threshold": 0.85
                }
            },
            {
                "name": "等待",
                "params": {
                    "seconds": 1,
                }
            }

        ]
    })
