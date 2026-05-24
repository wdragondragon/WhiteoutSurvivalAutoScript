from enum import Enum, unique


@unique
class TaskStatus(Enum):
    """
    任务结束标志
    """
    NOT_STARTED = "未运行"
    SUCCESS = "成功"
    FAILED = "失败"

    def __str__(self):
        return self.value
