"""
JAKA Lumi AGV 底盘通讯模组

基于 JAKA Lumi 底盘软件 API 手册开发的 Python 通讯模组，
通过 TCP Socket 与 AGV 底盘进行通讯，提供完整的 API 封装。

协议说明：
- 连接方式：TCP 客户端
- 默认服务器地址：192.168.10.10:31001
- 请求格式：类 URL 字符串，如 /api/move?marker=target_name
- 响应格式：JSON
- 响应类型：response（指令响应）、callback（实时数据回调）、notification（主动通知）

使用示例：
    from agv_comm import AGVClient

    client = AGVClient(host="192.168.10.10", port=31001)
    client.connect()
    status = client.status.get_robot_status()
    client.movement.move_to_marker("room_205")
    client.disconnect()
"""

__version__ = "1.0.0"
__author__ = "LumiCoffee"

from agv_comm.client import AGVClient
from agv_comm.exceptions import (
    AGVError,
    AGVConnectionError,
    AGVTimeoutError,
    AGVCommandError,
    AGVInvalidRequestError,
    AGVRequestDeniedError,
    AGVGoalUnreachableError,
)
from agv_comm.notifications import NotificationHandler

__all__ = [
    "AGVClient",
    "AGVError",
    "AGVConnectionError",
    "AGVTimeoutError",
    "AGVCommandError",
    "AGVInvalidRequestError",
    "AGVRequestDeniedError",
    "AGVGoalUnreachableError",
    "NotificationHandler",
]
