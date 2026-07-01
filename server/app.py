"""
Lumi 咖啡配送调度服务

Flask 后端，提供以下 API：
- 订单管理: GET/POST /api/orders
- 配送队列: GET /api/queue, POST /api/queue/prioritize, /api/queue/cancel
- Lumi 状态: GET /api/lumi/status, GET /api/lumi/state
- 告警管理: GET /api/alerts, POST /api/alerts/<id>/resolve
- 状态机控制: POST /api/lumi/resolve_error, POST /api/lumi/estop

架构：Flask 服务 + 状态机总控（后台线程），通过共享状态字典交互。
"""

import logging

from flask_cors import CORS
from flask import Flask, jsonify, request
import sys
import os
import json
import uuid
import random
from datetime import datetime, timedelta

# 确保 controller 模块可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controller import StateMachine, TaskManager

app = Flask(__name__)
CORS(app)

# ======================================================================
# 初始化状态机与任务管理器
# ======================================================================

task_manager = TaskManager()
state_machine = StateMachine(task_manager)

logger = logging.getLogger("werkzeug")
logger.setLevel(logging.WARNING)


# 告警回调：状态机产生告警时写入 alerts 列表


def _on_alert(alert_info):
    alerts.append({
        "id": _gen_id(),
        "code": alert_info.get("code", ""),
        "level": alert_info.get("level", "warning"),
        "description": alert_info.get("description", ""),
        "timestamp": datetime.now().isoformat(),
        "resolved": False,
    })


state_machine.set_alert_callback(_on_alert)

# ======================================================================
# 加载配置文件
# ======================================================================

_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_config.json")
with open(_config_path, "r", encoding="utf-8") as _f:
    server_config = json.load(_f)

DRINKS = server_config.get("drinks", [])
FLOORS = server_config.get("floors", [])
ROOMS_BY_FLOOR = {int(k): v for k, v in server_config.get("rooms", {}).items()}


def _gen_id():
    return str(uuid.uuid4())[:8].upper()


# 订单历史（不再初始化模拟数据，由营业员手动添加）
orders = []
alerts = []  # 告警列表


# ======================================================================
# 配置 API
# ======================================================================

@app.route("/api/config/options", methods=["GET"])
def get_options():
    """获取前端表单选项（饮品、楼层、房间）"""
    return jsonify(server_config)


# ======================================================================
# 订单 API
# ======================================================================

@app.route("/api/orders", methods=["GET"])
def get_orders():
    """获取订单列表，可按状态过滤"""
    status = request.args.get("status")
    if status:
        filtered = [o for o in orders if o["status"] == status]
    else:
        filtered = orders
    return jsonify(sorted(filtered, key=lambda o: o["createdAt"], reverse=True))


@app.route("/api/orders/dispatch", methods=["POST"])
def dispatch_order():
    """营业员手动送出配送

    请求体:
    {
        "items": [
            {"drink": "拿铁", "floor": 3, "room": "305"},
            {"drink": "美式咖啡", "floor": 3, "room": "305"},
            ...
        ]
    }
    """
    data = request.json or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "配送条目不能为空"}), 400

    # 全局分配托盘槽位（营业员放置顺序，从 0 开始）
    for idx, item in enumerate(items):
        item["tray_slot"] = idx

    # 按目标分组，每组生成一个配送订单
    groups = {}
    for item in items:
        drink = item.get("drink", "")
        floor = int(item.get("floor", 1))
        room = str(item.get("room", ""))
        tray_slot = item.get("tray_slot", 0)
        if not drink or not room:
            continue
        key = f"{floor}F-{room}"
        if key not in groups:
            groups[key] = {"floor": floor, "room": room, "drinks": []}
        groups[key]["drinks"].append({"drink": drink, "tray_slot": tray_slot})

    created_orders = []
    for key, group in groups.items():
        order = {
            "id": _gen_id(),
            "room": group["room"],
            "floor": group["floor"],
            "customer": "",
            "items": group["drinks"],  # [{"drink": "拿铁", "tray_slot": 0}, ...]
            "status": "queued",
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat(),
        }
        orders.append(order)
        created_orders.append(order)

        # 加入任务管理器，状态机会自动取出执行
        task_manager.add_task(order)

    if len(created_orders) == 1:
        return jsonify(created_orders[0])
    return jsonify(created_orders)


