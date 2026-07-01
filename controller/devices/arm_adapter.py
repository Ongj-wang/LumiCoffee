"""
JAKA 机械臂适配器

封装 JK_SDK.RC，提供面向状态机的高层接口。
负责连接管理、运动控制、IO 控制和状态查询。
"""

import time
import logging
from typing import Optional, List, Dict, Any

from controller.devices import DeviceBase, DeviceState
from controller import config

logger = logging.getLogger("controller.devices.arm")


class ArmAdapter(DeviceBase):
    """JAKA 机械臂适配器

    封装 JK_SDK.RC 类，将 SDK 调用转换为状态机可直接使用的同步接口。
    所有运动方法默认阻塞执行（等待到位后返回）。

    注：JK_SDK.RC 的所有方法返回元组，ret[0] == 0 表示调用成功。
    """

    @staticmethod
    def _is_success(ret) -> bool:
        """判断 SDK 返回值是否成功（ret[0] == 0）"""
        if isinstance(ret, tuple) and len(ret) > 0:
            return ret[0] == 0
        return False

    def __init__(self):
        super().__init__("arm")
        self._robot = None

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(self, ip: str = None) -> bool:
        """连接机械臂控制器

        Args:
            ip: 控制器 IP 地址，默认取 config.ARM_IP
        """
        ip = ip or config.ARM_IP

        self._set_state(DeviceState.CONNECTING)
        try:
            import sys
            import os
            # 确保 JK_SDK 在 Python 路径中
            sdk_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "JK_SDK")
            if os.path.exists(sdk_dir) and sdk_dir not in sys.path:
                sys.path.insert(0, os.path.dirname(sdk_dir))

            from JK_SDK import RC
            self._robot = RC(ip)
            ret = self._robot.login()
            self._logger.info(f"login 返回: {ret}")

            if not self._is_success(ret):
                self._set_state(DeviceState.ERROR, f"登录失败: {ret}")
                return False

            self._set_state(DeviceState.CONNECTED)
            self._logger.info(f"机械臂连接成功: {ip}")
            return True
        except Exception as e:
            self._set_state(DeviceState.ERROR, f"连接失败: {e}")
            return False

    def disconnect(self):
        """断开机械臂连接"""
        if self._robot:
            try:
                self._robot.logout()
            except Exception as e:
                self._logger.warning(f"logout 异常: {e}")
            self._robot = None
        self._set_state(DeviceState.DISCONNECTED)

    # ------------------------------------------------------------------
    # 电源与使能
    # ------------------------------------------------------------------

    def power_on(self) -> bool:
        """机械臂上电"""
        if not self.is_connected():
            return False
        try:
            ret = self._robot.power_on()
            self._logger.info(f"power_on 返回: {ret}")
            return self._is_success(ret)
        except Exception as e:
            self._logger.error(f"上电失败: {e}")
            return False

    def enable(self) -> bool:
        """使能机械臂"""
        if not self.is_connected():
            return False
        try:
            ret = self._robot.enable_robot()
            self._logger.info(f"enable_robot 返回: {ret}")
            return self._is_success(ret)
        except Exception as e:
            self._logger.error(f"使能失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 运动控制
    # ------------------------------------------------------------------

    def move_to_joint(self, joint_pos: List[float], speed: float = None) -> bool:
        """关节运动到目标角度（阻塞）

        Args:
            joint_pos: 6 个关节角度（度），如 [0, 30, -60, 0, 90, 0]
            speed: 速度比例（0.0-1.0），默认取 config.ARM_JOINT_MOVE_SPEED
        """
        if not self.is_connected():
            return False

        speed = speed or config.ARM_JOINT_MOVE_SPEED
        self._logger.info(f"关节运动: {joint_pos}, speed={speed}")

        try:
            # move_mode=0 (关节插值), is_block=True (阻塞等待到位)
            ret = self._robot.joint_move(joint_pos, 0, True, speed)
            self._logger.info(f"joint_move 返回: {ret}")
            return self._is_success(ret)
        except Exception as e:
            self._logger.error(f"关节运动失败: {e}")
            self._set_state(DeviceState.ERROR, f"关节运动异常: {e}")
            return False

    def move_to_pose(self, pose: List[float], move_mode:int =0, speed: float = None) -> bool:
        """笛卡尔直线运动到目标位姿（阻塞）

        Args:
            pose: TCP 目标位姿 [x, y, z, rx, ry, rz]（mm + 弧度）
            speed: 速度
        """
        if not self.is_connected():
            return False

        speed = speed or config.ARM_LINEAR_MOVE_SPEED
        self._logger.info(f"直线运动: {pose}, speed={speed}")

        try:
            # is_block=True
            ret = self._robot.linear_move(pose, move_mode, True, speed)
            self._logger.info(f"linear_move 返回: {ret}")
            return self._is_success(ret)
        except Exception as e:
            self._logger.error(f"直线运动失败: {e}")
            self._set_state(DeviceState.ERROR, f"直线运动异常: {e}")
            return False

    def go_home(self) -> bool:
        """回到预设安全位"""
        self._logger.info("机械臂回到安全位")
        return self.move_to_joint(config.ARM_HOME_JOINTS)

    def abort(self) -> bool:
        """中止当前运动"""
        if not self.is_connected():
            return False
        try:
            ret = self._robot.motion_abort()
            self._logger.info(f"motion_abort 返回: {ret}")
            return self._is_success(ret)
        except Exception as e:
            self._logger.error(f"中止运动失败: {e}")
            return False

    # ------------------------------------------------------------------
    # IO 控制（可用于夹爪）
    # ------------------------------------------------------------------

    def set_digital_output(self, index: int, value: bool, iotype: int = 0) -> bool:
        """设置数字 IO 输出（可用于控制夹爪）

        Args:
            index: IO 口索引号
            value: True=高电平/开，False=低电平/关
            iotype: IO 类型，0=控制器 IO，1=工具 IO
        """
        if not self.is_connected():
            return False
        try:
            val = 1 if value else 0
            ret = self._robot.set_digital_output(iotype, index, val)
            self._logger.info(f"DO[{iotype}][{index}] = {val}, 返回: {ret}")
            return self._is_success(ret)
        except Exception as e:
            self._logger.error(f"设置 DO 失败: {e}")
            return False

    def get_digital_input(self, index: int, iotype: int = 0) -> Optional[int]:
        """读取数字 IO 输入"""
        if not self.is_connected():
            return None
        try:
            ret = self._robot.get_digital_input(iotype, index)
            if self._is_success(ret):
                return ret[1] if len(ret) > 1 else 0
            self._logger.warning(f"读取 DI 失败: {ret}")
            return None
        except Exception as e:
            self._logger.error(f"读取 DI 失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_current_pose(self) -> Optional[List[float]]:
        """获取当前 TCP 位姿 [x, y, z, rx, ry, rz]"""
        if not self.is_connected():
            return None
        try:
            ret = self._robot.get_actual_tcp_position()
            if self._is_success(ret):
                return ret[1] if len(ret) > 1 else None
            self._logger.warning(f"获取 TCP 位姿失败: {ret}")
            return None
        except Exception as e:
            self._logger.error(f"获取 TCP 位姿失败: {e}")
            return None

    def get_joint_positions(self) -> Optional[List[float]]:
        """获取当前关节角度"""
        if not self.is_connected():
            return None
        try:
            ret = self._robot.get_actual_joint_position()
            if self._is_success(ret):
                return ret[1] if len(ret) > 1 else None
            self._logger.warning(f"获取关节角度失败: {ret}")
            return None
        except Exception as e:
            self._logger.error(f"获取关节角度失败: {e}")
            return None

    def get_robot_state(self) -> Optional[Any]:
        """获取机械臂状态"""
        if not self.is_connected():
            return None
        try:
            ret = self._robot.get_robot_state()
            if self._is_success(ret):
                return ret[1] if len(ret) > 1 else None
            self._logger.warning(f"获取机器人状态失败: {ret}")
            return None
        except Exception as e:
            self._logger.error(f"获取机器人状态失败: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """获取机械臂状态摘要"""
        base = super().get_status()
        if not self.is_connected():
            return base

        base["joint_positions"] = self.get_joint_positions()
        base["tcp_pose"] = self.get_current_pose()
        base["robot_state"] = self.get_robot_state()
        return base
