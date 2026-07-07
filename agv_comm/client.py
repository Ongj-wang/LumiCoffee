"""
AGV 底盘 TCP 核心客户端

实现与 AGV 底盘的 TCP Socket 通讯，包括：
- 连接管理与自动重连
- 指令发送与响应接收
- 回调数据（callback）和主动通知（notification）的异步处理
- 心跳保活机制
- 通讯日志记录

协议细节：
- 请求格式：类 URL 字符串，如 "/api/move?marker=target_name&uuid=123"
- 响应格式：JSON，type 字段区分 response/callback/notification
- 默认端口：31001
"""

import socket
import json
import uuid
import threading
import time
import logging
from typing import Optional, Callable, Any

from agv_comm.exceptions import (
    AGVConnectionError,
    AGVTimeoutError,
    raise_for_status,
)

logger = logging.getLogger("agv_comm")


class AGVClient:
    """AGV 底盘 TCP 通讯客户端

    管理与 AGV 底盘的连接，提供统一的指令发送接口，
    并在后台线程中处理回调数据和主动通知。

    Attributes:
        host: AGV 底盘服务器 IP 地址
        port: AGV 底盘服务器端口（默认 31001）
        timeout: 指令响应超时时间（秒）
        auto_reconnect: 是否启用自动重连
    """

    DEFAULT_HOST = "192.168.10.10"
    DEFAULT_PORT = 31001
    RECONNECT_INTERVAL = 5  # 重连间隔（秒）
    MAX_RECONNECT_ATTEMPTS = 10  # 最大重连次数
    HEARTBEAT_INTERVAL = 10  # 心跳间隔（秒）
    BUFFER_SIZE = 4096  # TCP 接收缓冲区大小

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
        auto_reconnect: bool = True,
        enable_heartbeat: bool = True,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.auto_reconnect = auto_reconnect
        self.enable_heartbeat = enable_heartbeat

        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._recv_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False

        # 响应等待队列：uuid -> (event, response_dict)
        self._pending_responses: dict[str, tuple[threading.Event, dict]] = {}

        # 回调和通知处理器
        self._callback_handlers: dict[str, list[Callable]] = {}
        self._notification_handlers: list[Callable] = []

        # 统计信息
        self._stats = {
            "commands_sent": 0,
            "responses_received": 0,
            "callbacks_received": 0,
            "notifications_received": 0,
            "reconnect_attempts": 0,
        }

        # 延迟初始化子模块
        self._movement = None
        self._status = None
        self._markers = None
        self._navigation = None
        self._system = None

    # ------------------------------------------------------------------
    # 子模块属性（延迟加载）
    # ------------------------------------------------------------------

    @property
    def movement(self):
        """移动控制模块"""
        if self._movement is None:
            from agv_comm.movement import MovementAPI
            self._movement = MovementAPI(self)
        return self._movement

    @property
    def status(self):
        """状态查询模块"""
        if self._status is None:
            from agv_comm.status import StatusAPI
            self._status = StatusAPI(self)
        return self._status

    @property
    def markers(self):
        """点位管理模块"""
        if self._markers is None:
            from agv_comm.markers import MarkerAPI
            self._markers = MarkerAPI(self)
        return self._markers

    @property
    def navigation(self):
        """地图与路径规划模块"""
        if self._navigation is None:
            from agv_comm.navigation import NavigationAPI
            self._navigation = NavigationAPI(self)
        return self._navigation

    @property
    def system(self):
        """系统管理模块"""
        if self._system is None:
            from agv_comm.system import SystemAPI
            self._system = SystemAPI(self)
        return self._system

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """当前是否已连接到底盘"""
        return self._connected and self._socket is not None

    @property
    def stats(self) -> dict:
        """通讯统计信息"""
        return self._stats.copy()

    def connect(self) -> None:
        """建立与 AGV 底盘的 TCP 连接

        Raises:
            AGVConnectionError: 连接失败
        """
        if self.is_connected:
            logger.warning("已经连接到底盘 %s:%d", self.host, self.port)
            return

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            self._connected = True
            self._running = True
            logger.info("已连接到底盘 %s:%d", self.host, self.port)

            # 启动接收线程
            self._recv_thread = threading.Thread(
                target=self._receive_loop, daemon=True, name="AGV-RecvThread"
            )
            self._recv_thread.start()

            # 启动心跳线程
            if self.enable_heartbeat:
                self._heartbeat_thread = threading.Thread(
                    target=self._heartbeat_loop, daemon=True, name="AGV-Heartbeat"
                )
                self._heartbeat_thread.start()

        except (socket.error, OSError) as e:
            self._cleanup_socket()
            raise AGVConnectionError(
                f"无法连接到底盘 {self.host}:{self.port}: {e}"
            )

    def disconnect(self) -> None:
        """主动断开与底盘的连接"""
        logger.info("正在断开与底盘的连接...")
        self._running = False
        self._connected = False
        self._cleanup_socket()

        # 唤醒所有等待中的响应
        for event, _ in self._pending_responses.values():
            event.set()
        self._pending_responses.clear()

        logger.info("已断开与底盘的连接")

    def reconnect(self, max_attempts: Optional[int] = None) -> bool:
        """手动重连

        Args:
            max_attempts: 最大重试次数，None 使用默认值

        Returns:
            重连是否成功
        """
        attempts = max_attempts or self.MAX_RECONNECT_ATTEMPTS
        self.disconnect()

        for i in range(attempts):
            try:
                logger.info("重连尝试 %d/%d ...", i + 1, attempts)
                self.connect()
                logger.info("重连成功")
                return True
            except AGVConnectionError:
                time.sleep(self.RECONNECT_INTERVAL)

        logger.error("重连失败，已达最大重试次数 %d", attempts)
        return False

    def _cleanup_socket(self) -> None:
        """清理 socket 资源"""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _auto_reconnect(self) -> bool:
        """自动重连逻辑

        Returns:
            重连是否成功
        """
        if not self.auto_reconnect:
            return False

        self._stats["reconnect_attempts"] += 1
        logger.warning("连接断开，尝试自动重连...")

        for i in range(self.MAX_RECONNECT_ATTEMPTS):
            if not self._running:
                return False
            try:
                self._cleanup_socket()
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self.timeout)
                self._socket.connect((self.host, self.port))
                self._connected = True
                logger.info("自动重连成功（第 %d 次尝试）", i + 1)
                return True
            except (socket.error, OSError):
                time.sleep(self.RECONNECT_INTERVAL)

        logger.error("自动重连失败")
        self._connected = False
        return False

    # ------------------------------------------------------------------
    # 指令发送
    # ------------------------------------------------------------------

    def send_command(
        self,
        command: str,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
        check_status: bool = True,
    ) -> dict:
        """发送指令并等待响应

        构造类 URL 格式的请求字符串，通过 TCP 发送给底盘，
        并阻塞等待对应的响应结果。

        Args:
            command: API 路径，如 "/api/move"
            params: 查询参数字典，如 {"marker": "room_205"}
            timeout: 响应超时时间（秒），None 使用默认超时
            check_status: 是否自动检查响应的 status 字段

        Returns:
            响应 JSON 字典

        Raises:
            AGVConnectionError: 未连接或发送失败
            AGVTimeoutError: 响应超时
            AGVInvalidRequestError: 请求无效
            AGVCommandError: 服务器错误
        """
        if not self.is_connected:
            raise AGVConnectionError("未连接到底盘，请先调用 connect()")

        # 构造请求字符串
        cmd_str = self._build_command_string(command, params)
        req_uuid = self._extract_uuid(params) if params and "uuid" in params else ""
        if not req_uuid:
            req_uuid = str(uuid.uuid4()).replace("-", "")[:16]
            cmd_str += f"&uuid={req_uuid}" if "?" in cmd_str else f"?uuid={req_uuid}"

        timeout = timeout or self.timeout

        # 注册等待
        event = threading.Event()
        self._pending_responses[req_uuid] = (event, {})

        # 发送
        logger.debug("发送指令: %s", cmd_str)
        try:
            with self._lock:
                self._socket.sendall(cmd_str.encode("utf-8"))
            self._stats["commands_sent"] += 1
        except (socket.error, OSError) as e:
            self._pending_responses.pop(req_uuid, None)
            self._connected = False
            if self._auto_reconnect():
                # 重连后重试一次
                return self.send_command(command, params, timeout, check_status)
            raise AGVConnectionError(f"指令发送失败: {e}")

        # 等待响应
        if not event.wait(timeout=timeout):
            self._pending_responses.pop(req_uuid, None)
            raise AGVTimeoutError(
                f"指令响应超时（{timeout}s）: {command}"
            )

        # 取出响应
        _, response = self._pending_responses.pop(req_uuid, (None, {}))
        if not response:
            raise AGVTimeoutError(f"未收到有效响应: {command}")

        self._stats["responses_received"] += 1

        # 检查状态码
        if check_status:
            raise_for_status(response)

        return response

    def send_command_async(
        self,
        command: str,
        params: Optional[dict] = None,
    ) -> str:
        """异步发送指令（不等待响应）

        Args:
            command: API 路径
            params: 查询参数字典

        Returns:
            本次请求的 uuid，可通过此 uuid 后续查询结果
        """
        if not self.is_connected:
            raise AGVConnectionError("未连接到底盘，请先调用 connect()")

        cmd_str = self._build_command_string(command, params)
        req_uuid = str(uuid.uuid4()).replace("-", "")[:16]
        cmd_str += f"&uuid={req_uuid}" if "?" in cmd_str else f"?uuid={req_uuid}"

        event = threading.Event()
        self._pending_responses[req_uuid] = (event, {})

        with self._lock:
            self._socket.sendall(cmd_str.encode("utf-8"))
        self._stats["commands_sent"] += 1

        return req_uuid

    def get_async_response(self, req_uuid: str, timeout: Optional[float] = None) -> dict:
        """获取异步指令的响应结果

        Args:
            req_uuid: send_command_async 返回的 uuid
            timeout: 等待超时时间

        Returns:
            响应 JSON 字典
        """
        if req_uuid not in self._pending_responses:
            raise AGVTimeoutError(f"找不到请求 uuid: {req_uuid}")

        event, response = self._pending_responses[req_uuid]
        timeout = timeout or self.timeout

        if not event.wait(timeout=timeout):
            self._pending_responses.pop(req_uuid, None)
            raise AGVTimeoutError(f"异步指令响应超时（{timeout}s）")

        self._pending_responses.pop(req_uuid, None)
        raise_for_status(response)
        return response

    # ------------------------------------------------------------------
    # 回调/通知处理
    # ------------------------------------------------------------------

    def register_callback(self, topic: str, handler: Callable[[dict], None]) -> None:
        """注册实时数据回调处理器

        当收到 type="callback" 且 topic 匹配的数据时，调用 handler。

        Args:
            topic: 数据主题，如 "robot_status"、"human_detection"、"robot_velocity"
            handler: 回调函数，接收 results 字典作为参数
        """
        if topic not in self._callback_handlers:
            self._callback_handlers[topic] = []
        self._callback_handlers[topic].append(handler)
        logger.debug("注册回调处理器: topic=%s", topic)

    def unregister_callback(self, topic: str, handler: Optional[Callable] = None) -> None:
        """取消回调处理器

        Args:
            topic: 数据主题
            handler: 指定要移除的处理器，None 则移除该 topic 下所有处理器
        """
        if topic in self._callback_handlers:
            if handler is None:
                del self._callback_handlers[topic]
            else:
                self._callback_handlers[topic] = [
                    h for h in self._callback_handlers[topic] if h != handler
                ]

    def register_notification_handler(self, handler: Callable[[dict], None]) -> None:
        """注册主动通知处理器

        当收到 type="notification" 的数据时，调用 handler。

        Args:
            handler: 通知处理函数，接收完整通知字典作为参数
        """
        self._notification_handlers.append(handler)
        logger.debug("注册通知处理器")

    def _dispatch_callback(self, data: dict) -> None:
        """分发回调数据到注册的处理器"""
        topic = data.get("topic", "")
        results = data.get("results", {})
        self._stats["callbacks_received"] += 1

        handlers = self._callback_handlers.get(topic, [])
        for handler in handlers:
            try:
                handler(results)
            except Exception as e:
                logger.error("回调处理器异常 (topic=%s): %s", topic, e)

    def _dispatch_notification(self, data: dict) -> None:
        """分发主动通知到注册的处理器"""
        self._stats["notifications_received"] += 1

        for handler in self._notification_handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error("通知处理器异常: %s", e)

    # ------------------------------------------------------------------
    # 后台线程
    # ------------------------------------------------------------------

    def _receive_loop(self) -> None:
        """TCP 数据接收循环（后台线程）

        持续从 socket 读取数据，按 JSON 解析后分发到对应的处理器。
        AGV 底盘可能在一帧数据中返回多个 JSON 对象，需要正确处理。
        """
        buffer = ""

        while self._running:
            try:
                if not self._socket:
                    break

                data = self._socket.recv(self.BUFFER_SIZE)
                if not data:
                    logger.warning("连接被关闭（收到空数据）")
                    self._connected = False
                    if self._running and not self._auto_reconnect():
                        break
                    # 重连成功后需要重新创建接收线程
                    if self._connected:
                        buffer = ""
                        continue
                    break

                buffer += data.decode("utf-8", errors="replace")

                # 尝试解析 buffer 中的 JSON 数据
                buffer = self._process_buffer(buffer)

            except socket.timeout:
                continue
            except (socket.error, OSError) as e:
                if not self._running:
                    break
                logger.warning("接收数据异常: %s", e)
                self._connected = False
                if self._running and not self._auto_reconnect():
                    break
                if self._connected:
                    buffer = ""
                    continue
                break

        logger.debug("接收线程退出")

    def _process_buffer(self, buffer: str) -> str:
        """从缓冲区中提取并处理 JSON 数据

        AGV 返回的数据可能包含多个 JSON 对象拼接，
        通过匹配花括号进行分割解析。

        Args:
            buffer: 当前缓冲区内容

        Returns:
            未解析完的剩余缓冲区内容
        """
        while buffer:
            # 寻找第一个 '{' 开始
            start = buffer.find("{")
            if start == -1:
                return ""

            # 匹配花括号找到完整 JSON
            depth = 0
            end = -1
            for i in range(start, len(buffer)):
                if buffer[i] == "{":
                    depth += 1
                elif buffer[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

            if end == -1:
                # JSON 不完整，等待更多数据
                return buffer[start:]

            json_str = buffer[start:end]
            remaining = buffer[end:]

            try:
                data = json.loads(json_str)
                self._handle_received_data(data)
            except json.JSONDecodeError:
                logger.warning("JSON 解析失败: %s", json_str[:200])

            buffer = remaining

        return ""

    def _handle_received_data(self, data: dict) -> None:
        """处理接收到的 JSON 数据，根据 type 字段分发"""
        msg_type = data.get("type", "")

        if msg_type == "response":
            # 指令响应，匹配 uuid
            resp_uuid = data.get("uuid", "")
            if resp_uuid and resp_uuid in self._pending_responses:
                event, _ = self._pending_responses[resp_uuid]
                self._pending_responses[resp_uuid] = (event, data)
                event.set()
            else:
                logger.debug("收到无匹配的响应: uuid=%s", resp_uuid)

        elif msg_type == "callback":
            # 实时数据回调
            self._dispatch_callback(data)

        elif msg_type == "notification":
            # 主动通知
            self._dispatch_notification(data)

        else:
            logger.debug("收到未知类型消息: type=%s", msg_type)

    def _heartbeat_loop(self) -> None:
        """心跳保活循环（后台线程）

        定期发送 robot_status 查询，保持连接活跃，
        同时可用于检测连接是否正常。
        """
        while self._running:
            time.sleep(self.HEARTBEAT_INTERVAL)
            if not self._running:
                break

            if self.is_connected:
                try:
                    # 使用 robot_status 作为心跳指令（轻量级查询）
                    self.send_command("/api/robot_status", timeout=5, check_status=False)
                    logger.debug("心跳正常")
                except AGVTimeoutError:
                    logger.warning("心跳超时，连接可能异常")
                    self._connected = False
                except AGVConnectionError:
                    logger.warning("心跳发送失败，尝试重连")
                except Exception as e:
                    logger.warning("心跳异常: %s", e)

        logger.debug("心跳线程退出")

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_command_string(command: str, params: Optional[dict] = None) -> str:
        """构造类 URL 格式的请求字符串

        Args:
            command: API 路径，如 "/api/move"
            params: 参数字典

        Returns:
            完整的请求字符串，如 "/api/move?marker=room_205&uuid=abc"
        """
        if not params:
            return command

        query_parts = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                value = str(value).lower()
            elif isinstance(value, (list, tuple)):
                value = ",".join(str(v) for v in value)
            query_parts.append(f"{key}={value}")

        if query_parts:
            return f"{command}?{'&'.join(query_parts)}"
        return command

    @staticmethod
    def _extract_uuid(params: dict) -> str:
        """从参数字典中提取 uuid"""
        return str(params.get("uuid", ""))

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
        return False

    def __repr__(self) -> str:
        status = "已连接" if self.is_connected else "未连接"
        return f"<AGVClient {self.host}:{self.port} [{status}]>"
