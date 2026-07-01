"""
机器人主程序状态机

管理 Lumi 的任务生命周期和各执行机构的协调配合。
在后台线程中循环运行，通过共享状态字典与 Flask 服务交互。
"""

import time
import logging
import threading
from enum import Enum
from typing import Optional, Dict, Any, List, Callable

from controller import config
from controller.task_manager import TaskManager, DeliveryTask
from controller.devices.agv_adapter import AGVAdapter
from controller.devices.arm_adapter import ArmAdapter
from controller.devices.vision_adapter import VisionAdapter
from controller.devices.gripper_adapter import GripperAdapter

logger = logging.getLogger("controller.state_machine")


class RobotState(Enum):
    """Lumi 机器人状态"""
    IDLE = "idle"                         # 在取餐点待命
    DISPATCHING = "dispatching"           # 正在取出任务
    MOVING_TO_ELEVATOR = "moving_to_elevator"  # AGV 前往电梯口
    TAKING_ELEVATOR = "taking_elevator"   # 乘梯至目标楼层
    NAVIGATING_TO_ROOM = "navigating_to_room"  # 导航至房间门口
    VISION_CALIBRATING = "vision_calibrating"  # 视觉校准放置位置
    PLACING_COFFEE = "placing_coffee"     # 机械臂执行放置动作序列
    RETURNING = "returning"               # 返回取餐点
    COMPLETED = "completed"               # 单次任务完成
    ERROR = "error"                       # 异常状态
    CHARGING = "charging"                 # 前往充电点


