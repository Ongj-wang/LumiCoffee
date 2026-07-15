"""
AGV 底盘适配器

封装 agv_comm.AGVClient，提供面向状态机的高层接口。
负责连接管理、移动控制、状态查询和异常通知。
"""

import time
import logging
from typing import Optional, Callable, Dict, Any

from controller.devices import DeviceBase, DeviceState
from controller import config

logger = logging.getLogger("controller.devices.agv")






class AGVAdapter(DeviceBase):
    """AGV 底盘适配器

    封装 agv_comm.AGVClient，将底层 TCP 通讯和 API 调用
    转换为状态机可直接使用的同步接口。
    """

    def __init__(self):
        super().__init__("agv")
        self._client = None
        self._notification_callback: Optional[Callable] = None

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(self, host: str = None, port: int = None) -> bool:
        """连接 AGV 底盘

        Args:
            host: AGV IP 地址，默认取 config.AGV_HOST
            port: AGV 端口，默认取 config.AGV_PORT
        """
        host = host or config.AGV_HOST
        port = port or config.AGV_PORT

        self._set_state(DeviceState.CONNECTING)
        try:
            from agv_comm import AGVClient
            self._client = AGVClient(host=host, port=port)
            self._client.connect()
            self._set_state(DeviceState.CONNECTED)
            self._logger.info(f"AGV 连接成功: {host}:{port}")
            return True
        except Exception as e:
            self._set_state(DeviceState.ERROR, f"连接失败: {e}")
            return False

    def _ensure_client(self) -> bool:
        if self._client is not None:
            return True

        try:
            from agv_comm import AGVClient
            self._client = AGVClient(host=config.AGV_HOST, port=config.AGV_PORT)

            # 如果底层 AGVClient 仍然是 TCP 长连接，就这里 connect
            # 如果你后续把 AGVClient 改成无连接发送，这里就不需要 connect
            self._client.connect()

            self._set_state(DeviceState.CONNECTED)
            return True
        except Exception as e:
            self._set_state(DeviceState.ERROR, f"AGV 客户端准备失败: {e}")
            return False


    def disconnect(self):
        """断开 AGV 连接"""
        if self._client:
            try:
                self._client.disconnect()
            except Exception as e:
                self._logger.warning(f"断开连接时异常: {e}")
            self._client = None
        self._set_state(DeviceState.DISCONNECTED)

    # ------------------------------------------------------------------
    # 移动控制
    # ------------------------------------------------------------------

    def move_to(self, target_name: str, timeout: float = None) -> bool:
        """前往目标点位（阻塞等待完成）

        Args:
            target_name: 目标 marker 点位名称
            timeout: 超时时间（秒），默认使用 NAVIGATION_TIMEOUT

        Returns:
            是否成功到达目标
        """
        if not self._ensure_client():
         print("not ._ensure_client")
         return False
        timeout = timeout or config.NAVIGATION_TIMEOUT
        self._logger.info(f"开始移动至: {target_name}")

        try:
            # 发送移动指令
            resp = self._client.movement.move_to_marker(target_name, timeout=10)
            task_id = resp.get("results", {}).get("task_id")
            if not task_id:
                self._logger.error(f"移动指令无 task_id: {resp}")
                return False

            # 轮询等待移动完成
            start = time.time()
            while time.time() - start < timeout:
                status = self._client.status.get_robot_status(timeout=5)
                results = status.get("results", {})
                move_status = results.get("move_status", "")
                print("move_to:move_status",move_status)
                if move_status == "succeeded":
                    self._logger.info(f"已到达目标: {target_name}")
                    return True
                elif move_status in ("failed", "canceled"):
                    self._logger.error(f"移动失败: {move_status}")
                    return False

                time.sleep(0.5)

            self._logger.error(f"移动超时: {target_name} ({timeout}s)")
            return False

        except Exception as e:
            self._set_state(DeviceState.ERROR, f"移动异常: {e}")
            return False

    def move_to_floor(self, floor: int, timeout: float = None) -> bool:
        """乘梯前往指定楼层

        通过 AGV 内置的电梯联动功能实现，
        AGV 会自动呼叫电梯、进入、乘梯、出电梯。

        Args:
            floor: 目标楼层号
            timeout: 超时时间（秒），默认使用 ELEVATOR_TIMEOUT + NAVIGATION_TIMEOUT
        """
        target = f"floor_{floor}"
        timeout = timeout or (config.ELEVATOR_TIMEOUT + config.NAVIGATION_TIMEOUT)
        self._logger.info(f"乘梯前往 {floor} 楼")
        return self.move_to(target, timeout=timeout)

    def cancel_move(self) -> bool:
        """取消当前移动任务"""
        if not self._ensure_client():
            return False
        try:
            self._client.movement.cancel_move(timeout=5)
            self._logger.info("移动已取消")
            return True
        except Exception as e:
            self._logger.error(f"取消移动失败: {e}")
            return False

    def emergency_stop(self, enable: bool = True) -> bool:
        """设置/解除急停"""
        if not self._ensure_client():
            return False
        try:
            self._client.movement.estop(enable=enable, timeout=5)
            action = "急停" if enable else "解除急停"
            self._logger.info(f"AGV {action}")
            return True
        except Exception as e:
            self._logger.error(f"急停操作失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """获取 AGV 完整状态"""
        base = super().get_status()
        if not self._ensure_client():
            return base

        try:
            resp = self._client.status.get_robot_status(timeout=5)
            results = resp.get("results", {})
            base.update({
                "move_status": results.get("move_status", "unknown"),
                "running_status": results.get("running_status", ""),
                "battery": results.get("power_percent", 0),
                "current_floor": results.get("current_floor", 1),
                "current_pose": results.get("current_pose", {}),
                "charge_state": results.get("charge_state", False),
                "estop": results.get("estop_state", False),
                "error_code": results.get("error_code", "0"),
            })
        except Exception as e:
            self._logger.warning(f"获取状态失败: {e}")
            base["move_status"] = "unknown"

        return base

    def get_battery(self) -> float:
        """获取当前电量百分比（%）"""
        status = self.get_status()
        return status.get("battery", 0)

    def get_current_position(self) -> Dict[str, Any]:
        """获取当前位置信息（楼层 + 位姿）"""
        status = self.get_status()
        return {
            "floor": status.get("current_floor", 1),
            "pose": status.get("current_pose", {"x": 0, "y": 0, "theta": 0}),
        }

    def is_moving(self) -> bool:
        """AGV 是否正在执行移动任务"""
        status = self.get_status()
        return status.get("move_status") == "running"

    # ------------------------------------------------------------------
    # 通知回调
    # ------------------------------------------------------------------

    def register_notification_handler(self, callback: Callable):
        """注册 AGV 异常通知回调

        Args:
            callback: 回调函数，参数为通知字典 {code, level, description, data}
        """
        self._notification_callback = callback
        if self._client:
            self._client.register_notification_handler(callback)
            self._logger.info("已注册 AGV 通知回调")
    
    def AGV_Back(self,AGV_linear_velocity: float, AGV_angular_velocity: float, AGV_uuid: Optional[str] = None,AGV_timeout: Optional[float] = None):
        """
        AGV_linear_velocity 范围必须是负数，范围是-0.5到0.5m/s ， 时间固定为0.5s  ,调速度来设置距离[-0.25m , 0.25m]
        """
        return  self._client.movement.joy_control(AGV_linear_velocity, AGV_angular_velocity)
