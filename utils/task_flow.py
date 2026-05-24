
import time
import log_util
from TaskStatus import TaskStatus


class TaskStep:
    """
    单步任务
    """

    def __init__(self, name, action, retry=1, timeout=None):
        self.name = name
        self.action = action
        self.retry = retry
        self.timeout = timeout

    def run(self):
        """
        执行任务步骤，返回 TaskStatus
        """
        start = time.time()
        for attempt in range(self.retry):
            try:
                result = self.action()
                if isinstance(result, TaskStatus):
                    if result == TaskStatus.SUCCESS:
                        return TaskStatus.SUCCESS
                elif result:
                    return TaskStatus.SUCCESS
            except Exception as e:
                log_util.log.print(f"步骤 [{self.name}] 第 {attempt + 1} 次执行出错: {e}")
            if self.timeout and (time.time() - start) >= self.timeout:
                log_util.log.print(f"步骤 [{self.name}] 超时")
                return TaskStatus.FAILED
            time.sleep(0.5)  # 每次重试间隔
        log_util.log.print(f"步骤 [{self.name}] 执行失败")
        return TaskStatus.FAILED


class TaskFlow:
    """
    支持链式 DSL 定义任务流
    """

    def __init__(self, executor):
        self.executor = executor
        self.steps = []

    def step(self, name, action, retry=1, timeout=None):
        """
        添加一步操作
        """
        self.steps.append(TaskStep(name, action, retry, timeout))
        return self  # 链式调用

    def run(self):
        """
        执行整个任务流
        """
        for step in self.steps:
            status = step.run()
            if status != TaskStatus.SUCCESS:
                return status
        return TaskStatus.SUCCESS
