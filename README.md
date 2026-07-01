# Lumi Coffee - JAKA Lumi 咖啡配送机器人系统

基于 JAKA Lumi 移动底盘的咖啡配送机器人调度控制系统。营业员通过 Web 界面手动录入饮品订单，系统自动调度机器人完成跨楼层配送。

## 系统架构

三层架构设计：

```
┌──────────────┐    HTTP/REST    ┌──────────────┐   共享状态    ┌──────────────┐
│   Vue 前端    │ ──────────────> │  Flask 服务   │ <──────────> │  状态机总控   │
│  (人机交互)   │   localhost:5173│  localhost:5000│              │  (设备协调)   │
└──────────────┘                 └──────────────┘              └──────────────┘
                                                                      │
                                                        ┌─────────────┼─────────────┐
                                                        ▼             ▼             ▼
                                                   AGV 底盘      JAKA 机械臂     视觉/夹爪
```

## 目录结构

```
LumiCoffee/
├── lumi-web/                # 前端 (Vue 3 + TSX)
│   ├── src/
│   │   ├── api/             # API 请求封装
│   │   ├── views/           # 页面组件
│   │   │   ├── OrderConfirm.tsx   # 订单录入与送出
│   │   │   ├── QueueStatus.tsx    # 配送队列监控
│   │   │   └── AlertPanel.tsx     # 告警与异常处理
│   │   └── router/          # 路由配置
│   └── vite.config.ts       # Vite 构建配置
│
├── server/                  # Flask 后端服务
│   ├── app.py               # 主入口，API 路由
│   └── server_config.json   # 业务配置（饮品、楼层、房间）
│
├── controller/              # 状态机总控
│   ├── config.py            # 设备连接与运行参数
│   ├── state_machine.py     # 状态机核心（12 状态）
│   ├── task_manager.py      # 任务队列管理
│   └── devices/             # 设备适配器
│       ├── agv_adapter.py   # AGV 底盘适配器
│       ├── arm_adapter.py   # JAKA 机械臂适配器
│       ├── vision_adapter.py   # 视觉相机（预留）
│       └── gripper_adapter.py  # 夹爪（预留）
│
├── agv_comm/                # AGV 通讯模组
│   ├── client.py            # HTTP 客户端封装
│   ├── movement.py          # 运动控制
│   ├── navigation.py        # 导航管理
│   ├── status.py            # 状态查询
│   └── system.py            # 系统管理
│
├── JK_SDK/                  # JAKA 机械臂 SDK
│
└── 资料手册/                 # 硬件文档
    ├── AGV API手册.pdf
    └── JAKA Lumi底盘使用手册.pdf
```

## 环境要求

- **Python** >= 3.10
- **Node.js** >= 18
- **npm** >= 9

## 快速开始

### 1. 安装依赖

**后端：**

```bash
pip install flask flask-cors requests
```

**前端：**

```bash
cd lumi-web
npm install
```

### 2. 修改配置

**设备连接配置** — `controller/config.py`：

```python
AGV_HOST = "192.168.10.10"        # AGV 底盘 IP
AGV_PORT = 31001                   # AGV 端口
ARM_IP = "192.168.182.132"        # 机械臂 IP
ARM_HOME_JOINTS = [0,0,0,0,0,0]  # 机械臂安全位关节角度
TAKE_CUP_READY_POSE = [0,0,0,0,0,0]  # 取杯准备位（关节角度）
CUP_POSE = [...]                    # 各托盘槽位笛卡尔位姿
PLACE_POSE = [0,0,0,0,0,0]       # 放置饮品位姿
PLACE_CUP_OVER = [0,0,0,0,0,0]  # 放置完成后位姿
```

**业务配置** — `server/server_config.json`：

```json
{
  "drinks": ["美式咖啡", "拿铁", ...],
  "floors": [1, 2, 3, ...],
  "rooms": { "1": ["101", "102", ...], ... }
}
```

### 3. 启动服务

