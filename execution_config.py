DEFAULT_EXECUTION_SETTINGS = {
    "batch_enabled": False,
    "batch_size": 1,
    "batch_cycle_mode": "loop",
    "serial_actions_enabled": False,
    "serial_action_interval_sec": 1.0,
    "relogin_interval_sec": 0.0,
    "batch_start_timeout_sec": 180,
    "batch_launch_interval_sec": 0.0,
    "batch_between_delay_sec": 3.0,
    "session_retry_limit": 3,
}

DEFAULT_TASK_CONFIG_SETTINGS = {
    "shuffle_tasks": False,
}


def _bool_value(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
    return bool(value)


def _int_value(value, default, minimum=None, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def _float_value(value, default, minimum=None, maximum=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def normalize_execution_settings(raw_settings=None):
    raw_settings = raw_settings or {}
    settings = DEFAULT_EXECUTION_SETTINGS.copy()
    settings.update(raw_settings)
    settings["batch_enabled"] = _bool_value(settings.get("batch_enabled"), False)
    settings["batch_size"] = _int_value(settings.get("batch_size"), 1, minimum=1)
    settings["batch_cycle_mode"] = settings.get("batch_cycle_mode") or "loop"
    settings["serial_actions_enabled"] = _bool_value(settings.get("serial_actions_enabled"), False)
    settings["serial_action_interval_sec"] = _float_value(
        settings.get("serial_action_interval_sec"), 1.0, minimum=0.0
    )
    settings["relogin_interval_sec"] = _float_value(settings.get("relogin_interval_sec"), 0.0, minimum=0.0)
    settings["batch_start_timeout_sec"] = _int_value(settings.get("batch_start_timeout_sec"), 180, minimum=1)
    settings["batch_launch_interval_sec"] = _float_value(
        settings.get("batch_launch_interval_sec"), 0.0, minimum=0.0
    )
    settings["batch_between_delay_sec"] = _float_value(settings.get("batch_between_delay_sec"), 3.0, minimum=0.0)
    settings["session_retry_limit"] = _int_value(settings.get("session_retry_limit"), 3, minimum=0)
    return settings


def normalize_task_config_settings(raw_settings=None):
    raw_settings = raw_settings or {}
    settings = DEFAULT_TASK_CONFIG_SETTINGS.copy()
    settings.update(raw_settings)
    settings["shuffle_tasks"] = _bool_value(settings.get("shuffle_tasks"), False)
    return settings
