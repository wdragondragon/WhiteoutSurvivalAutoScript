import os
import shutil
import sys


APP_DIR_NAME = "WhiteoutSurvivalAutoScript"


def bundled_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    return os.path.join(bundled_base_dir(), *parts)


def resolve_resource_path(path):
    if not path:
        return path
    if os.path.isabs(path) or os.path.exists(path):
        return path
    return resource_path(path)


def user_data_dir():
    override = os.environ.get("WHITEOUT_AUTO_DATA_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))

    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base_dir = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base_dir, APP_DIR_NAME)


def user_path(*parts):
    return os.path.join(user_data_dir(), *parts)


def task_configs_dir():
    return user_path("configs")


def config_file_path():
    return user_path("config.json")


def ensure_user_data():
    os.makedirs(user_data_dir(), exist_ok=True)
    os.makedirs(task_configs_dir(), exist_ok=True)
    _copy_if_missing(resource_path("config.json"), config_file_path())
    _seed_task_configs()


def _copy_if_missing(src, dst):
    if not os.path.exists(src) or os.path.exists(dst):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def _seed_task_configs():
    bundled_configs_dir = resource_path("configs")
    if not os.path.isdir(bundled_configs_dir):
        return
    for filename in os.listdir(bundled_configs_dir):
        if not filename.endswith(".json"):
            continue
        _copy_if_missing(
            os.path.join(bundled_configs_dir, filename),
            os.path.join(task_configs_dir(), filename),
        )
