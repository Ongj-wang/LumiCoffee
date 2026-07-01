"""
设备适配器基础模块

定义所有设备适配器的公共接口和状态枚举。
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger("controller.devices")


class DeviceState(Enum):
    """设备连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class DeviceBase(ABC):
    """设备适配器抽象基类

    所有设备适配器（AGV、机械臂、视觉、夹爪）均需继承此类，
    实现统一的连接管理和状态查询接口。
    """

    def __init__(self, name: str):
        self._name = name
        self._state = DeviceState.DISCONNECTED
        self._error_msg: Optional[str] = None
        self._logger = logging.getLogger(f"controller.devices.{name}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> DeviceState:
        return self._state

    @property
    def error_msg(self) -> Optional[str]:
        return self._error_msg

    def is_connected(self) -> bool:
        return self._state == DeviceState.CONNECTED

    def _set_state(self, state: DeviceState, error_msg: Optional[str] = None):
        old = self._state
        self._state = state
        self._error_msg = error_msg
        if state == DeviceState.ERROR:
            self._logger.error(f"[{self._name}] {old.value} -> ERROR: {error_msg}")
        else:
            self._logger.info(f"[{self._name}] {old.value} -> {state.value}")

    @abstractmethod
    def connect(self) -> bool:
        """连接设备，返回是否成功"""
        ...

    @abstractmethod
    def disconnect(self):
        """断开设备连接"""
        ...

    def get_status(self) -> Dict[str, Any]:
        """获取设备状态摘要"""
        return {
            "name": self._name,
            "state": self._state.value,
            "error": self._error_msg,
        }

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self._name!r} state={self._state.value}>"
