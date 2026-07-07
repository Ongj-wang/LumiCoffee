"""
AGV 状态查询与实时数据 API

封装与机器人状态查询相关的接口：
- 获取全局状态（/api/robot_status）
- 获取机器人信息（/api/robot_info）
- 请求实时数据推送（/api/request_data）
- 获取电源状态（/api/get_power_status）
- 获取全局路径（/api/get_planned_path）
- 获取电梯状态（/api/lift_status）
"""

from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from agv_comm.client import AGVClient


class StatusAPI:
    """状态查询与实时数据 API 模块"""

    def __init__(self, client: "AGVClient"):
        self._client = client

    # ------------------------------------------------------------------
    # 接口 3：获取机器人当前全局状态
    # ------------------------------------------------------------------

    def get_robot_status(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人当前全局状态

        返回包括：移动目标、移动状态、充电状态、急停状态、
        电量百分比、当前坐标、当前楼层、错误码等。

        建议调用频率 1-2Hz。

        Returns:
            results 字段包含：
            - move_target: 移动目标点位名称
            - move_status: idle/running/succeeded/failed/canceled
            - running_status: 详细运行状态（goto_lift/enter_lift/take_lift 等）
            - move_retry_times: 路径重试次数
            - charge_state: 充电状态（bool）
            - soft_estop_state: 软件急停状态（bool）
            - hard_estop_state: 硬件急停状态（bool）
            - estop_state: 综合急停状态（bool）
            - power_percent: 电量百分比（%）
            - current_pose: 当前位姿 {x, y, theta}
            - current_floor: 当前楼层
            - chargepile_id: 充电桩 ID（充电时）
            - error_code: 16进制错误码（8字节，非0表示异常）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/robot_status", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 4：获取机器人信息
    # ------------------------------------------------------------------

    def get_robot_info(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人基本信息

        Returns:
            results 字段包含：
            - product_id: 机器人编号（如 "WATER-xxxx-xxxxx"）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/robot_info", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 9：请求实时数据推送
    # ------------------------------------------------------------------

    def request_robot_status(
        self,
        frequency: float = 2.0,
        handler: Optional[Callable[[dict], None]] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """请求底盘以指定频率推送机器人全局状态

        成功请求后，底盘会以指定频率发送 type="callback" 的实时数据，
        可通过 client.register_callback("robot_status", handler) 注册处理器。

        Args:
            frequency: 推送频率（Hz），默认 2Hz
            handler: 可选的回调处理函数，接收 results 字典
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        if handler:
            self._client.register_callback("robot_status", handler)

        params = {"topic": "robot_status", "frequency": frequency}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/request_data", params, timeout=timeout)

    def request_human_detection(
        self,
        frequency: float = 1.0,
        handler: Optional[Callable[[dict], None]] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """请求人腿检测实时数据（需配置人腿识别模块）

        Args:
            frequency: 推送频率（Hz），默认 1Hz
            handler: 回调处理函数，接收 results 字典
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        if handler:
            self._client.register_callback("human_detection", handler)

        params = {"topic": "human_detection", "frequency": frequency}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/request_data", params, timeout=timeout)

    def request_robot_velocity(
        self,
        frequency: float = 1.0,
        handler: Optional[Callable[[dict], None]] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """请求机器人实时速度数据

        Args:
            frequency: 推送频率（Hz），默认 1Hz
            handler: 回调处理函数，接收 results 字典
                - angular: 角速度（正=左转，负=右转）
                - linear: 线速度（正=前进，负=后退）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        if handler:
            self._client.register_callback("robot_velocity", handler)

        params = {"topic": "robot_velocity", "frequency": frequency}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/request_data", params, timeout=timeout)

    def stop_data_stream(self, topic: str, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """停止指定主题的实时数据推送

        Args:
            topic: 数据主题（robot_status/human_detection/robot_velocity）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {"topic": topic, "frequency": 0}
        if uuid:
            params["uuid"] = uuid
        # 取消回调注册
        self._client.unregister_callback(topic)
        return self._client.send_command("/api/request_data", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 19：获取电源状态
    # ------------------------------------------------------------------

    def get_power_status(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取电池电源状态

        Returns:
            results 字段包含：
            - battery_capacity: 电量百分比（%）
            - battery_current: 电池电流（正=充电，负=放电）
            - battery_voltage: 电池电压（V）
            - charge_voltage: 充电电压（V）
            - charger_connected_notice: 是否正在充电（bool）
            - head_current: 上位机耗电电流
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/get_power_status", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 20：获取全局路径
    # ------------------------------------------------------------------

    def get_planned_path(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人当前规划的全局路径

        无任务时返回空路径。路径点数有限制，超过上限会平均取点。

        Returns:
            results 字段包含：
            - path: [[x1,y1], [x2,y2], ...] 路径点列表
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/get_planned_path", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 21：获取电梯状态
    # ------------------------------------------------------------------

    def get_lift_status(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人当前所乘坐电梯的状态

        注意：仅在 running_status 为 wait_lift_outside 到 exit_lift 之间可调用，
        其他时间调用会返回超时错误。

        Returns:
            results 字段包含：
            - current_floor: 电梯当前所在楼层（0表示获取楼层失败）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/lift_status", params or None, timeout=timeout)
