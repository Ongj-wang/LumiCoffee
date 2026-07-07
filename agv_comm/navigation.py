"""
AGV 地图与路径规划 API

封装与地图和路径相关的接口：
- 获取地图列表（/api/map/list）
- 设置当前地图（/api/map/set_current_map）
- 获取当前地图（/api/map/get_current_map）
- 获取地图列表详情（/api/map/list_info）
- 查询附近可到点（/api/map/accessible_point_query）
- 查询障碍物距离（/api/map/distance_probe）
- 两点间路径规划（/api/make_plan）
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agv_comm.client import AGVClient


class NavigationAPI:
    """地图与路径规划 API 模块"""

    def __init__(self, client: "AGVClient"):
        self._client = client

    # ------------------------------------------------------------------
    # 接口 14.1：获取地图列表
    # ------------------------------------------------------------------

    def get_map_list(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人中所有地图名称和楼层

        Returns:
            results 字段为字典，如 {"map_name_1": [1,2,3,4,5], "map_name_2": [10]}
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/map/list", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 14.2：设置当前地图
    # ------------------------------------------------------------------

    def set_current_map(
        self,
        map_name: str,
        floor: int,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """设置机器人当前使用的地图和楼层

        注意：设置成功后会重启 water 服务，可能收不到 response。

        Args:
            map_name: 地图名称
            floor: 楼层
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典（可能收不到）
        """
        params = {"map_name": map_name, "floor": floor}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/map/set_current_map", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 14.3：获取当前地图
    # ------------------------------------------------------------------

    def get_current_map(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人当前地图信息

        Returns:
            results 字段包含：
            - map_name: 地图名称
            - floor: 当前楼层
            - info: 地图详情（分辨率、宽高、左下角坐标等）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/map/get_current_map", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 14.4：获取地图列表详情
    # ------------------------------------------------------------------

    def get_map_list_info(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取所有地图的详细信息

        Returns:
            results 字段为字典，包含每张地图所有楼层的分辨率、宽高、坐标等信息。
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/map/list_info", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 14.5：查询附近可到点
    # ------------------------------------------------------------------

    def query_accessible_point(
        self,
        x: float,
        y: float,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """在目标点附近寻找可到达的位置

        根据传感器探测结果，在目标点附近寻找当前无障碍的可到点。
        仅适用于当前地图的当前楼层。

        Args:
            x: 目标点 x 坐标（米）
            y: 目标点 y 坐标（米）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            results 字段包含 position: {x, y}
        """
        params = {"x": x, "y": y}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/map/accessible_point_query", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 14.6：查询障碍物距离
    # ------------------------------------------------------------------

    def probe_distance(
        self,
        x: float,
        y: float,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """查询目标点到静态地图障碍和传感器探测障碍物的距离

        Args:
            x: 目标点 x 坐标（米）
            y: 目标点 y 坐标（米）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            results 字段包含 env_dist:
            - obstacle: 到传感器探测障碍的距离（-1表示太远无法获取）
            - static: 到静态地图障碍的距离
        """
        params = {"x": x, "y": y}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/map/distance_probe", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 22：两点间路径规划
    # ------------------------------------------------------------------

    def make_plan(
        self,
        start_x: float,
        start_y: float,
        start_floor: int,
        goal_x: float,
        goal_y: float,
        goal_floor: int,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """规划两点间的最短路径

        Args:
            start_x: 起始位置 x 坐标
            start_y: 起始位置 y 坐标
            start_floor: 起始楼层
            goal_x: 目标位置 x 坐标
            goal_y: 目标位置 y 坐标
            goal_floor: 目标楼层
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            results 字段包含：
            - distance: 路径长度（米）

        Raises:
            AGVGoalUnreachableError: 目标不可达
        """
        params = {
            "start_x": start_x,
            "start_y": start_y,
            "start_floor": start_floor,
            "goal_x": goal_x,
            "goal_y": goal_y,
            "goal_floor": goal_floor,
        }
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/make_plan", params, timeout=timeout)
