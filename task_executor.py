# emulator_executor.py
import importlib
import pkgutil
import time

import log_util
from TaskStatus import TaskStatus
from emulator_executor import EmulatorExecutor

TASK_REGISTRY = {}


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
                if result == TaskStatus.SUCCESS:
                    time.sleep(1)
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
        for task in task_config.get("tasks", []):
            name = task["name"]
            params = task.get("params", {})
            if self.execute_task(name, params) == TaskStatus.FAILED:
                log_util.log.print(f"任务 {name} 执行失败，停止后续任务")
                break

    def close(self):
        self.run_status = False

    def get_run_status(self):
        return self.run_status
