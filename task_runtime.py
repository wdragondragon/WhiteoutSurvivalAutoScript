import time

import log_util
from StepStatus import StepStatus
from TaskStatus import TaskStatus

TASK_REGISTRY = {}


def is_task_success(result):
    return result in (TaskStatus.SUCCESS, StepStatus.SUCCESS, True)


def is_task_failure(result):
    return result in (TaskStatus.FAILED, StepStatus.FAILED, False)


def _task_source(func):
    return f"{func.__module__}.{func.__name__}"


def _task_call_config(task):
    if isinstance(task, dict):
        return task.get("name"), task.get("params", task.get("param", {})) or {}
    return task, {}


def register_task(name, param_defs=None, pre_task=None, after_task=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                executor = args[0]
                if pre_task:
                    for task in pre_task:
                        task_name, task_params = _task_call_config(task)
                        pre_result = executor.execute_task(task_name, task_params)
                        if is_task_failure(pre_result):
                            return pre_result
                result = func(*args, **kwargs)
                if is_task_success(result):
                    time.sleep(1)
                if after_task:
                    for task in after_task:
                        task_name, task_params = _task_call_config(task)
                        after_result = executor.execute_task(task_name, task_params)
                        if is_task_failure(after_result):
                            return after_result
            except Exception as e:
                log_util.log.print(f"任务 {name} 执行出错：{e}")
                raise
            return result

        source = _task_source(func)
        if name in TASK_REGISTRY:
            previous_source = TASK_REGISTRY[name].get("source", "未知来源")
            log_util.log.print(f"任务 {name} 已注册，将由 {source} 覆盖 {previous_source}")

        TASK_REGISTRY[name] = {
            "func": wrapper,
            "param_defs": param_defs or [],
            "source": source,
        }
        return wrapper

    return decorator


class TaskExecutor:

    def __init__(self, emulator_name=None, emulator_executor=None):
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
        from task_helpers.params import configured_shared_march_limit

        shared_limit = configured_shared_march_limit(task_config)
        if shared_limit:
            self.state["active_march_shared_limit"] = shared_limit
        else:
            self.state.pop("active_march_shared_limit", None)

        for task in task_config.get("tasks", []):
            name = task["name"]
            params = task.get("params", {})
            if is_task_failure(self.execute_task(name, params)):
                log_util.log.print(f"任务 {name} 执行失败，停止后续任务")
                break

    def close(self):
        self.run_status = False

    def get_run_status(self):
        return self.run_status


_is_task_success = is_task_success
_is_task_failure = is_task_failure
