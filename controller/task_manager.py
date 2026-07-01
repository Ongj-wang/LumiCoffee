"""
任务队列管理器

管理配送队列，实现优先级排序和同楼层批量合并。
与 Flask 的 queue 列表共享引用，状态机通过此模块取出和管理任务。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("controller.task_manager")

# 等待超时自动提权阈值（分钟）
AUTO_PRIORITIZE_MINUTES = 15


@dataclass
class DeliveryTask:
    """配送任务"""
    order_id: str
    floor: int
    room: str
    items: List[str]
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    position: int = 0

    def is_overdue(self) -> bool:
        """是否等待超时（需要自动提权）"""
        elapsed = datetime.now() - self.created_at
        return elapsed > timedelta(minutes=AUTO_PRIORITIZE_MINUTES)


class TaskManager:
    """任务队列管理器

    管理待配送任务队列，提供：
    - FIFO 默认排序
    - 手动加急优先级
    - 等待超时自动提权
    - 同楼层批量合并
    """

    def __init__(self):
        self._queue: List[DeliveryTask] = []
        self._current_task: Optional[DeliveryTask] = None
        self._completed: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 队列操作
    # ------------------------------------------------------------------

    def add_task(self, order: Dict[str, Any]) -> DeliveryTask:
        """从 Flask 订单字典创建配送任务并加入队列

        Args:
            order: Flask 订单字典，包含 id, floor, room, items, createdAt 等字段
        """
        task = DeliveryTask(
            order_id=order.get("id", ""),
            floor=int(order.get("floor", 1)),
            room=str(order.get("room", "")),
            items=order.get("items", []),
            priority=int(order.get("priority", 0)),
            created_at=_parse_datetime(order.get("createdAt")),
            position=len(self._queue),
        )
        self._queue.append(task)
        self._sort_queue()
        logger.info(f"任务入队: {task.order_id} -> {task.floor}F-{task.room}, 队列长度={len(self._queue)}")
        return task

    def get_next_task(self) -> Optional[DeliveryTask]:
        """取出下一个任务（从队列头部移除并返回）

        取出前会先执行超时自动提权检查。
        """
        self._check_auto_prioritize()
        self._sort_queue()

        if not self._queue:
            return None

        task = self._queue.pop(0)
        self._current_task = task
        self._reindex()
        logger.info(f"取出任务: {task.order_id} -> {task.floor}F-{task.room}, 剩余={len(self._queue)}")
        return task

    def peek_same_floor(self, floor: int) -> List[DeliveryTask]:
        """查看队列中目标楼层相同的任务（不移除）

        用于同楼层批量配送优化：完成一个房间后检查是否还有其他同楼层任务。
        """
        return [t for t in self._queue if t.floor == floor]

    def pop_same_floor(self, floor: int) -> Optional[DeliveryTask]:
        """取出一个同楼层任务（从队列移除）"""
        self._check_auto_prioritize()
        self._sort_queue()

        for i, task in enumerate(self._queue):
            if task.floor == floor:
                self._queue.pop(i)
                self._reindex()
                logger.info(f"取出同楼层任务: {task.order_id} -> {task.floor}F-{task.room}")
                return task
        return None

    def complete_task(self, task: DeliveryTask, success: bool = True):
        """标记任务完成"""
        record = {
            "order_id": task.order_id,
            "floor": task.floor,
            "room": task.room,
            "items": task.items,
            "success": success,
            "completed_at": datetime.now().isoformat(),
        }
        self._completed.append(record)
        if self._current_task and self._current_task.order_id == task.order_id:
            self._current_task = None
        logger.info(f"任务完成: {task.order_id}, success={success}")

    def cancel_task(self, order_id: str) -> bool:
        """取消指定任务"""
        for i, task in enumerate(self._queue):
            if task.order_id == order_id:
                self._queue.pop(i)
                self._reindex()
                logger.info(f"任务取消: {order_id}")
                return True
        return False

    def prioritize(self, order_id: str) -> bool:
        """手动提升优先级"""
        for task in self._queue:
            if task.order_id == order_id:
                task.priority += 1
                self._sort_queue()
                logger.info(f"任务加急: {order_id}, priority={task.priority}")
                return True
        return False

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def queue(self) -> List[DeliveryTask]:
        return self._queue

    @property
    def current_task(self) -> Optional[DeliveryTask]:
        return self._current_task

    @property
    def queue_length(self) -> int:
        return len(self._queue)

    def has_tasks(self) -> bool:
        return len(self._queue) > 0

    def get_queue_summary(self) -> List[Dict[str, Any]]:
        """获取队列摘要（供 API 返回）"""
        return [
            {
                "order_id": t.order_id,
                "floor": t.floor,
                "room": t.room,
                "items": t.items,
                "priority": t.priority,
                "position": t.position,
                "created_at": t.created_at.isoformat(),
                "waited_minutes": round((datetime.now() - t.created_at).total_seconds() / 60, 1),
            }
            for t in self._queue
        ]

    def sync_from_flask(self, flask_queue: List[Dict]):
        """从 Flask 的 queue 列表同步任务

        对比已有的 order_id，将新增的任务加入管理器。
        """
        existing_ids = {t.order_id for t in self._queue}
        if self._current_task:
            existing_ids.add(self._current_task.order_id)

        for item in flask_queue:
            order = item.get("order", item)
            order_id = order.get("id", "")
            if order_id and order_id not in existing_ids:
                self.add_task(order)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _sort_queue(self):
        """排序：优先级降序 > 创建时间升序（FIFO）"""
        self._queue.sort(key=lambda t: (-t.priority, t.created_at))
        self._reindex()

    def _reindex(self):
        """重新编号"""
        for i, task in enumerate(self._queue):
            task.position = i

    def _check_auto_prioritize(self):
        """检查并执行超时自动提权"""
        for task in self._queue:
            if task.is_overdue() and task.priority == 0:
                task.priority = 1
                logger.info(f"任务自动提权: {task.order_id} (等待超过 {AUTO_PRIORITIZE_MINUTES} 分钟)")


def _parse_datetime(dt_str) -> datetime:
    """安全解析 datetime 字符串"""
    if isinstance(dt_str, datetime):
        return dt_str
    if not dt_str:
        return datetime.now()
    try:
        return datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return datetime.now()