@app.route("/api/orders/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    """取消订单"""
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        return jsonify({"error": "订单不存在"}), 404

    order["status"] = "cancelled"
    order["updatedAt"] = datetime.now().isoformat()

    # 从任务管理器中移除
    task_manager.cancel_task(order_id)

    return jsonify({"ok": True})


# ======================================================================
# 队列 API
# ======================================================================

@app.route("/api/queue", methods=["GET"])
def get_queue():
    """获取当前配送队列（从任务管理器读取）"""
    return jsonify(task_manager.get_queue_summary())


@app.route("/api/queue/prioritize/<order_id>", methods=["POST"])
def prioritize_order(order_id):
    """提升订单优先级"""
    if task_manager.prioritize(order_id):
        return jsonify({"ok": True})
    return jsonify({"error": "订单不在队列中"}), 404


@app.route("/api/queue/cancel/<order_id>", methods=["POST"])
def cancel_from_queue(order_id):
    """从队列中移除订单"""
    order = next((o for o in orders if o["id"] == order_id), None)
    if order:
        order["status"] = "cancelled"
        order["updatedAt"] = datetime.now().isoformat()

    if task_manager.cancel_task(order_id):
        return jsonify({"ok": True})
    return jsonify({"error": "订单不在队列中"}), 404


@app.route("/api/queue/dispatch", methods=["POST"])
def dispatch_next():
    """手动触发下一单配送（从队首取出任务并开始执行）"""
    task = task_manager.get_next_task()
    if not task:
        return jsonify({"error": "队列为空，无可配送任务"}), 404
    return jsonify({"ok": True, "order_id": task.order_id, "floor": task.floor, "room": task.room})


# ======================================================================
# Lumi 状态 API
# ======================================================================

@app.route("/api/lumi/status", methods=["GET"])
def get_lumi_status():
    """获取 Lumi 当前状态（从状态机共享状态读取）"""
    return jsonify(state_machine.shared_status)


@app.route("/api/lumi/state", methods=["GET"])
def get_lumi_state():
    """获取状态机当前状态"""
    return jsonify({
        "robotState": state_machine.current_state.value,
        "currentTask": state_machine.shared_status.get("currentTask"),
        "targetFloor": state_machine.shared_status.get("targetFloor"),
        "targetRoom": state_machine.shared_status.get("targetRoom"),
        "queueLength": task_manager.queue_length,
        "devices": {
            "agv": state_machine.agv.get_status(),
            "arm": state_machine.arm.get_status(),
            "vision": state_machine.vision.get_status(),
            "gripper": state_machine.gripper.get_status(),
        },
    })


@app.route("/api/lumi/resolve_error", methods=["POST"])
def resolve_error():
    """解除异常状态"""
    state_machine.resolve_error()
    return jsonify({"ok": True})


@app.route("/api/lumi/estop", methods=["POST"])
def estop():
    """紧急停止"""
    data = request.json or {}
    enable = data.get("enable", True)
    if enable:
        state_machine.emergency_stop()
    else:
        state_machine.release_estop()
    return jsonify({"ok": True})


# ======================================================================
# 告警 API
# ======================================================================

@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    """获取告警列表"""
    return jsonify(sorted(alerts, key=lambda a: a["timestamp"], reverse=True))


@app.route("/api/alerts/<alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id):
    """标记告警为已处理"""
    alert = next((a for a in alerts if a["id"] == alert_id), None)
    if not alert:
        return jsonify({"error": "告警不存在"}), 404

    alert["resolved"] = True
    return jsonify({"ok": True})


# ======================================================================
# 内部辅助函数
# ======================================================================

def _add_demo_alert():
    """添加一条模拟告警"""
    alert_types = [
        {"code": "01006", "level": "warning", "description": "机器人可能被困住了"},
        {"code": "04013", "level": "warning", "description": "呼叫电梯超过3分钟"},
        {"code": "01203", "level": "info", "description": "全局路径规划失败，正在重试"},
        {"code": "02005", "level": "warning", "description": "姿态校正被触发（机器人可能被搬动）"},
    ]
    alert_info = random.choice(alert_types)
    alerts.append({
        "id": _gen_id(),
        "code": alert_info["code"],
        "level": alert_info["level"],
        "description": alert_info["description"],
        "timestamp": datetime.now().isoformat(),
        "resolved": False,
    })


# ======================================================================
# 启动
# ======================================================================

if __name__ == "__main__":
    # 初始化几条模拟告警
    _add_demo_alert()
    _add_demo_alert()

    # 连接设备（无真实设备时会失败，但不影响 Flask 服务运行）
    state_machine.connect_devices()

    # 启动状态机后台线程
    state_machine.start()

    print("=" * 50)
    print("  Lumi 咖啡配送调度服务")
    print("  后端 API: http://localhost:5000/api")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
