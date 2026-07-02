"""
AGV Mock Server - AGV 底盘模拟服务

模拟 JAKA Lumi AGV 底盘的 TCP Socket 服务，用于开发和测试。

协议：
- 请求格式：类 URL 字符串，如 /api/move?marker=room_205&uuid=abc123
- 响应格式：JSON，包含 type、uuid、status、results 等字段

用法：
    python mock_agv_server.py [host] [port]
    
    默认监听 0.0.0.0:31001
"""

import socket
import threading
import json
import time
import re
import logging
import argparse
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("mock_agv")


class AGVState:
    """模拟 AGV 的状态"""
    
    def __init__(self):
        self.battery = 85  # 电量百分比
        self.current_floor = 1
        self.current_pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
        self.move_status = "idle"  # idle, running, succeeded, failed, canceled
        self.move_target = ""
        self.running_status = "idle"
        self.charge_state = False
        self.soft_estop_state = False
        self.hard_estop_state = False
        self.error_code = "0x00000000"
        self.move_retry_times = 0
        
        # 模拟点位坐标（用于返回到达后的位姿）
        self.markers = {
            "floor_1": {"x": 0.0, "y": 0.0, "theta": 0.0, "floor": 1},
            "floor_2": {"x": 0.0, "y": 0.0, "theta": 0.0, "floor": 2},
            "floor_3": {"x": 0.0, "y": 0.0, "theta": 0.0, "floor": 3},
            "floor_4": {"x": 0.0, "y": 0.0, "theta": 0.0, "floor": 4},
            "floor_5": {"x": 0.0, "y": 0.0, "theta": 0.0, "floor": 5},
            "1F_101": {"x": 1.0, "y": 2.0, "theta": 0.0, "floor": 1},
            "1F_102": {"x": 1.5, "y": 2.0, "theta": 0.0, "floor": 1},
            "1F_大厅": {"x": 2.0, "y": 3.0, "theta": 0.0, "floor": 1},
            "2F_201": {"x": 1.0, "y": 2.0, "theta": 0.0, "floor": 2},
            "2F_205": {"x": 2.0, "y": 2.5, "theta": 0.0, "floor": 2},
            "3F_305": {"x": 1.5, "y": 3.0, "theta": 0.0, "floor": 3},
            "charging_pile": {"x": 0.5, "y": 0.5, "theta": 0.0, "floor": 1},
        }
        
        # 移动模拟参数
        self.move_duration = 3.0  # 模拟移动耗时（秒）
        self._move_thread: Optional[threading.Thread] = None
        self._move_lock = threading.Lock()
    
    def start_move(self, marker: str, task_id: str) -> None:
        """开始模拟移动（异步）"""
        with self._move_lock:
            if self._move_thread and self._move_thread.is_alive():
                logger.warning("上一个移动任务仍在进行中")
                return
            
            self.move_status = "running"
            self.move_target = marker
            self.running_status = "running"
            
            self._move_thread = threading.Thread(
                target=self._simulate_move,
                args=(marker, task_id),
                daemon=True
            )
            self._move_thread.start()
    
    def _simulate_move(self, marker: str, task_id: str) -> None:
        """模拟移动过程"""
        logger.info(f"开始模拟移动: {marker} (task_id={task_id})")
        
        # 检查是否跨楼层
        marker_info = self.markers.get(marker, {})
        target_floor = marker_info.get("floor", self.current_floor)
        
        if target_floor != self.current_floor:
            logger.info(f"跨楼层移动: {self.current_floor}F -> {target_floor}F")
            self.running_status = "goto_lift"
            time.sleep(self.move_duration * 0.3)
            
            self.running_status = "take_lift"
            time.sleep(self.move_duration * 0.3)
            
            self.current_floor = target_floor
            self.running_status = "exit_lift"
            time.sleep(self.move_duration * 0.2)
        else:
            time.sleep(self.move_duration * 0.8)
        
        # 更新位姿
        if marker in self.markers:
            self.current_pose = {
                "x": marker_info["x"],
                "y": marker_info["y"],
                "theta": marker_info["theta"]
            }
        
        # 移动完成
        self.move_status = "succeeded"
        self.running_status = "idle"
        self.move_target = ""
        
        logger.info(f"移动完成: {marker}, 当前楼层: {self.current_floor}F")
    
    def cancel_move(self) -> None:
        """取消移动"""
        self.move_status = "canceled"
        self.running_status = "idle"
        self.move_target = ""
        logger.info("移动已取消")
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "move_target": self.move_target,
            "move_status": self.move_status,
            "running_status": self.running_status,
            "move_retry_times": self.move_retry_times,
            "charge_state": self.charge_state,
            "soft_estop_state": self.soft_estop_state,
            "hard_estop_state": self.hard_estop_state,
            "estop_state": self.soft_estop_state or self.hard_estop_state,
            "power_percent": self.battery,
            "current_pose": self.current_pose,
            "current_floor": self.current_floor,
            "chargepile_id": "",
            "error_code": self.error_code,
        }


