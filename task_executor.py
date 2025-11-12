# emulator_executor.py
import time

import log_util
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
            if not self.execute_task(name, params):
                log_util.log.print(f"任务 {name} 执行失败，停止后续任务")
                break

    def close(self):
        self.run_status = False

    def get_run_status(self):
        return self.run_status


@register_task("自动打开游戏", param_defs=[])
def check_open(executor: TaskExecutor, params):
    x, y, find = executor.emulator_executor.find_img("buttons/button1.png")
    if find:
        log_util.log.print(f"[{executor.emulator_name}] 识别到游戏未打开，打开游戏")
        executor.emulator_executor.click(x, y)
    return True


@register_task("重新登录", param_defs=[{
    "name": "interval", "type": "int", "default": 0, "desc": "重上等待时间/秒"
}])
def re_login(executor: TaskExecutor, params):
    x, y, find = executor.emulator_executor.find_img("buttons/relogin.png")
    if find:
        inv = params.get("interval", 0)
        log_util.log.print(f"[{executor.emulator_name}] 识别到游戏未登录，等待{inv}秒后重新登录")
        time.sleep(inv)
        log_util.log.print(f"[{executor.emulator_name}] 执行游戏重新登录")
        executor.emulator_executor.click(x, y)
    return True


@register_task("返回主页", pre_task=["自动打开游戏", "重新登录"])
def back_home(executor: TaskExecutor, params):
    back_image_path = ["buttons/back.png", "buttons/back2.png", "buttons/back3.png", "buttons/back4.png",
                       "buttons/back5.png"]
    x, y, find = executor.emulator_executor.find_img(back_image_path)
    while find:
        log_util.log.print(f"[{executor.emulator_name}] 点击返回")
        executor.emulator_executor.click(x, y)
        time.sleep(0.5)
        x, y, find = executor.emulator_executor.find_img(back_image_path)
    return True


@register_task("打开联盟", pre_task=["自动打开游戏", "重新登录"])
def click_lm(executor: TaskExecutor, params):
    back_home(executor, params)
    x, y, find = executor.emulator_executor.find_img("buttons/lm.png")
    if find:
        log_util.log.print(f"[{executor.emulator_name}] 进入联盟页")
        executor.emulator_executor.click(x, y)
    return True


@register_task("建棋", pre_task=["打开联盟"])
def click_lm(executor: TaskExecutor, params):
    import event_util
    event_util.multiple_clicks(executor, [
        ("buttons/lmld.png", "进入联盟领地"),
        ("buttons/ldjz.png", "进入领地建筑"),
        ("buttons/jqqw.png", "前往建旗"),
        ("buttons/jz.png", "点击建造"),
        ("buttons/pqbd.png", "派遣部队"),
        ("buttons/cz.png", "出征"),
    ])
    return True


@register_task("自动洗练")
def pet_page(executor: TaskExecutor, params):
    region = (290, 225, 324, 250)
    i = 0
    while executor.run_status:
        _, _, up = executor.emulator_executor.find_img("buttons/up.png", region=region, threshold=0.75)
        _, _, down = executor.emulator_executor.find_img("buttons/down.png", region=region, threshold=0.65)
        _, _, zero = executor.emulator_executor.find_img("buttons/add_zero.png", region=(261, 231, 294, 250),
                                                         threshold=0.60)
        if up:
            log_util.log.print(f"[{executor.emulator_name}] 洗练替换")
            executor.emulator_executor.find_and_click_button("buttons/replaced.png")
        elif down or zero:
            log_util.log.print(f"[{executor.emulator_name}] 洗练重洗")
            executor.emulator_executor.find_and_click_button("buttons/re_baptize.png")
            time.sleep(0.2)
        else:
            executor.emulator_executor.find_and_click_button("buttons/baptize.png")
        i += 1
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
