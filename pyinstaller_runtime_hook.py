import os
import sys


if getattr(sys, "frozen", False):
    override = os.environ.get("WHITEOUT_AUTO_DATA_DIR")
    if override:
        user_data_dir = os.path.abspath(os.path.expanduser(override))
    elif sys.platform == "win32":
        base_dir = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        user_data_dir = os.path.join(base_dir, "WhiteoutSurvivalAutoScript")
    elif sys.platform == "darwin":
        user_data_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "WhiteoutSurvivalAutoScript")
    else:
        base_dir = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        user_data_dir = os.path.join(base_dir, "WhiteoutSurvivalAutoScript")
    os.makedirs(user_data_dir, exist_ok=True)
    os.chdir(user_data_dir)
