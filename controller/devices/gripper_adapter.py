"""
夹爪适配器（预留）

接口已定义。实际夹爪可通过以下两种方式之一控制：
1. 机械臂 IO 口：通过 arm_adapter.set_digital_output() 控制
2. 独立串口：使用 pyserial 直接通讯

待确认夹爪型号和通讯方式后替换内部实现。
"""

import logging
from typing import Dict, Any

from controller.devices import DeviceBase, DeviceState

logger = logging.getLogger("controller.devices.gripper")


class GripperAdapter(DeviceBase):
    """夹爪适配器

    当前为 stub 实现。
    若夹爪通过机械臂 IO 控制，可将 arm_adapter 传入并调用其 DO 接口。
    若夹爪有独立串口，在此处用 pyserial 实现。
    """

    def __init__(self):
        super().__init__("gripper")
        self._gripping = False

    def connect(self, port: str = None, baudrate: int = None) -> bool:
        """连接夹爪（stub）"""
        self._set_state(DeviceState.CONNECTING)
        # TODO: 对接真实串口或 IO
        self._logger.info("夹爪连接成功（stub 模式）")
        self._set_state(DeviceState.CONNECTED)
        return True

    def disconnect(self):
        """断开夹爪（stub）"""
        self._gripping = False
        self._set_state(DeviceState.DISCONNECTED)

    def open(self) -> bool:
        """打开夹爪

        Returns:
            是否成功
        """
        if not self.is_connected():
            return False
        self._logger.info("夹爪打开（stub）")
        # TODO: 发送真实开爪指令
        self._gripping = False
        return True

    def close(self) -> bool:
        """闭合夹爪

        Returns:
            是否成功
        """
        if not self.is_connected():
            return False
        self._logger.info("夹爪闭合（stub）")
        # TODO: 发送真实闭爪指令
        self._gripping = True
        return True

    def is_gripping(self) -> bool:
        """夹爪是否处于夹持状态"""
        return self._gripping

    def get_status(self) -> Dict[str, Any]:
        """获取夹爪状态"""
        base = super().get_status()
        base["gripping"] = self._gripping
        return base
