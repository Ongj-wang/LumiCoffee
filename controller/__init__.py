"""
Lumi 机器人主程序控制器

包含状态机总控、任务队列管理和设备适配器。
"""

import logging

# 设置 controller 包级别日志为 INFO
logging.getLogger("controller").setLevel(logging.INFO)

from controller.state_machine import StateMachine, RobotState
from controller.task_manager import TaskManager, DeliveryTask

__all__ = [
    "StateMachine",
    "RobotState",
    "TaskManager",
    "DeliveryTask",
]
