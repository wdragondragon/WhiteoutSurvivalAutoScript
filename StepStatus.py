from enum import Enum, unique


@unique
class StepStatus(Enum):
    """
    任务结束标志
    """
    SUCCESS = "成功"
    FAILED = "失败"

    def __str__(self):
        return self.value
