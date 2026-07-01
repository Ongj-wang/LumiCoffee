"""
AGV 系统管理 API

封装与系统管理相关的接口：
- WiFi 管理（接口 13）：列表、连接、获取当前连接、IP 信息、详细信息
- 参数设置（接口 11/12）：最大速度设置与获取
- 灯带控制（接口 17）：亮度、颜色
- 自诊断（接口 18）：获取诊断结果
- 关机重启（接口 15）：关机、重启
- 软件更新（接口 16）：版本查询、检查更新、更新、重启服务
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agv_comm.client import AGVClient


class SystemAPI:
    """系统管理 API 模块"""

    def __init__(self, client: "AGVClient"):
        self._client = client

    # ==================================================================
    # WiFi 管理（接口 13）
    # ==================================================================

    def wifi_list(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人当前可用的 WiFi 列表

        Returns:
            results 字段为字典，key 为 SSID，value 为信号强度。
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/wifi/list", params or None, timeout=timeout)

    def wifi_connect(
        self,
        ssid: str,
        password: Optional[str] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """连接到指定 WiFi

        Args:
            ssid: WiFi 名称
            password: WiFi 密码（已连接过可不填）
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典
        """
        params = {"SSID": ssid}
        if password:
            params["password"] = password
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/wifi/connect", params, timeout=timeout)

    def wifi_get_active(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> str:
        """获取当前连接的 WiFi SSID

        Returns:
            当前连接的 SSID，未连接时返回空字符串。
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        response = self._client.send_command("/api/wifi/get_active_connection", params or None, timeout=timeout)
        return response.get("results", "")

    def wifi_info(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取机器人 IP 和无线网卡地址

        Returns:
            results 字段包含：
            - IPaddr: WiFi 分配的 IP（未连接为空）
            - HWaddr: 无线网卡物理地址
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/wifi/info", params or None, timeout=timeout)

    def wifi_detail_list(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取可用 WiFi 列表的详细信息

        Returns:
            results 字段为字典，每个 SSID 包含：
            - SSID, SIGNAL（信号强度）, ACTIVE（连接状态）,
              FREQ（频段）, SECURITY（加密方式）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/wifi/detail_list", params or None, timeout=timeout)

    # ==================================================================
    # 参数管理（接口 11/12）
    # ==================================================================

    def set_params(
        self,
        max_speed_linear: Optional[float] = None,
        max_speed_angular: Optional[float] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """设置机器人运动参数

        设置后在重启软件或整机前有效。
        实际运行速度会结合机器人内部参数取最小值。

        Args:
            max_speed_linear: 最大直线速度（m/s），范围 [0.1, 1.0]
            max_speed_angular: 最大角速度（rad/s），范围 [0.5, 3.5]
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Returns:
            响应字典（无论成功失败 status 均为 OK，需调用 get_params 确认）
        """
        params = {}
        if max_speed_linear is not None:
            params["max_speed_linear"] = max_speed_linear
        if max_speed_angular is not None:
            params["max_speed_angular"] = max_speed_angular
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/set_params", params or None, timeout=timeout)

    def get_params(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取当前机器人参数

        Returns:
            results 字段包含当前参数值，如 {"max_speed_linear": 0.5}
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/get_params", params or None, timeout=timeout)

    # ==================================================================
    # 灯带控制（接口 17）
    # ==================================================================

    def set_led_brightness(
        self, value: int, uuid: Optional[str] = None, timeout: Optional[float] = None
    ) -> dict:
        """设置 LED 灯带亮度

        Args:
            value: 亮度百分比，范围 [0, 100]
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Note:
            急停或充电状态下设置可能不生效。
        """
        params = {"value": value}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/LED/set_luminance", params, timeout=timeout)

    def set_led_color(
        self,
        r: int,
        g: int,
        b: int,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """设置 LED 灯带颜色

        Args:
            r: 红色值，范围 [0, 100]
            g: 绿色值，范围 [0, 100]
            b: 蓝色值，范围 [0, 100]
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Note:
            RGB 全为 0 时不能生效。会读写硬件 flash，不建议高频使用。
            急停或充电状态下设置可能不生效。
        """
        params = {"r": r, "g": g, "b": b}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/LED/set_color", params, timeout=timeout)

    # ==================================================================
    # 自诊断（接口 18）
    # ==================================================================

    def get_diagnosis(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """获取自诊断结果

        Returns:
            results 字段为字典，各诊断项包含：
            - status: 最近一次诊断结果（bool）
            - time_stamp: 最近诊断时间
            - total_count: 总诊断次数
            - success_count: 成功次数

            诊断项包括：sensor_core, motor_core_right/left,
            radio_core, power_core, depth_camera, laser, IMU, CAN, internet
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/diagnosis/get_result", params or None, timeout=timeout)

    # ==================================================================
    # 关机重启（接口 15）
    # ==================================================================

    def shutdown(
        self,
        reboot: bool = False,
        delay: Optional[int] = None,
        uuid: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """关机或重启机器人

        关机前会发出通知，10 秒后电源关闭。
        重启时重新上电与断电间有 5 秒间隔。

        Args:
            reboot: True 为重启，False 为关机
            delay: 延迟重启时间（分钟），范围 [0, 14400]，仅 reboot=True 时有效
            uuid: 自定义请求标识
            timeout: 响应超时时间（秒）

        Note:
            可能收不到 response。
        """
        params = {}
        if reboot:
            params["reboot"] = True
        if delay is not None and reboot:
            params["delay"] = delay
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/shutdown", params or None, timeout=timeout)

    # ==================================================================
    # 软件更新（接口 16）
    # ==================================================================

    def get_software_version(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> str:
        """获取当前软件版本号

        Returns:
            版本号字符串，如 "1.8.8"
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        response = self._client.send_command("/api/software/get_version", params or None, timeout=timeout)
        return response.get("results", "")

    def check_for_update(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """检查是否有新版本

        需要机器人接入网络。阻塞执行。

        Returns:
            results 字段包含：
            - version_latest: 最新版本
            - version_current: 当前版本
            - enable_update: 是否可以更新（bool）
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/software/check_for_update", params or None, timeout=timeout)

    def update_software(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """更新软件到最新版本

        需要机器人接入网络。阻塞执行。
        升级成功后自动重启服务，所有 TCP 连接需要重新建立。

        Returns:
            响应字典
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/software/update", params or None, timeout=timeout)

    def restart_service(self, uuid: Optional[str] = None, timeout: Optional[float] = None) -> dict:
        """重启软件服务

        重启后所有 TCP 连接需要重新建立。

        Returns:
            响应字典
        """
        params = {}
        if uuid:
            params["uuid"] = uuid
        return self._client.send_command("/api/software/restart", params or None, timeout=timeout)
