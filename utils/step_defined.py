import os

import yaml

import log_util
from event_util import click_img
from task_executor import TaskExecutor, register_task
from utils.task_flow import TaskFlow

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
        steps = data.get("steps", [])

        # 动态创建任务函数
        def make_task(steps, pre_task):
            def task_func(executor: TaskExecutor, params):
                flow = TaskFlow(executor)
                for s in steps:
                    action_func = ACTION_MAP.get(s["action"])
                    if not action_func:
                        log_util.log.print(f"未定义动作: {s['action']}")
                        continue
                    # 每步封装 lambda
                    flow.step(
                        s["name"],
                        lambda c=s: action_func(executor, s),
                        retry=s.get("retry", 1)
                    )
                return flow.run()

            return task_func

        # 注册任务
        register_task(task_name, pre_task=pre_task)(make_task(steps, pre_task))
        log_util.log.print(f"[YAML注册] 已注册任务: {task_name}")
