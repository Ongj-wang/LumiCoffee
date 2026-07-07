"""
AGV 主动通知处理模块

封装 AGV 底盘主动发出的通知（notification），包括：
- 移动任务通知（01xxx）
- 电梯任务通知（04xxx）
- 状态变化通知（02xxx）
- 异常状态通知（03xxx）

通知字段说明：
- code: 通知 ID（唯一标识）
- description: 英文描述
- level: 级别（info/warning/error）
- data: 附加信息（部分通知包含）

注意：由于网络原因可能收不到通知，不建议作为流程控制的主要依据。
建议结合 /api/robot_status 的实时状态做流程判断。
"""

import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agv_comm.client import AGVClient

logger = logging.getLogger("agv_comm.notifications")


# ======================================================================
# 通知代码常量定义
# ======================================================================

class NotificationCode:
    """AGV 通知代码常量

    按 API 手册定义的通知代码分类。
    """

    # ---------- 移动任务通知 ----------
    MOVE_STARTED = "01001"             # 移动任务开始
    MOVE_FINISHED = "01002"            # 移动任务完成
    MOVE_FAILED = "01003"              # 移动任务失败（重试耗尽）
    MOVE_CANCELED = "01004"            # 移动任务被取消
    MOVE_RETRIED = "01005"             # 移动重试
    MOVE_TRAPPED = "01006"             # 机器人可能被困住
    MOVE_NO_PATH = "01007"             # 找不到可用路径（任务开始前判断）

    LEAVE_CHARGING_PILE_START = "01010"     # 开始离开充电桩
    LEAVE_CHARGING_PILE_OK = "01011"        # 离开充电桩成功
    LEAVE_CHARGING_PILE_FAIL = "01012"      # 离开充电桩失败
    LEAVE_CHARGING_PILE_RETRY = "01013"     # 重试离开充电桩

    DOCK_CHARGING_PILE_START = "01020"      # 开始自动停靠充电桩
    DOCK_CHARGING_PILE_OK = "01021"         # 停靠充电桩成功
    DOCK_CHARGING_PILE_FAIL = "01022"       # 停靠充电桩失败
    DOCK_DATA_ERROR = "01023"               # 停靠失败，数据异常
    DOCK_NO_FEATURE = "01024"               # 停靠失败，没找到特征
    DOCK_NO_POWER = "01025"                 # 回充失败，没收到上电信号
    DOCK_NO_INFRARED = "01026"              # 回充失败，没收到红外信号
    DOCK_TIMEOUT = "01027"                  # 停靠失败，超时

    ELECTRONIC_DOOR_START = "01030"         # 开始控制电子门/闸机
    ELECTRONIC_DOOR_FINISH = "01031"        # 结束控制电子门/闸机
    ELECTRONIC_DOOR_TIMEOUT = "01032"       # 控制电子门超时

    NARROW_AREA_WAIT = "01033"              # 开始狭窄区等待
    NARROW_AREA_DONE = "01034"              # 狭窄区等待结束

    CRUISE_STARTED = "01101"                # 巡游任务开始
    CRUISE_FINISHED = "01102"               # 巡游任务完成
    CRUISE_FAILED = "01103"                 # 巡游任务失败
    CRUISE_CANCELED = "01104"               # 巡游任务被取消

    TRAFFIC_BUSY = "01200"                  # 交通繁忙
    TRAPPED_UNKNOWN_AREA = "01201"          # 被困在未知区域（灰色区域）
    TRAPPED_OBSTACLE = "01202"              # 被困在障碍物附近（黑线）
    GLOBAL_PLAN_FAILED = "01203"            # 全局路径规划失败
    LOCAL_PLAN_FAILED = "01204"             # 局部路径规划失败
    NO_ENTRY_DETECTED = "01210"             # 检测到禁止通行标志

    # ---------- 电梯任务通知 ----------
    GOTO_LIFT_START = "04000"               # 开始去电梯门口
    GOTO_LIFT_OK = "04001"                  # 去电梯门口成功
    GOTO_LIFT_FAIL = "04002"                # 去电梯门口失败
    CALL_LIFT_START = "04010"               # 开始呼叫电梯
    CALL_LIFT_OK = "04011"                  # 呼叫电梯成功
    CALL_LIFT_TIMEOUT = "04013"             # 呼叫电梯超过3分钟

    TAKE_LIFT_START = "04020"               # 开始乘坐电梯
    TAKE_LIFT_OK = "04021"                  # 乘坐电梯成功
    TAKE_LIFT_TIMEOUT = "04023"             # 乘坐电梯超过3分钟

    ENTER_LIFT_START = "04030"              # 开始进电梯
    ENTER_LIFT_OK = "04031"                 # 进电梯成功
    ENTER_LIFT_FAIL = "04032"               # 进电梯失败
    ENTER_LIFT_NO_SPACE = "04033"           # 电梯空间不够，等下一趟

    AVOID_LIFT_START = "04040"              # 进电梯失败，开始回避
    AVOID_LIFT_OK = "04041"                 # 回避电梯成功

    EXIT_LIFT_START = "04050"               # 开始出电梯
    EXIT_LIFT_OK = "04051"                  # 出电梯成功
    EXIT_LIFT_FAIL = "04052"                # 出电梯失败

    BACK_LIFT_START = "04060"               # 出电梯失败，回到电梯
    BACK_LIFT_OK = "04061"                  # 回到电梯成功
    BACK_LIFT_FAIL = "04062"                # 回到电梯失败

    WAIT_LIFT_UNLOCK_START = "04070"        # 开始等待电梯解锁
    WAIT_LIFT_UNLOCK_END = "04071"          # 等待电梯解锁结束

    # ---------- 状态变化通知 ----------
    POWEROFF = "02000"                      # 将关机断电
    CHARGE_ON = "02001"                     # 进入充电状态
    CHARGE_OFF = "02002"                    # 退出充电状态
    ESTOP_ON = "02003"                      # 进入急停状态
    ESTOP_OFF = "02004"                     # 退出急停状态
    ATTITUDE_CORRECTION = "02005"           # 姿态校正被触发（可能被搬动）
    SOFTWARE_SHUTDOWN = "02006"             # 软件即将关闭
    ROBOT_MAYBE_LOST = "02010"              # 机器人可能迷路

    # ---------- 异常状态通知 ----------
    ABNORMAL_OBJECT = "03001"               # 机器人体内检测到异物

    # 任务完成/失败/取消的常用代码集合
    TASK_TERMINAL_CODES = {MOVE_FINISHED, MOVE_FAILED, MOVE_CANCELED,
                           CRUISE_FINISHED, CRUISE_FAILED, CRUISE_CANCELED}

    WARNING_CODES = {MOVE_FAILED, MOVE_TRAPPED, MOVE_NO_PATH,
                     LEAVE_CHARGING_PILE_FAIL, LEAVE_CHARGING_PILE_RETRY,
                     DOCK_CHARGING_PILE_FAIL, DOCK_DATA_ERROR, DOCK_NO_FEATURE,
                     DOCK_NO_POWER, DOCK_NO_INFRARED, DOCK_TIMEOUT,
                     ELECTRONIC_DOOR_TIMEOUT,
                     TRAPPED_UNKNOWN_AREA, TRAPPED_OBSTACLE,
                     EXIT_LIFT_FAIL, BACK_LIFT_FAIL,
                     CALL_LIFT_TIMEOUT, TAKE_LIFT_TIMEOUT,
                     ATTITUDE_CORRECTION, ROBOT_MAYBE_LOST, ABNORMAL_OBJECT}


