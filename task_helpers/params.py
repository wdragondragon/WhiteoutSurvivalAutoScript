import log_util
from task_helpers.constants import (
    GATHER_RESOURCE_ALIASES,
    GATHER_RESOURCE_CONFIG,
    MAX_ACTIVE_MARCHES,
)


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


def _next_gather_queue(executor, queues):
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


def configured_shared_march_limit(task_config):
    total = 0
    for task in task_config.get("tasks", []):
        total += _configured_task_march_slot_count(task)
    if total <= 0:
        return None
    return min(total, MAX_ACTIVE_MARCHES)


_configured_shared_march_limit = configured_shared_march_limit