class MockAGVServer:
    """AGV 模拟服务端"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 31001):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.state = AGVState()
        self._task_counter = 0
    
    def start(self) -> None:
        """启动服务"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)
        self.running = True
        
        logger.info(f"AGV Mock Server 启动: {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                logger.info(f"客户端连接: {addr}")
                
                # 每个客户端一个线程
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Accept 异常: {e}")
        
        self.server_socket.close()
        logger.info("AGV Mock Server 已停止")
    
    def stop(self) -> None:
        """停止服务"""
        self.running = False
    
    def _handle_client(self, client_socket: socket.socket, addr: tuple) -> None:
        """处理单个客户端连接"""
        client_socket.settimeout(1.0)
        buffer = ""
        
        try:
            while self.running:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        logger.info(f"客户端断开: {addr}")
                        break
                    
                    buffer += data.decode("utf-8", errors="replace")
                    
                    # 解析请求（可能一次收到多个请求）
                    while buffer:
                        # 查找请求分隔（换行或完整的 URL 路径）
                        lines = buffer.split("\n", 1)
                        request_line = lines[0].strip()
                        buffer = lines[1] if len(lines) > 1 else ""
                        
                        if not request_line:
                            continue
                        
                        logger.debug(f"收到请求: {request_line}")
                        response = self._process_request(request_line)
                        
                        if response:
                            response_str = json.dumps(response, ensure_ascii=False)
                            client_socket.sendall(response_str.encode("utf-8"))
                            logger.debug(f"发送响应: {response_str[:200]}...")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"客户端处理异常: {e}")
                    break
                    
        finally:
            try:
                client_socket.close()
            except:
                pass
    
    def _process_request(self, request: str) -> Optional[Dict[str, Any]]:
        """处理请求并返回响应"""
        # 解析 URL-like 请求
        # 格式: /api/xxx?param1=value1&param2=value2
        match = re.match(r'(/api/\w+)(?:\?(.*))?', request)
        if not match:
            logger.warning(f"无法解析请求: {request}")
            return None
        
        path = match.group(1)
        query_str = match.group(2) or ""
        
        # 解析查询参数
        params = {}
        for param in query_str.split("&"):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = value
        
        req_uuid = params.get("uuid", "")
        
        # 路由处理
        if path == "/api/robot_status":
            return self._handle_robot_status(req_uuid)
        
        elif path == "/api/move":
            marker = params.get("marker", "")
            return self._handle_move(req_uuid, marker)
        
        elif path == "/api/robot_info":
            return self._handle_robot_info(req_uuid)
        
        elif path == "/api/move/cancel":
            return self._handle_move_cancel(req_uuid)
        
        elif path == "/api/estop":
            return self._handle_estop(req_uuid)
        
        elif path == "/api/estop/release":
            return self._handle_estop_release(req_uuid)
        
        elif path == "/api/request_data":
            return self._handle_request_data(req_uuid, params)
        
        elif path == "/api/position_adjust":
            return self._handle_position_adjust(req_uuid, params)
        
        else:
            logger.warning(f"未知 API: {path}")
            return self._make_response(req_uuid, status="INVALID_REQUEST", error_message=f"Unknown API: {path}")
    
    def _make_response(
        self,
        uuid: str,
        status: str = "OK",
        error_message: str = "",
        results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """构造标准响应"""
        return {
            "type": "response",
            "uuid": uuid,
            "status": status,
            "error_message": error_message,
            "results": results or {},
        }
    
    def _handle_robot_status(self, uuid: str) -> Dict[str, Any]:
        """处理 /api/robot_status"""
        return self._make_response(
            uuid,
            status="OK",
            error_message="",
            results=self.state.get_status()
        )
    
    def _handle_move(self, uuid: str, marker: str) -> Dict[str, Any]:
        """处理 /api/move"""
        if not marker:
            return self._make_response(uuid, status="INVALID_REQUEST", error_message="marker is required")
        
        # 生成 task_id
        self._task_counter += 1
        task_id = f"task_{self._task_counter:06d}"
        
        # 开始模拟移动
        self.state.start_move(marker, task_id)
        
        return self._make_response(
            uuid,
            status="OK",
            error_message="",
            results={"task_id": task_id}
        )
    
    def _handle_robot_info(self, uuid: str) -> Dict[str, Any]:
        """处理 /api/robot_info"""
        return self._make_response(
            uuid,
            status="OK",
            error_message="",
            results={"product_id": "MOCK-LUMI-001"}
        )
    
    def _handle_move_cancel(self, uuid: str) -> Dict[str, Any]:
        """处理 /api/move/cancel"""
        self.state.cancel_move()
        return self._make_response(uuid, status="OK", error_message="")
    
    def _handle_estop(self, uuid: str) -> Dict[str, Any]:
        """处理 /api/estop"""
        self.state.soft_estop_state = True
        self.state.cancel_move()
        return self._make_response(uuid, status="OK", error_message="")
    
    def _handle_estop_release(self, uuid: str) -> Dict[str, Any]:
        """处理 /api/estop/release"""
        self.state.soft_estop_state = False
        return self._make_response(uuid, status="OK", error_message="")
    
    def _handle_request_data(self, uuid: str, params: Dict[str, str]) -> Dict[str, Any]:
        """处理 /api/request_data（请求实时数据推送）"""
        # 这里只返回成功响应，实际推送由客户端的 callback 机制处理
        # 模拟服务端暂不实现主动推送
        return self._make_response(
            uuid,
            status="OK",
            error_message="",
            results={"frequency": float(params.get("frequency", "2.0"))}
        )
    
    def _handle_position_adjust(self, uuid: str, params: Dict[str, str]) -> Dict[str, Any]:
        """处理 /api/position_adjust"""
        # 模拟位置校正
        dx = float(params.get("dx", "0"))
        dy = float(params.get("dy", "0"))
        
        self.state.current_pose["x"] += dx
        self.state.current_pose["y"] += dy
        
        return self._make_response(
            uuid,
            status="OK",
            error_message="",
            results={"new_pose": self.state.current_pose}
        )


def main():
    parser = argparse.ArgumentParser(description="AGV Mock Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=31001, help="监听端口 (默认: 31001)")
    args = parser.parse_args()
    
    server = MockAGVServer(host=args.host, port=args.port)
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("收到停止信号")
        server.stop()


if __name__ == "__main__":
    main()
