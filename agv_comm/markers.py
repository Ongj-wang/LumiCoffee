"""
AGV 点位（Marker）管理 API

封装与地图点位相关的接口：
- 在当前位置标记 marker（/api/markers/insert）
- 获取 marker 列表（/api/markers/query_list）
- 删除 marker（/api/markers/delete）
- 获取点位数量（/api/markers/count）
- 获取点位摘要（/api/markers/query_brief）
- 指定坐标标记 marker（/api/markers/insert_by_pose）

Marker 类型说明：
- 0: 一般点位
- 1: 前台点
- 3: 电梯外
- 4: 电梯内
- 7: 闸机
- 11: 充电桩
- >1000: 自定义类型（建议使用监控页面添加）
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agv_comm.client import AGVClient


class MarkerAPI:
    """点位管理 API 模块"""

    # 常用点位类型常量
    TYPE_GENERAL = 0       # 一般点位
    TYPE_RECEPTION = 1     # 前台点
    TYPE_LIFT_OUTSIDE = 3  # 电梯外
    TYPE_LIFT_INSIDE = 4   # 电梯内
    TYPE_GATE = 7          # 闸机
    TYPE_CHARGER = 11      # 充电桩

    def __init__(self, client: "AGVClient"):
        self._client = client

    # ------------------------------------------------------------------
    # 接口 5.1：在当前位置标记 marker
    # ------------------------------------------------------------------

    def insert(
        self,
        name: str,
        type_: int = TYPE_GENERAL,
        num: int = 1,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """在机器人当前位置标记一个 marker 点位

        如果 name 已存在，则更新坐标。

        Args:
            name: 点位名称（不支持特殊字符）
            type_: 点位类型（0一般/1前台/3电梯外/4电梯内/7闸机/11充电桩）
            num: 点位编号（电梯、闸机、充电桩等具有编号属性）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {"name": name, "type": type_, "num": num}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/markers/insert", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 5.2：获取 marker 列表
    # ------------------------------------------------------------------

    def query_list(
        self,
        floor: Optional[int] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """获取所有点位（marker）信息

        每个点位包含：marker_name、floor、pose（四元数）、key（类型）。
        四元数转 theta：theta = 2 * atan2(orientation.z, orientation.w)

        Args:
            floor: 按楼层过滤，None 返回所有楼层
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            results 字段为字典，key 为点位名称，value 为点位信息。
            无点位时 results 为 null。
        """
        params = {}
        if floor is not None:
            params["floor"] = floor
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/markers/query_list", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 5.3：删除 marker
    # ------------------------------------------------------------------

    def delete(
        self,
        name: str,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """删除指定的 marker 点位

        Args:
            name: 要删除的点位名称
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典。点位不存在时返回 INVALID_REQUEST。
        """
        params = {"name": name}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/markers/delete", params, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 5.4：获取点位数量
    # ------------------------------------------------------------------

    def count(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> int:
        """获取当前地图中的点位数量

        Returns:
            点位数量（int）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        response = self._client.send_command("/api/markers/count", params or None, timeout=timeout)
        return response.get("results", {}).get("count", 0)

    # ------------------------------------------------------------------
    # 接口 5.5：获取点位摘要信息
    # ------------------------------------------------------------------

    def query_brief(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取所有点位的摘要信息

        比 query_list 更简洁，每个点位格式为 "类型-楼层"。

        Returns:
            results 字段为字典，如 {"meeting_room": "0-1", "205_room": "0-1"}
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/markers/query_brief", params or None, timeout=timeout)

    # ------------------------------------------------------------------
    # 接口 5.6：指定坐标标记 marker
    # ------------------------------------------------------------------

    def insert_by_pose(
        self,
        name: str,
        x: float,
        y: float,
        theta: float,
        type_: int = TYPE_GENERAL,
        num: int = 1,
        floor: Optional[int] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """在指定坐标位置添加 marker

        Args:
            name: 点位名称（不支持特殊字符）
            x: 地图坐标 x
            y: 地图坐标 y
            theta: 点位方向（弧度），范围 [-π, π]
            type_: 点位类型
            num: 点位编号
            floor: 楼层（非0），默认为机器人当前楼层
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {
            "name": name,
            "x": x,
            "y": y,
            "theta": theta,
            "type": type_,
            "num": num,
        }
        if floor is not None:
            params["floor"] = floor
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/markers/insert_by_pose", params, timeout=timeout)
