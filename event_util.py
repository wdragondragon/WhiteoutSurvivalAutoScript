import time

import log_util
from task_executor import TaskExecutor


def multiple_clicks(executor: TaskExecutor, images):
    for image, desc in images:
        x, y, find = executor.emulator_executor.find_img(image)
        if not find:
            return

        log_util.log.print(f"[{executor.emulator_name}] 进入{desc}")
        executor.emulator_executor.click(x, y)
        time.sleep(0.5)
