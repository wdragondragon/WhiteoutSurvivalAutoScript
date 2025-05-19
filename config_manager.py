# config_manager.py
import json
import threading

# 修改为你的雷电模拟器路径
ADB_PATH = r"C:\leidian\LDPlayer9\adb.exe"

LDCONSOLE_PATH = r"C:\leidian\LDPlayer9\ldconsole.exe"

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

    def get_task_configs(self):
        return self.config.get("task_configs", [
            {
                "name": "示例任务配置1",
                "tasks": [
                    {"name": "点击按钮", "params": {"template_path": "buttons/start.png", "threshold": 0.9}},
                    {"name": "等待", "params": {"seconds": 2}}
                ]
            }
        ])

    def set_task_configs(self, task_configs):
        self.config["task_configs"] = task_configs

    def get_emulator_bindings(self):
        return self.config.get("emulator_bindings", {"模拟器1": "示例任务配置1"})

    def set_emulator_bindings(self, bindings):
        self.config["emulator_bindings"] = bindings