class StateMachine:
    """Lumi 主程序状态机

    在后台线程运行，循环调用 tick() 推进状态。
    通过 shared_status 字典向 Flask 暴露实时状态。
    """

    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager

        # 设备适配器
        self.agv = AGVAdapter()
        self.arm = ArmAdapter()
        self.vision = VisionAdapter()
        self.gripper = GripperAdapter()

        # 状态
        self._state = RobotState.IDLE
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 当前任务相关
        self._current_task: Optional[DeliveryTask] = None
        self._target_floor: int = 1
        self._target_room: str = ""
        self._remaining_items: List[Dict[str, Any]] = []  # [{"drink": "拿铁", "tray_slot": 0}, ...]

        # 告警回调
        self._alert_callback: Optional[Callable] = None

        # 共享状态（Flask 读取）
        self.shared_status: Dict[str, Any] = {
            "connected": False,
            "moveStatus": "idle",
            "battery": 0,
            "currentFloor": 1,
            "currentPose": {"x": 0, "y": 0, "theta": 0},
            "charging": False,
            "estop": False,
            "currentTask": None,
            "robotState": RobotState.IDLE.value,
            "targetFloor": None,
            "targetRoom": None,
        }

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self):
        """启动状态机后台线程"""
        if self._running:
            logger.warning("状态机已在运行中")
            return

        self._running = True
        self._thread = threading.Thread(target=self._main_loop, daemon=True, name="state_machine")
        self._thread.start()
        logger.info("状态机已启动")

    def stop(self):
        """停止状态机"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("状态机已停止")

    def connect_devices(self):
        """连接所有设备"""
        logger.info("正在连接设备...")
        agv_ok = self.agv.connect()
        arm_ok = self.arm.connect()
        vis_ok = self.vision.connect()
        grip_ok = self.gripper.connect()
        self.shared_status["connected"] = arm_ok

        if agv_ok:
            # 注册 AGV 通知回调
            self.agv.register_notification_handler(self._on_agv_notification)
            # 读取初始状态
            self._refresh_agv_status()

        logger.info(f"设备连接完成: AGV={agv_ok}, ARM={arm_ok}, VISION={vis_ok}, GRIPPER={grip_ok}")
        return agv_ok

    def set_alert_callback(self, callback: Callable):
        """设置告警回调函数"""
        self._alert_callback = callback

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _main_loop(self):
        """状态机主循环"""
        logger.info("状态机主循环开始")
        while self._running:
            try:
                self.tick()
            except Exception as e:
                logger.exception(f"状态机 tick 异常: {e}")
                self._transition_to(RobotState.ERROR, error_msg=str(e))
            time.sleep(config.TICK_INTERVAL)
        logger.info("状态机主循环结束")

    def tick(self):
        """单次状态推进"""
        with self._lock:
            state = self._state

        handler = {
            RobotState.IDLE: self._tick_idle,
            RobotState.DISPATCHING: self._tick_dispatching,
            RobotState.MOVING_TO_ELEVATOR: self._tick_moving_to_elevator,
            RobotState.TAKING_ELEVATOR: self._tick_taking_elevator,
            RobotState.NAVIGATING_TO_ROOM: self._tick_navigating_to_room,
            RobotState.VISION_CALIBRATING: self._tick_vision_calibrating,
            RobotState.PLACING_COFFEE: self._tick_placing_coffee,
            RobotState.RETURNING: self._tick_returning,
            RobotState.COMPLETED: self._tick_completed,
            RobotState.ERROR: self._tick_error,
            RobotState.CHARGING: self._tick_charging,
        }.get(state)

        if handler:
            handler()

        # 定期刷新 AGV 状态
        self._refresh_agv_status()

    # ------------------------------------------------------------------
    # 各状态处理
    # ------------------------------------------------------------------

    def _tick_idle(self):
        """IDLE: 在取餐点待命，检查是否有新任务"""
        if not self.task_manager.has_tasks():
            return

        # 检查电量
        battery = self.shared_status.get("battery", 100)
        if battery < config.CRITICAL_BATTERY:
            logger.warning(f"电量危急 ({battery}%)，前往充电")
            self._transition_to(RobotState.CHARGING)
            return

        if battery < config.LOW_BATTERY_THRESHOLD:
            logger.info(f"电量较低 ({battery}%)，完成当前批次后回充")

        # 有任务，开始调度
        self._transition_to(RobotState.DISPATCHING)

    def _tick_dispatching(self):
        """DISPATCHING: 从队列取出任务"""
        task = self.task_manager.get_next_task()
        if not task:
            logger.info("队列为空，回到 IDLE")
            self._transition_to(RobotState.IDLE)
            return

        self._current_task = task
        self._target_floor = task.floor
        self._target_room = task.room
        self._remaining_items = list(task.items)
        self.shared_status["currentTask"] = task.order_id
        self.shared_status["targetFloor"] = task.floor
        self.shared_status["targetRoom"] = task.room

        logger.info(f"任务已取出: {task.order_id} -> {task.floor}F-{task.room}, 托盘={task.items}")
        self._transition_to(RobotState.MOVING_TO_ELEVATOR)

    def _tick_moving_to_elevator(self):
        """MOVING_TO_ELEVATOR: AGV 前往电梯口"""
        current_floor = self.shared_status.get("currentFloor", 1)

        if current_floor == self._target_floor:
            # 已在目标楼层，直接去房间
            logger.info("已在目标楼层，跳过电梯")
            self._transition_to(RobotState.NAVIGATING_TO_ROOM)
            return

        # 前往目标楼层（AGV 内置电梯联动）
        logger.info(f"乘梯前往 {self._target_floor} 楼")
        self.shared_status["moveStatus"] = "running"
        ok = self.agv.move_to_floor(self._target_floor)

        if ok:
            self._transition_to(RobotState.NAVIGATING_TO_ROOM)
        else:
            self._raise_alert("电梯移动失败", level="warning")
            self._transition_to(RobotState.ERROR, error_msg="乘梯失败")

    def _tick_taking_elevator(self):
        """TAKING_ELEVATOR: 乘梯中（AGV 自动处理电梯流程）

        实际上 move_to_floor 已包含完整电梯流程，
        此状态作为中间状态，检测 AGV 运行状态变化。
        """
        # 由 move_to_floor 的阻塞调用处理，正常情况下不会进入此状态
        self._transition_to(RobotState.NAVIGATING_TO_ROOM)

    def _tick_navigating_to_room(self):
        """NAVIGATING_TO_ROOM: 导航至房间门口"""
        # 构建目标点位名称（需与 AGV 地图上预设的 marker 对应）
        target_marker = f"{self._target_floor}F_{self._target_room}"
        logger.info(f"导航至房间: {target_marker}")
        self.shared_status["moveStatus"] = "running"

        ok = self.agv.move_to(target_marker)
        if ok:
            self.shared_status["moveStatus"] = "idle"
            self._transition_to(RobotState.VISION_CALIBRATING)
        else:
            self._raise_alert(f"导航至 {target_marker} 失败", level="warning")
            self._transition_to(RobotState.ERROR, error_msg=f"导航失败: {target_marker}")

    def _tick_vision_calibrating(self):
        """VISION_CALIBRATING: 视觉校准放置位置"""
        logger.info("视觉校准中...")

        # 拍照
        captured = self.vision.capture()
        if not captured:
            logger.warning("拍照失败，回退到盲放模式")
            self._transition_to(RobotState.PLACING_COFFEE)
            return

        # 检测目标
        offset = self.vision.detect_target()
        if offset is None:
            logger.warning("未检测到目标，回退到盲放模式")
            self._transition_to(RobotState.PLACING_COFFEE)
            return

        dx, dy, dtheta = offset
        logger.info(f"视觉偏差: dx={dx}mm, dy={dy}mm, dtheta={dtheta}rad")
        # TODO: 将偏差量传给机械臂做补偿
        self._transition_to(RobotState.PLACING_COFFEE)

    def _tick_placing_coffee(self):
        """PLACING_COFFEE: 机械臂执行放置动作序列

        动作序列：停车稳定 → 机械臂伸出 → 夹爪释放 → 机械臂收回
        安全约束：底盘必须已停止

        每次放置时从 _remaining_items 取第一杯，通过 tray_slot 确定托盘位置。
        """
        logger.info("开始放置咖啡...")

        # 确认底盘已停止
        if self.agv.is_moving():
            logger.warning("底盘仍在移动，等待停止")
            return

        # 获取当前要放置的饮品
        if not self._remaining_items:
            logger.warning("没有剩余饮品可放置")
            self._transition_to(RobotState.RETURNING)
            return

        current_cup = self._remaining_items[0]
        drink = current_cup.get("drink", "未知")
        tray_slot = current_cup.get("tray_slot", 0)
        logger.info(f"准备放置: {drink} (托盘第 {tray_slot} 格)")

        # TODO: 根据 tray_slot 计算机械臂取杯位姿
        pick_pose = self._compute_pick_pose(tray_slot)

        # 机械臂运动到放置位
        ok = self.arm.move_to_pose(config.TAKE_CUP_READY_POSE)
        if not ok:
            logger.error("机械臂运动到取饮品位置失败")
            self._raise_alert("机械臂取饮品位置运动失败", level="warning")
            self._transition_to(RobotState.ERROR, error_msg="机械臂取饮品位置运动失败")
            return
        self.arm.move_to_pose(pick_pose,0,50)
        self.arm.move_to_pose([0,0,40,0,0,0],1,30) # 机械臂抬起饮品

        # 机械臂运动到放置位
        self.arm.move_to_pose(config.PLACE_POSE, move_mode=0, speed=40)
        self.arm.move_to_pose([0,0,-15,0,0,0],1,30)
        self.arm.move_to_pose(config.PLACE_CUP_OVER, 60)

        # # 夹爪释放
        # self.gripper.open()
        # time.sleep(0.5)

        # 机械臂收回安全位
        self.arm.go_home()
        time.sleep(0.3)

        # 任务队列中移除已放置的饮品
        if self._remaining_items:
            placed = self._remaining_items.pop(0)
            logger.info(f"已放置: {placed.get('drink')} (托盘第 {placed.get('tray_slot')} 格), 剩余: {len(self._remaining_items)}")

        # 检查是否还有同房间饮品
        if self._remaining_items:
            logger.info(f"同房间还有 {len(self._remaining_items)} 杯，继续放置")
            self._transition_to(RobotState.PLACING_COFFEE)
            return

        # 当前房间完成，检查同楼层其他任务
        same_floor_task = self.task_manager.pop_same_floor(self._target_floor)
        if same_floor_task:
            logger.info(f"同楼层还有任务: {same_floor_task.order_id} -> {same_floor_task.room}")
            self.task_manager.complete_task(self._current_task, success=True)
            self._current_task = same_floor_task
            self._target_room = same_floor_task.room
            self._remaining_items = list(same_floor_task.items)
            self.shared_status["targetRoom"] = same_floor_task.room
            self.shared_status["currentTask"] = same_floor_task.order_id
            self._transition_to(RobotState.NAVIGATING_TO_ROOM)
            return

        # 所有任务完成，返回取餐点
        if self._current_task:
            self.task_manager.complete_task(self._current_task, success=True)
        self._transition_to(RobotState.RETURNING)

    def _tick_returning(self):
        """RETURNING: 返回取餐点"""
        logger.info("返回取餐点...")
        self.shared_status["moveStatus"] = "running"

        # 如果不在1楼，先回到1楼
        current_floor = self.shared_status.get("currentFloor", 1)
        if current_floor != 1:
            ok = self.agv.move_to_floor(1)
            if not ok:
                self._raise_alert("返回取餐点乘梯失败", level="warning")
                self._transition_to(RobotState.ERROR, error_msg="返回失败")
                return

        # 前往取餐点 marker
        ok = self.agv.move_to("pickup_point")
        self.shared_status["moveStatus"] = "idle"

        if ok:
            self._transition_to(RobotState.COMPLETED)
        else:
            self._raise_alert("返回取餐点导航失败", level="warning")
            self._transition_to(RobotState.ERROR, error_msg="返回导航失败")

    def _tick_completed(self):
        """COMPLETED: 任务完成，检查是否还有新任务"""
        self._current_task = None
        self.shared_status["currentTask"] = None
        self.shared_status["targetFloor"] = None
        self.shared_status["targetRoom"] = None

        # 检查电量是否需要回充
        battery = self.shared_status.get("battery", 100)
        if battery < config.LOW_BATTERY_THRESHOLD:
            logger.info(f"电量 {battery}%，前往充电")
            self._transition_to(RobotState.CHARGING)
            return

        # 有新任务则继续，否则回 IDLE
        if self.task_manager.has_tasks():
            self._transition_to(RobotState.DISPATCHING)
        else:
            self._transition_to(RobotState.IDLE)

    def _tick_error(self):
        """ERROR: 异常状态，等待人工介入"""
        # 保持当前状态，等待外部调用 resolve_error()
        pass

    def _tick_charging(self):
        """CHARGING: 低电量，前往充电点"""
        logger.info("前往充电点...")
        self.shared_status["moveStatus"] = "running"

        ok = self.agv.move_to("charging_point", timeout=60)
        self.shared_status["moveStatus"] = "idle"

        if ok:
            self.shared_status["charging"] = True
            logger.info("已到达充电点，等待充电")
            # TODO: 监听充电完成后再回到 IDLE
            # 当前简化处理：到达充电点后转为 IDLE
            self._transition_to(RobotState.IDLE)
        else:
            self._raise_alert("前往充电点失败", level="warning")
            self._transition_to(RobotState.ERROR, error_msg="充电点导航失败")

    # ------------------------------------------------------------------
    # 外部控制接口
    # ------------------------------------------------------------------

    def resolve_error(self):
        """人工解除异常状态"""
        with self._lock:
            if self._state == RobotState.ERROR:
                logger.info("异常已解除，回到 IDLE")
                self._state = RobotState.IDLE
                self.shared_status["robotState"] = RobotState.IDLE.value

    def emergency_stop(self):
        """紧急停止"""
        logger.warning("紧急停止！")
        self.agv.emergency_stop(enable=True)
        self.arm.abort()
        self.shared_status["estop"] = True
        self._transition_to(RobotState.ERROR, error_msg="紧急停止")

    def release_estop(self):
        """解除急停"""
        self.agv.emergency_stop(enable=False)
        self.shared_status["estop"] = False
        self.resolve_error()

    @property
    def current_state(self) -> RobotState:
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _transition_to(self, new_state: RobotState, error_msg: str = None):
        """状态转换"""
        with self._lock:
            old = self._state
            self._state = new_state

        self.shared_status["robotState"] = new_state.value
        self.shared_status["moveStatus"] = (
            "idle" if new_state in (RobotState.IDLE, RobotState.COMPLETED, RobotState.ERROR)
            else "running"
        )

        if error_msg:
            self.shared_status["lastError"] = error_msg

        logger.info(f"状态转换: {old.value} -> {new_state.value}" + (f" ({error_msg})" if error_msg else ""))

    def _refresh_agv_status(self):
        """刷新 AGV 状态到共享字典"""
        try:
            status = self.agv.get_status()
            self.shared_status["connected"] = self.arm.is_connected()
            self.shared_status["battery"] = status.get("battery", 0)
            self.shared_status["currentFloor"] = status.get("current_floor", 1)
            self.shared_status["currentPose"] = status.get("current_pose", {"x": 0, "y": 0, "theta": 0})
            self.shared_status["charging"] = status.get("charge_state", False)
            self.shared_status["estop"] = status.get("estop", False)
        except Exception as e:
            logger.warning(f"刷新 AGV 状态失败: {e}")

    def _on_agv_notification(self, notification: Dict):
        """处理 AGV 主动通知"""
        code = notification.get("code", "")
        level = notification.get("level", "info")
        desc = notification.get("description", "")
        logger.info(f"AGV 通知 [{level}]: {code} - {desc}")

        if level in ("warning", "error"):
            self._raise_alert(desc, code=code, level=level)

    def _raise_alert(self, description: str, code: str = "", level: str = "warning"):
        """触发告警"""
        logger.warning(f"告警 [{level}]: {description}")
        if self._alert_callback:
            try:
                self._alert_callback({
                    "code": code,
                    "level": level,
                    "description": description,
                })
            except Exception as e:
                logger.error(f"告警回调异常: {e}")

    def _compute_pick_pose(self, tray_slot: int):
        """根据托盘格子计算机械臂取杯位姿"""
        if tray_slot < 0 or tray_slot >= len(config.CUP_POSE):
            return None    
        return config.CUP_POSE[tray_slot]
