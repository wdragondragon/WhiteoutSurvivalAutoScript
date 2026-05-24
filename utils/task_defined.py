import os

import yaml

import log_util
import task_executor
from event_util import click_img
from task_executor import TaskExecutor, register_task
from utils.task_flow import TaskFlow
import importlib
import pkgutil

ACTION_MAP = {
    "click_img": lambda executor, params: click_img(
        executor,
        params.get("img_path"),
        params.get("desc", params.get("img_path"))
    )
}


def load_yaml_tasks(tasks_dir="tasks"):
    """
    自动扫描目录下 YAML 文件，将任务注册到 TASK_REGISTRY
    """
    for filename in os.listdir(tasks_dir):
        if not filename.endswith(".yaml") and not filename.endswith(".yml"):
            continue
        path = os.path.join(tasks_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        task_name = data["name"]
        pre_task = data.get("pre_task", [])
        param_defs = data.get("param_defs", [])

        # 动态创建任务函数
        def make_task(steps):

            def task_func(executor: TaskExecutor, params):

                flow = TaskFlow(executor)
                for s in steps:
                    action = s["action"]
                    if action == "exist_task":
                        # 每步封装 lambda
                        flow.step(
                            s["name"],
                            lambda s_=s: executor.execute_task(s_["name"], s_["params"]),  # 使用 s_ 作为默认参数名
                            retry=s.get("retry", 1)
                        )
                    else:
                        action_func = ACTION_MAP.get(s["action"])
                        if not action_func:
                            log_util.log.print(f"未定义动作: {s['action']}")
                            continue
                        # 每步封装 lambda
                        flow.step(
                            s["name"],
                            lambda s_=s: action_func(executor, s_),  # 使用 s_ 作为默认参数名
                            retry=s.get("retry", 1)
                        )
                return flow.run()

            return task_func

        # 注册任务
        register_task(task_name, pre_task=pre_task, param_defs=param_defs)(make_task(data.get("steps", [])))
        log_util.log.print(f"[YAML注册] 已注册任务: {task_name}")


# ======================
# ✅ 新增：自动加载任务方法
# ======================
def load_all_tasks(tasks_pkg_name="tasks"):
    """
    自动加载任务模块：
    - 默认扫描 'tasks' 目录下的所有 py 文件
    - 自动 import 模块，从而触发 @register_task 装饰器注册逻辑
    """
    try:
        tasks_pkg = importlib.import_module(tasks_pkg_name)
        for module_info in pkgutil.walk_packages(tasks_pkg.__path__, f"{tasks_pkg_name}."):
            importlib.import_module(module_info.name)
        load_yaml_tasks()
        # 自动加载所有 YAML 任务
        log_util.log.print(f"已加载所有任务模块，共 {len(task_executor.TASK_REGISTRY)} 个任务")
    except ModuleNotFoundError:
        log_util.log.print(f"未找到任务目录：{tasks_pkg_name}")
    except Exception as e:
        log_util.log.print(f"加载任务模块时出错：{e}")
