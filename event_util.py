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


def multiple_clicks(
        executor: TaskExecutor,
        images,
        click_timeout=5,
        check_interval=1,
        wait_miss=False,
        on_timeout=None
):
    """
    顺序点击图片列表，点击后等待图片消失
    每轮循环自动等待当前图片出现，点击，等待消失，进入下一轮

    :param wait_miss: 是否等待上张图片消失
    :param executor: TaskExecutor
    :param images: [ (image_path, desc), ... ]
    :param click_timeout: 点击等待出现/消失的最大时长
    :param check_interval: 检测间隔，秒
    :param on_timeout: 超时回调函数，接收参数 (executor, image_path, desc)
    :return: TaskStatus.SUCCESS / TaskStatus.FAILED
    """
    for image, desc in images:
        # 1. 等待图片出现
        start_time = time.time()
        while True:
            x, y, found = executor.emulator_executor.find_img(image)
            if found:
                log_util.log.print(f"[{executor.emulator_name}] 点击 {desc}")
                executor.emulator_executor.click(x, y)
                break
            if time.time() - start_time > click_timeout:
                log_util.log.print(f"[{executor.emulator_name}] {desc} 未出现，超时")
                if on_timeout:
                    on_timeout(executor, image, desc)
                return StepStatus.FAILED
            time.sleep(check_interval)

        # 2. 等待图片消失
        if wait_miss:
            start_time = time.time()
            while True:
                _, _, still_found = executor.emulator_executor.find_img(image)
                if not still_found:
                    break
                if time.time() - start_time > click_timeout:
                    log_util.log.print(f"[{executor.emulator_name}] {desc} 未消失，超时")
                    if on_timeout:
                        on_timeout(executor, image, desc)
                    return StepStatus.FAILED
                time.sleep(check_interval)

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
