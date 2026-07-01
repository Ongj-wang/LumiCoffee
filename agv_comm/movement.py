"""
AGV 移动控制 API

封装与机器人移动相关的所有指令，包括：
- 单目标点移动（/api/move marker/location）
- 多目标点巡游（/api/move markers）
- 移动取消（/api/move/cancel）
- 直接控制（/api/joy_control）
- 急停控制（/api/estop）
- 位置校正（/api/position_adjust）
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agv_comm.client import AGVClient


class MovementAPI:
    """移动控制 API 模块

    提供机器人导航移动、直接控制和急停等功能。

    移动任务状态说明（move_status 字段）：
    - idle: 空闲，未收到移动指令
    - running: 正在执行移动任务
    - succeeded: 移动任务成功完成
    - failed: 移动任务失败
    - canceled: 移动任务被取消

    running_status 详细状态：
    - idle: 空闲
    - goto_lift: 去往电梯
    - wait_lift_unlock: 等待电梯解锁
    - wait_lift_outside: 电梯外等候
    - enter_lift: 进入电梯
    - take_lift: 乘坐电梯
    - exit_lift: 出电梯
    - avoid_lift: 避让电梯
    - back_to_lift: 回到电梯
    - leave_charging_pile: 离开充电桩
    - dock_to_charging_pile: 停靠充电桩
    - running: 其它非关键状态
    """

    def __init__(self, client: "AGVClient"):
        self._client = client

    # ------------------------------------------------------------------
    # 接口 1.1：单目标点移动
    # ------------------------------------------------------------------

    def move_to_marker(
        self,
        marker: str,
        max_continuous_retries: Optional[int] = None,
        distance_tolerance: Optional[float] = None,
        theta_tolerance: Optional[float] = None,
        angle_offset: Optional[float] = None,
        yaw_goal_reverse_allowed: Optional[int] = None,
        occupied_tolerance: Optional[float] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """移动机器人到指定的 marker 点位

        Args:
            marker: 目标点位名称（需预先标记）
            max_continuous_retries: 原地最大连续重试次数（默认30次）
            distance_tolerance: 距离容差（米），到达此距离内算成功
            theta_tolerance: 角度容差（弧度），角度小于此值算成功
            angle_offset: 到达后角度偏移（弧度），范围[-π, π]
            yaw_goal_reverse_allowed: 双向停靠控制：1允许/0不允许/-1默认
            occupied_tolerance: 让步停靠距离（米），目标被占用时在附近停靠
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            包含 task_id 的响应字典
        """
        params = {"marker": marker}
        if max_continuous_retries is not None:
            params["max_continuous_retries"] = max_continuous_retries
        if distance_tolerance is not None:
            params["distance_tolerance"] = distance_tolerance
        if theta_tolerance is not None:
            params["theta_tolerance"] = theta_tolerance
        if angle_offset is not None:
            params["angle_offset"] = angle_offset
        if yaw_goal_reverse_allowed is not None:
            params["yaw_goal_reverse_allowed"] = yaw_goal_reverse_allowed
        if occupied_tolerance is not None:
            params["occupied_tolerance"] = occupied_tolerance
        if uuid:
            params["uuid"] = uuid

        return self._client.send_command("/api/move", params, timeout=timeout)

    def move_to_location(
        self,
        x: float,
        y: float,
        theta: float,
        max_continuous_retries: Optional[int] = None,
        distance_tolerance: Optional[float] = None,
        theta_tolerance: Optional[float] = None,
        angle_offset: Optional[float] = None,
        yaw_goal_reverse_allowed: Optional[int] = None,
        occupied_tolerance: Optional[float] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """移动机器人到指定坐标位置

        Args:
            x: 地图坐标系 x 值（米）
            y: 地图坐标系 y 值（米）
            theta: 目标方向角度（弧度）
            max_continuous_retries: 原地最大连续重试次数
            distance_tolerance: 距离容差（米）
            theta_tolerance: 角度容差（弧度）
            angle_offset: 到达后角度偏移（弧度）
            yaw_goal_reverse_allowed: 双向停靠控制
            occupied_tolerance: 让步停靠距离（米）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            包含 task_id 的响应字典
        """
        params = {"location": f"{x},{y},{theta}"}
        if max_continuous_retries is not None:
            params["max_continuous_retries"] = max_continuous_retries
        if distance_tolerance is not None:
            params["distance_tolerance"] = distance_tolerance
        if theta_tolerance is not None:
            params["theta_tolerance"] = theta_tolerance
        if angle_offset is not None:
            params["angle_offset"] = angle_offset
        if yaw_goal_reverse_allowed is not None:
            params["yaw_goal_reverse_allowed"] = yaw_goal_reverse_allowed
        if occupied_tolerance is not None:
            params["occupied_tolerance"] = occupied_tolerance
        if uuid:
            params["uuid"] = uuid

        return self._client.send_command("/api/move", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 1.2：多目标点巡游
    # ------------------------------------------------------------------

    def cruise(
        self,
        markers: list[str],
        count: int = 1,
        distance_tolerance: float = 0.5,
        max_continuous_retries: Optional[int] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """多目标点循环巡游

        Args:
            markers: 点位名称列表（至少2个），不支持跨楼层
            count: 巡游次数，-1 表示无限循环
            distance_tolerance: 点位到达距离容差（米），最小0.5
            max_continuous_retries: 原地最大连续重试次数（默认5）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            包含 task_id 的响应字典
        """
        if len(markers) < 2:
            raise ValueError("巡游至少需要2个点位")

        params = {
            "markers": markers,  # 会被 build_command_string 用逗号拼接
            "count": count,
            "distance_tolerance": distance_tolerance,
        }
        if max_continuous_retries is not None:
            params["max_continuous_retries"] = max_continuous_retries
        if uuid:
            params["uuid"] = uuid

        return self._client.send_command("/api/move", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 2：移动取消
    # ------------------------------------------------------------------

    def cancel_move(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """取消当前正在执行的移动任务

        取消后机器人会原地停止，进入待命状态。
        在电梯相关流程中（enter_lift/take_lift/exit_lift 等）
        不建议调用取消，以免流程出错。

        Args:
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/move/cancel", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 6：直接控制（遥控）
    # ------------------------------------------------------------------

    def joy_control(
        self,
        linear_velocity: float,
        angular_velocity: float,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """直接控制机器人线速度和角速度

        用于遥控场景，优先级高于 move 指令。
        单个命令持续时间 0.5s，可连续发送（>=2Hz）使运动连贯。

        Args:
            linear_velocity: 线速度（m/s），范围 [-0.5, 0.5]，正=前进，负=后退
            angular_velocity: 角速度（rad/s），范围 [-1.0, 1.0]，正=左转，负=右转
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {
            "angular_velocity": angular_velocity,
            "linear_velocity": linear_velocity,
        }
        if uuid:
            params["uuid"] = uuid

        return self._client.send_command("/api/joy_control", params, timeout=timeout)

    def stop(self, uuid: Optional[str] = None) -> dict:
        """停止机器人（线速度和角速度均设为0）

        Returns:
            响应字典
        """
        return self.joy_control(0.0, 0.0, uuid=uuid)

    # ------------------------------------------------------------------
    # 接口 7：急停控制
    # ------------------------------------------------------------------

    def estop(self, enable: bool = True, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """设置/解除软件急停

        急停模式下机器人可被推动。软件和硬件急停相互独立，不能相互解锁。
        软件重启或整机重启后急停状态重置为 False。

        Args:
            enable: True 进入急停，False 解除急停
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {"flag": enable}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/estop", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 8.1：指定 marker 校正位置
    # ------------------------------------------------------------------

    def adjust_position_by_marker(
        self, marker: str, uuid: Optional[str] = None, timeout: Optional[float] = None
    ) -> dict:
        """使用 marker 校正机器人当前位置

        将机器人推至 marker 标记的位置后调用此接口进行位置校正。

        Args:
            marker: 已标定的 marker 点位名称
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {"marker": marker}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/position_adjust", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 8.2：指定坐标校正位置
    # ------------------------------------------------------------------

    def adjust_position_by_pose(
        self,
        x: float,
        y: float,
        theta: float,
        floor: Optional[int] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """使用指定坐标校正机器人位置

        Args:
            x: 坐标 x
            y: 坐标 y
            theta: 方向角度
            floor: 楼层，不填默认为当前楼层
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {"x": x, "y": y, "theta": theta}
        if floor is not None:
            params["floor"] = floor
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/position_adjust_by_pose", params, timeout=timeout)