class NotificationHandler:
    """通知监听器

    提供基于通知代码的精细化事件处理，支持：
    - 按代码注册特定处理器
    - 按类别（移动/电梯/状态/异常）注册处理器
    - 等待特定通知到达的同步方法

    使用示例：
        handler = NotificationHandler(client)
        handler.on(NotificationCode.MOVE_FINISHED, lambda n: print("到达!"))
        handler.on_warning(lambda n: print(f"警告: {n}"))
        result = handler.wait_for(NotificationCode.MOVE_FINISHED, timeout=120)
    """

    def __init__(self, client: "AGVClient"):
        self._client = client
        self._code_handlers: dict[str, list[Callable]] = {}
        self._level_handlers: dict[str, list[Callable]] = {}  # info/warning/error
        self._global_handlers: list[Callable] = []
        self._wait_events: dict[str, dict] = {}  # code -> {event, result}

        # 注册为客户端的通知处理器
        self._client.register_notification_handler(self._on_notification)

    def on(self, code: str, handler: Callable[[dict], None]) -> None:
        """注册特定通知代码的处理器

        Args:
            code: 通知代码，如 NotificationCode.MOVE_FINISHED
            handler: 处理函数，接收通知字典作为参数
        """
        if code not in self._code_handlers:
            self._code_handlers[code] = []
        self._code_handlers[code].append(handler)

    def on_level(self, level: str, handler: Callable[[dict], None]) -> None:
        """按通知级别注册处理器

        Args:
            level: 通知级别（"info"/"warning"/"error"）
            handler: 处理函数
        """
        if level not in self._level_handlers:
            self._level_handlers[level] = []
        self._level_handlers[level].append(handler)

    def on_warning(self, handler: Callable[[dict], None]) -> None:
        """注册 warning 级别通知处理器"""
        self.on_level("warning", handler)

    def on_info(self, handler: Callable[[dict], None]) -> None:
        """注册 info 级别通知处理器"""
        self.on_level("info", handler)

    def on_all(self, handler: Callable[[dict], None]) -> None:
        """注册全局通知处理器（所有通知都会触发）"""
        self._global_handlers.append(handler)

    def wait_for(self, code: str, timeout: float = 60.0) -> Optional[dict]:
        """同步等待特定通知到达

        Args:
            code: 要等待的通知代码
            timeout: 超时时间（秒）

        Returns:
            通知字典，超时返回 None
        """
        import threading

        event = threading.Event()
        wait_info = {"event": event, "result": None}
        self._wait_events[code] = wait_info

        event.wait(timeout=timeout)

        result = wait_info.get("result")
        self._wait_events.pop(code, None)
        return result

    def wait_for_any(self, codes: list[str], timeout: float = 60.0) -> Optional[dict]:
        """同步等待任意一个通知到达

        Args:
            codes: 通知代码列表
            timeout: 超时时间（秒）

        Returns:
            最先到达的通知字典，超时返回 None
        """
        import threading

        event = threading.Event()
        wait_info = {"event": event, "result": None}

        for code in codes:
            self._wait_events[code] = wait_info

        event.wait(timeout=timeout)

        result = wait_info.get("result")
        for code in codes:
            self._wait_events.pop(code, None)
        return result

    def _on_notification(self, data: dict) -> None:
        """内部通知分发处理"""
        code = data.get("code", "")
        level = data.get("level", "")
        description = data.get("description", "")

        logger.info(
            "收到通知 [%s] level=%s desc=%s data=%s",
            code, level, description, data.get("data", {})
        )

        # 触发等待事件
        if code in self._wait_events:
            wait_info = self._wait_events[code]
            wait_info["result"] = data
            wait_info["event"].set()

        # 触发特定代码处理器
        for handler in self._code_handlers.get(code, []):
            try:
                handler(data)
            except Exception as e:
                logger.error("通知处理器异常 (code=%s): %s", code, e)

        # 触发级别处理器
        for handler in self._level_handlers.get(level, []):
            try:
                handler(data)
            except Exception as e:
                logger.error("通知级别处理器异常 (level=%s): %s", level, e)

        # 触发全局处理器
        for handler in self._global_handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error("全局通知处理器异常: %s", e)
