import time

import log_util
from StepStatus import StepStatus
from task_executor import TaskExecutor


def click_img(executor: TaskExecutor, img_path, desc):
    x, y, find = executor.emulator_executor.find_img(img_path)
    if find:
        log_util.log.print(f"[{executor.emulator_name}] {desc}")
        executor.emulator_executor.click(x, y)
        return StepStatus.FAILED
    return StepStatus.SUCCESS


def multiple_clicks(executor: TaskExecutor, images):
    for image, desc in images:
        x, y, find = executor.emulator_executor.find_img(image)
        if not find:
            return

        log_util.log.print(f"[{executor.emulator_name}] 进入{desc}")
        executor.emulator_executor.click(x, y)
        time.sleep(0.5)
    return StepStatus.SUCCESS


def wait_until(func, interval=1, timeout=30):
    """
    重复执行 func，直到其返回 True 或超时。

    :param func: 可调用对象（无参或自行闭包参数），返回 True 表示成功。
    :param interval: 每次执行的间隔（秒）
    :param timeout: 最大等待时长（秒）
    :return: True（成功） 或 False（超时）
    """
    start = time.time()
    while True:
        try:
            if func():
                return StepStatus.SUCCESS
        except Exception as e:
            # 如果 func 抛异常，可按需选择是否忽略或中断
            print(f"执行函数出错：{e}")
        elapsed = time.time() - start
        if elapsed >= timeout:
            return StepStatus.FAILED
        time.sleep(interval)