**启动后端（先启动）：**

```bash
python server/app.py
```

后端运行在 `http://localhost:5000`。

**启动前端：**

```bash
cd lumi-web
npm run dev
```

前端运行在 `http://localhost:5173`，API 请求自动代理到后端。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config/options` | 获取表单选项（饮品、楼层、房间） |
| GET | `/api/orders` | 获取订单列表（可按 `?status=` 过滤） |
| POST | `/api/orders/dispatch` | 送出配送（批量提交饮品条目） |
| POST | `/api/orders/:id/cancel` | 取消订单 |
| GET | `/api/queue` | 获取当前配送队列 |
| POST | `/api/queue/prioritize/:id` | 提升订单优先级 |
| POST | `/api/queue/cancel/:id` | 从队列移除 |
| POST | `/api/queue/dispatch` | 手动触发下一单配送 |
| GET | `/api/lumi/status` | 获取 Lumi 状态 |
| GET | `/api/lumi/state` | 获取状态机与设备状态 |
| POST | `/api/lumi/resolve_error` | 解除错误状态 |
| POST | `/api/lumi/estop` | 急停 |
| GET | `/api/alerts` | 获取告警列表 |
| POST | `/api/alerts/:id/resolve` | 标记告警已处理 |

## 状态机

状态机在后台线程中运行（0.5s 周期），管理任务生命周期：

```
IDLE → DISPATCHING → MOVING_TO_ELEVATOR → TAKING_ELEVATOR
  ↑                                            ↓
RETURNING ← COMPLETED ← PLACING_COFFEE ← VISION_CALIBRATING
```

| 状态 | 说明 |
|------|------|
| `idle` | 在取餐点待命 |
| `dispatching` | 取出任务，读取目标楼层和房间 |
| `moving_to_elevator` | AGV 前往电梯口 |
| `taking_elevator` | 乘梯至目标楼层 |
| `navigating_to_room` | 导航至房间门口 |
| `vision_calibrating` | 视觉定位校准 |
| `placing_coffee` | 根据 tray_slot 取杯并放置饮品 |
| `returning` | 返回取餐点 |
| `completed` | 任务完成 |
| `error` | 异常状态 |
| `charging` | 前往充电 |

## 托盘系统

咖啡按营业员添加顺序放置在机器人托盘上，每杯分配一个 `tray_slot`（从 0 开始）：

```
托盘: [ slot 0: 拿铁 ] [ slot 1: 美式 ] [ slot 2: 冰拿铁 ]
```

- 前端送出时，后端按提交顺序全局分配 `tray_slot`，再按楼层-房间分组生成任务
- 状态机放置时通过 `_compute_pick_pose(tray_slot)` 查找对应槽位的笛卡尔位姿
- 托盘位姿在 `controller/config.py` 的 `CUP_POSE` 中配置（需现场标定）

## 任务调度策略

- **优先级排序**：手动加急 > 超时提权（15 分钟） > FIFO
- **同楼层合并**：完成一次放置后检查同楼层其他任务，减少电梯往返
- **电量管理**：低于 20% 完成当前批次后回充，低于 10% 立即中止任务

## 页面说明

| 路由 | 页面 | 功能 |
|------|------|------|
| `/order` | 订单确认 | 营业员手动录入饮品、楼层、房间，批量送出 |
| `/queue` | 队列状态 | 查看当前配送队列，调整优先级，手动触发配送 |
| `/alerts` | 异常处理 | 查看和处理系统告警 |

## 硬件依赖

| 设备 | 型号 | 状态 |
|------|------|------|
| 移动底盘 | JAKA Lumi AGV | 已集成（agv_comm 模组） |
| 机械臂 | JAKA（JK_SDK） | 已集成（关节/直线运动 + IO 控制，SDK 返回元组 ret[0]==0 为成功） |
| 视觉相机 | 待定 | 预留接口（stub） |
| 夹爪 | 待定 | 预留接口（stub） |

## License

Private - 内部项目
