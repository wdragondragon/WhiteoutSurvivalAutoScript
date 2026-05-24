import random
import time

import log_util
from execution_config import normalize_execution_settings, normalize_task_config_settings
from StepStatus import StepStatus
from TaskStatus import TaskStatus

TASK_REGISTRY = {}


class SessionRecovered(Exception):
    pass


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


def register_task(name, param_defs=None, pre_task=None, after_task=None, initial_state="wild"):
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
            except SessionRecovered:
                raise
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
            "initial_state": initial_state,
        }
        return wrapper

    return decorator


class TaskExecutor:

    def __init__(self, emulator_name=None, emulator_executor=None, runtime_options=None, task_status_callback=None):
        self.run_status = True
        self.state = {}
        self.runtime_options = normalize_execution_settings(runtime_options)
        self.task_status_callback = task_status_callback
        self.current_task_name = None
        self.current_task_initial_state = None
        self._handling_session_recovery = False
        self._last_session_checkpoint_at = 0.0
        if emulator_name is None:
            self.emulator_name = emulator_executor.name
        else:
            self.emulator_name = emulator_name
        self.emulator_executor = emulator_executor
        if self.emulator_executor is not None:
            self.emulator_executor.before_input_action = self.before_input_action

    def _emit_task_status(self, task_name):
        if not self.task_status_callback:
            return
        try:
            self.task_status_callback(self.emulator_name, task_name or "")
        except Exception as e:
            log_util.log.print(f"[{self.emulator_name}] 任务状态回调失败: {e}")

    def execute_task(self, task_name, params):
        if not params:
            params = {}
        task_info = TASK_REGISTRY.get(task_name)
        if not task_info:
            log_util.log.print(f"任务 {task_name} 未注册")
            return False
        func = task_info["func"]
        initial_state = task_info.get("initial_state", "wild")
        session_retry_limit = int(self.runtime_options.get("session_retry_limit", 3))
        previous_task_name = self.current_task_name
        previous_initial_state = self.current_task_initial_state
        try:
            for retry_index in range(session_retry_limit + 1):
                self.current_task_name = task_name
                self.current_task_initial_state = initial_state
                self._emit_task_status(f"准备: {task_name}")
                try:
                    if not self.prepare_current_task_state():
                        return False
                    self._emit_task_status(task_name)
                    return func(self, params)
                except SessionRecovered:
                    if retry_index >= session_retry_limit:
                        log_util.log.print(f"[{self.emulator_name}] 任务 {task_name} 多次重登恢复失败，停止执行")
                        return False
                    log_util.log.print(
                        f"[{self.emulator_name}] 任务 {task_name} 重登恢复完成，"
                        f"重新执行({retry_index + 1}/{session_retry_limit})"
                    )
                except Exception as e:
                    log_util.log.print(f"执行任务 {task_name} 出错: {e}")
                    return False
            return False
        finally:
            self.current_task_name = previous_task_name
            self.current_task_initial_state = previous_initial_state
            self._emit_task_status(previous_task_name)

    def execute_task_config(self, task_config, runtime_options=None):
        from task_helpers.params import configured_shared_march_limit

        if not isinstance(task_config, dict):
            log_util.log.print(f"[{self.emulator_name}] 任务配置无效，跳过执行")
            return

        previous_options = self.runtime_options
        if runtime_options:
            merged_options = self.runtime_options.copy()
            merged_options.update(runtime_options)
            self.runtime_options = normalize_execution_settings(merged_options)

        shared_limit = configured_shared_march_limit(task_config)
        if shared_limit:
            self.state["active_march_shared_limit"] = shared_limit
        else:
            self.state.pop("active_march_shared_limit", None)

        try:
            task_config_settings = normalize_task_config_settings(task_config)
            tasks = list(task_config.get("tasks", []))
            if task_config_settings.get("shuffle_tasks") and len(tasks) > 1:
                random.shuffle(tasks)
                order = " -> ".join(task.get("name", "未知任务") for task in tasks)
                log_util.log.print(f"[{self.emulator_name}] 本轮乱序任务顺序: {order}")

            for task in tasks:
                if not self.run_status:
                    break
                name = task["name"]
                params = task.get("params", {})
                if is_task_failure(self.execute_task(name, params)):
                    log_util.log.print(f"任务 {name} 执行失败，停止后续任务")
                    break
        finally:
            self.runtime_options = previous_options

    def prepare_current_task_state(self):
        from task_state import prepare_task_state

        return prepare_task_state(self, self.current_task_initial_state)

    def before_input_action(self, action_name):
        if self._handling_session_recovery or not self.current_task_name:
            return
        self._recover_session_if_needed()

    def check_session_checkpoint(self):
        if self._handling_session_recovery or not self.current_task_name:
            return
        now = time.monotonic()
        if now - self._last_session_checkpoint_at < 1.0:
            return
        self._last_session_checkpoint_at = now
        self._recover_session_if_needed()

    def _recover_session_if_needed(self):
        x, y, found = self.emulator_executor.find_img("buttons/relogin.png", threshold=0.78, log_missing=False)
        if not found:
            return

        relogin_interval = float(self.runtime_options.get("relogin_interval_sec", 0.0) or 0.0)
        log_util.log.print(f"[{self.emulator_name}] 检测到被顶号/未登录，等待 {relogin_interval:g} 秒后重新登录")
        self._handling_session_recovery = True
        try:
            end_time = time.time() + relogin_interval
            while self.run_status and time.time() < end_time:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(0.2, remaining))
            if not self.run_status:
                return
            self.emulator_executor.click(x, y)
            self._wait_until_relogin_disappears()
            self.prepare_current_task_state()
        finally:
            self._handling_session_recovery = False
        raise SessionRecovered()

    def _wait_until_relogin_disappears(self, timeout=70):
        end_time = time.time() + timeout
        while self.run_status and time.time() < end_time:
            _, _, found = self.emulator_executor.find_img("buttons/relogin.png", threshold=0.78, log_missing=False)
            if not found:
                return True
            time.sleep(1)
        return False

    def close(self):
        self.run_status = False
        self._emit_task_status("")

    def get_run_status(self):
        return self.run_status


_is_task_success = is_task_success
_is_task_failure = is_task_failure
