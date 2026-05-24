# config_manager.py
import json
import os
import threading

from execution_config import normalize_emulator_settings, normalize_execution_settings

# 修改为你的雷电模拟器路径
ADB_PATH = r"E:\leidian\LDPlayer9\adb.exe"

LDCONSOLE_PATH = r"E:\leidian\LDPlayer9\ldconsole.exe"

# 模板匹配阈值（0~1）
MATCH_THRESHOLD = 0.85


class ConfigManager:
    def __init__(self, filepath="config.json"):
        self.filepath = filepath
        self._lock = threading.Lock()
        self.config = {}
        self.load()

    def load(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {}
        except json.JSONDecodeError as e:
            print(f"加载配置出错: {e}")
            self.config = {}

    def save(self):
        with self._lock:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def get_selected_emulators(self):
        return self.config.get("selected_emulators", [])

    def set_selected_emulators(self, emulators_list):
        self.config["selected_emulators"] = emulators_list

    def get_emulator_bindings(self, emulator_name):
        return self.config.get("emulator_bindings", {}).get(emulator_name)

    def set_emulator_bindings(self, emulator_name, config_name):
        if "emulator_bindings" not in self.config:
            self.config["emulator_bindings"] = {}
        self.config.get("emulator_bindings")[emulator_name] = config_name

    def get_execution_settings(self):
        return normalize_execution_settings(self.config)

    def set_execution_settings(self, settings):
        normalized = normalize_execution_settings(settings)
        self.config.update(normalized)

    def get_emulator_settings(self, emulator_name):
        settings_map = self.config.get("emulator_settings", {})
        return normalize_emulator_settings(settings_map.get(emulator_name, {}))

    def set_emulator_settings(self, emulator_name, settings):
        if "emulator_settings" not in self.config:
            self.config["emulator_settings"] = {}
        self.config["emulator_settings"][emulator_name] = normalize_emulator_settings(settings)

    def get_emulator_shuffle_tasks(self, emulator_name):
        return self.get_emulator_settings(emulator_name).get("shuffle_tasks", False)

    def set_emulator_shuffle_tasks(self, emulator_name, enabled):
        settings = self.get_emulator_settings(emulator_name)
        settings["shuffle_tasks"] = bool(enabled)
        self.set_emulator_settings(emulator_name, settings)


class TaskConfigManager:
    def __init__(self, config_path="configs/"):
        self.config_path = config_path
        os.makedirs("configs", exist_ok=True)

    def save_config_to_file(self, config_name, task_config):
        data = {
            "name": config_name,
            "tasks": task_config
        }
        path = os.path.join(self.config_path, f"{config_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"配置已保存至 {path}")

    def load_config_from_file(self, config_name):
        path = os.path.join(self.config_path, f"{config_name}.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            print(f"加载出错: {str(e)}")

    def get_config_name_list(self):
        config_name_list = []
        if not os.path.exists(self.config_path):
            return
        for fname in os.listdir(self.config_path):
            if fname.endswith(".json"):
                config_name_list.append(fname[:-5])
        return config_name_list
