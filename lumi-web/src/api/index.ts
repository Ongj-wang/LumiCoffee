import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

// ---------- 类型定义 ----------

export interface Order {
  id: string
  room: string
  floor: number
  customer: string
  items: string[]
  status: 'pending' | 'ready' | 'queued' | 'delivering' | 'delivered' | 'cancelled'
  createdAt: string
  updatedAt: string
}

export interface TrayItem {
  drink: string
  tray_slot: number
}

export interface QueueItem {
  order_id: string
  floor: number
  room: string
  items: TrayItem[]
  priority: number
  position: number
  created_at: string
  waited_minutes: number
  tray_slots: number[]
}

export type ErrorAction = 'skip_current_cup' | 'cancel_current_cup'

export interface ErrorCup {
  drink: string
  tray_slot: number
}

export interface ErrorContext {
  source: string | null
  actionPending: boolean
  availableActions: ErrorAction[]
  cup: ErrorCup | null
  message: string | null
}

export interface LumiStatus {
  connected: boolean
  moveStatus: 'idle' | 'running' | 'succeeded' | 'failed' | 'canceled'
  battery: number
  currentFloor: number
  currentPose: { x: number; y: number; theta: number }
  charging: boolean
  estop: boolean
  currentTask: string | null
  robotState?: string
  targetFloor?: number | null
  targetRoom?: string | null
  errorContext?: ErrorContext
}

export interface LumiState {
  robotState: string
  currentTask: string | null
  targetFloor: number | null
  targetRoom: string | null
  queueLength: number
  errorContext?: ErrorContext
  devices: {
    agv: Record<string, unknown>
    arm: Record<string, unknown>
    vision: Record<string, unknown>
    gripper: Record<string, unknown>
  }
}

export interface Alert {
  id: string
  level: 'info' | 'warning' | 'error'
  code: string
  description: string
  timestamp: string
  resolved: boolean
}

export interface ConfigOptions {
  drinks: string[]
  floors: number[]
  rooms: Record<string, string[]>
}

// ---------- 配置接口 ----------

export const configApi = {
  /** 获取表单选项（饮品、楼层、房间） */
  getOptions(): Promise<{ data: ConfigOptions }> {
    return http.get('/config/options')
  },
}

// ---------- 订单接口 ----------

export const orderApi = {
  /** 获取订单列表（可按状态过滤） */
  getOrders(status?: string): Promise<{ data: Order[] }> {
    return http.get('/orders', { params: { status } })
  },

  /**
   * 送出配送：营业员手动录入饮品列表后，点击送出按钮调用
   * @param items 配送条目，每项包含饮品、楼层、房间号
   */
  dispatch(items: { drink: string; floor: number; room: string }[]): Promise<{ data: Order }> {
    return http.post('/orders/dispatch', { items })
  },

  /** 取消订单 */
  cancelOrder(orderId: string): Promise<void> {
    return http.post(`/orders/${orderId}/cancel`)
  },
}

// ---------- 队列接口 ----------

export const queueApi = {
  /** 获取当前配送队列 */
  getQueue(): Promise<{ data: QueueItem[] }> {
    return http.get('/queue')
  },

  /** 手动提升订单优先级 */
  prioritize(orderId: string): Promise<void> {
    return http.post(`/queue/prioritize/${orderId}`)
  },

  /** 从队列中移除 */
  removeFromQueue(orderId: string): Promise<void> {
    return http.post(`/queue/cancel/${orderId}`)
  },

  /** 开始下一单（触发队首订单配送） */
  dispatchNext(): Promise<{ data: { ok: boolean; order_id: string; floor: number; room: string } }> {
    return http.post('/queue/dispatch')
  },
}

// ---------- Lumi 状态接口 ----------

export const lumiApi = {
  /** 获取 Lumi 当前状态 */
  getStatus(): Promise<{ data: LumiStatus }> {
    return http.get('/lumi/status')
  },

  /** 获取状态机详细状态 */
  getState(): Promise<{ data: LumiState }> {
    return http.get('/lumi/state')
  },

  /** 提交人工干预动作 */
  submitErrorAction(action: ErrorAction): Promise<void> {
    return http.post('/lumi/handle_error', { action })
  },
}

// ---------- 告警接口 ----------

export const alertApi = {
  /** 获取告警列表 */
  getAlerts(): Promise<{ data: Alert[] }> {
    return http.get('/alerts')
  },

  /** 标记告警为已处理 */
  resolveAlert(alertId: string): Promise<void> {
    return http.post(`/alerts/${alertId}/resolve`)
  },
}