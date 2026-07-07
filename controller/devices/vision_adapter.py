"""
视觉相机适配器（预留）

接口已定义，当前返回模拟数据。
待实际相机硬件和 SDK 到位后替换内部实现。
"""

import logging
from typing import Optional, Tuple, Dict, Any

from controller.devices import DeviceBase, DeviceState

logger = logging.getLogger("controller.devices.vision")


class VisionAdapter(DeviceBase):
    """视觉相机适配器

    负责触发拍照和检测放置目标。
    当前为 stub 实现，所有方法返回模拟数据。
    后续对接真实相机时只需替换 connect / capture / detect_target 的内部逻辑。
    """

    def __init__(self):
        super().__init__("vision")

    def connect(self, host: str = None, port: int = None) -> bool:
        """连接视觉相机（stub）"""
        self._set_state(DeviceState.CONNECTING)
        # TODO: 对接真实相机 SDK
        self._logger.info("视觉相机连接成功（stub 模式）")
        self._set_state(DeviceState.CONNECTED)
        return True

    def disconnect(self):
        """断开视觉相机（stub）"""
        self._set_state(DeviceState.DISCONNECTED)

    def capture(self) -> bool:
        """触发拍照

        Returns:
            是否成功获取图像
        """
        if not self.is_connected():
            return False
        self._logger.info("触发拍照（stub）")
        # TODO: 调用真实相机 SDK 拍照
        return True

    def detect_target(self) -> Optional[Tuple[float, float, float]]:
        """检测放置目标，返回偏差坐标

        Returns:
            (dx, dy, dtheta) 偏差量（mm + 弧度），未检测到返回 None
            stub 模式下返回 (0, 0, 0) 表示无偏差
        """
        if not self.is_connected():
            return None

        self._logger.info("检测放置目标（stub）")
        # TODO: 调用真实视觉算法
        # 模拟：无偏差
        return (0.0, 0.0, 0.0)
