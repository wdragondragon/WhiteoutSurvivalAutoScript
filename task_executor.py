# emulator_executor.py
import log_util
from emulator_executor import EmulatorExecutor

TASK_REGISTRY = {}


def register_task(name, param_defs=None):
    def decorator(func):
        TASK_REGISTRY[name] = {
            "func": func,
            "param_defs": param_defs or []
        }
        return func

    return decorator


class TaskExecutor:
    def __init__(self, emulator_name=None, emulator_executor: EmulatorExecutor = None):
        if emulator_name is None:
            self.emulator_name = emulator_executor.name
        else:
            self.emulator_name = emulator_name
        self.emulator_executor = emulator_executor

    def execute_task(self, task_name, params):
        task_info = TASK_REGISTRY.get(task_name)
        if not task_info:
            log_util.log.print(f"任务 {task_name} 未注册")
            return False
        func = task_info["func"]
        try:
            log_util.log.print(f"[{self.emulator_name}] 执行任务: {task_name}，参数: {params}")
            return func(self, params)
        except Exception as e:
            log_util.log.print(f"执行任务 {task_name} 出错: {e}")
            return False

    def execute_task_config(self, task_config):
        for task in task_config.get("tasks", []):
            name = task["name"]
            params = task.get("params", {})
            if not self.execute_task(name, params):
                log_util.log.print(f"任务 {name} 执行失败，停止后续任务")
                break


@register_task("点击按钮", param_defs=[
    {"name": "template_path", "type": "str", "default": "buttons/button1.png", "desc": "按钮模板路径"},
    {"name": "threshold", "type": "float", "default": 0.85, "desc": "匹配阈值(0-1)"}
])
def task_click_button(executor: TaskExecutor, params):
    # 模拟执行点击操作
    template = params.get("template_path")
    threshold = float(params.get("threshold", 0.85))
    executor.emulator_executor.find_and_click_button(template, threshold)
    log_util.log.print(f"{executor.emulator_name} 执行点击，模板: {template}，阈值: {threshold}")
    return True


@register_task("等待", param_defs=[
    {"name": "seconds", "type": "int", "default": 1, "desc": "等待秒数"}
])
def task_wait(executor: TaskExecutor, params):
    seconds = int(params.get("seconds", 1))
    log_util.log.print(f"{executor.emulator_name} 等待 {seconds} 秒")
    import time
    time.sleep(seconds)
    return True


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
