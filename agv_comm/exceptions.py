"""
AGV 通讯模组自定义异常

根据 API 手册中的状态码定义对应的异常类：
- OK: 正常
- INVALID_REQUEST: 请求无效（参数错误）
- REQUEST_DENIED: 请求被拒绝
- UNKNOWN_ERROR: 服务器错误
- GOAL_CAN_NOT_BE_REACHED: 目标不可达
"""


class AGVError(Exception):
    """AGV 通讯模组基础异常类"""

    def __init__(self, message: str = "", status: str = "", error_message: str = ""):
        self.status = status
        self.error_message = error_message
        super().__init__(message or error_message or f"AGV错误: status={status}")


class AGVConnectionError(AGVError):
    """连接异常：TCP 连接失败、断连、重连超时"""

    pass


class AGVTimeoutError(AGVError):
    """响应超时：指令发送后在规定时间内未收到响应"""

    pass


class AGVCommandError(AGVError):
    """指令执行异常：服务器返回 UNKNOWN_ERROR"""

    pass


class AGVInvalidRequestError(AGVError):
    """无效请求：参数缺失或参数值无效"""

    pass


class AGVRequestDeniedError(AGVError):
    """请求被拒绝：系统拒绝该请求"""

    pass


class AGVGoalUnreachableError(AGVError):
    """目标不可达：路径规划失败，无法到达目标点"""

    pass


# 状态码 -> 异常类映射
STATUS_EXCEPTION_MAP = {
    "INVALID_REQUEST": AGVInvalidRequestError,
    "REQUEST_DENIED": AGVRequestDeniedError,
    "UNKNOWN_ERROR": AGVCommandError,
    "GOAL_CAN_NOT_BE_REACHED": AGVGoalUnreachableError,
}


def raise_for_status(response: dict) -> None:
    """根据响应的 status 字段抛出对应异常

    Args:
        response: API 响应字典

    Raises:
        AGVInvalidRequestError: status == "INVALID_REQUEST"
        AGVRequestDeniedError: status == "REQUEST_DENIED"
        AGVCommandError: status == "UNKNOWN_ERROR"
        AGVGoalUnreachableError: status == "GOAL_CAN_NOT_BE_REACHED"
    """
    status = response.get("status", "")
    if status == "OK":
        return

    error_msg = response.get("error_message", "")
    exc_class = STATUS_EXCEPTION_MAP.get(status, AGVCommandError)
    raise exc_class(
        message=f"[{status}] {error_msg}",
        status=status,
        error_message=error_msg,
    )
