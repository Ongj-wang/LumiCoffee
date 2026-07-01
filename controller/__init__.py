"""
Lumi 机器人主程序控制器

包含状态机总控、任务队列管理和设备适配器。
"""

import logging

# 配置 controller 包日志：级别 INFO + 控制台 handler
_ctrl_logger = logging.getLogger("controller")
_ctrl_logger.setLevel(logging.INFO)
_ctrl_logger.propagate = False  # 禁止向上传播，避免 root handler 重复打印

if not _ctrl_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    _ctrl_logger.addHandler(_handler)

from controller.state_machine import StateMachine, RobotState
from controller.task_manager import TaskManager, DeliveryTask

__all__ = [
    "StateMachine",
    "RobotState",
    "TaskManager",
    "DeliveryTask",
]
