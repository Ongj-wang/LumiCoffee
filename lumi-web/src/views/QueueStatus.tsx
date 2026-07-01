import { defineComponent, ref, onMounted, onUnmounted } from 'vue'
import { queueApi, lumiApi } from '../api'
import type { QueueItem, LumiStatus } from '../api'

export default defineComponent({
  name: 'QueueStatus',
  setup() {
    const queue = ref<QueueItem[]>([])
    const lumi = ref<LumiStatus | null>(null)
    const loading = ref(false)
    let timer: ReturnType<typeof setInterval> | null = null

    /** 加载队列和 Lumi 状态 */
    const refresh = async () => {
      loading.value = true
      try {
        const [queueRes, lumiRes] = await Promise.all([
          queueApi.getQueue(),
          lumiApi.getStatus(),
        ])
        queue.value = queueRes.data
        lumi.value = lumiRes.data
        console.log('刷新数据成功', queueRes.data)
      } catch (e) {
        console.error('刷新数据失败', e)
      } finally {
        loading.value = false
      }
    }

    /** 提升优先级 */
    const prioritize = async (orderId: string) => {
      try {
        await queueApi.prioritize(orderId)
        await refresh()
      } catch (e) {
        console.error('提升优先级失败', e)
      }
    }

    /** 取消队列中的订单 */
    const removeFromQueue = async (orderId: string) => {
      if (!confirm('确定从队列中移除该订单？')) return
      try {
        await queueApi.removeFromQueue(orderId)
        await refresh()
      } catch (e) {
        console.error('取消失败', e)
      }
    }

    /** 移动状态中文映射 */
    const moveStatusMap: Record<string, string> = {
      idle: '空闲',
      running: '配送中',
      succeeded: '已完成',
      failed: '失败',
      canceled: '已取消',
    }

    onMounted(() => {
      refresh()
      timer = setInterval(refresh, 5000) // 每5秒自动刷新
    })

    onUnmounted(() => {
      if (timer) clearInterval(timer)
    })

    return () => (
      <div>
        <div class="page-header">
          <h2>📦 队列状态</h2>
          <p>实时查看配送队列和 Lumi 运行状态（每 5 秒自动刷新）</p>
        </div>

        {/* Lumi 状态概览 */}
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-value" style={{ color: lumi.value?.connected ? 'var(--success)' : 'var(--danger)' }}>
              {lumi.value?.connected ? '● 已连接' : '● 未连接'}
            </div>
            <div class="stat-label">Lumi 连接状态</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">
              {lumi.value ? moveStatusMap[lumi.value.moveStatus] || lumi.value.moveStatus : '--'}
            </div>
            <div class="stat-label">当前任务状态</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style={{ color: (lumi.value?.battery ?? 100) < 20 ? 'var(--danger)' : 'inherit' }}>
              {lumi.value ? `${lumi.value.battery}%` : '--'}
            </div>
            <div class="stat-label">
              电池电量 {lumi.value?.charging ? '(充电中)' : ''}
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{lumi.value ? `${lumi.value.currentFloor}F` : '--'}</div>
            <div class="stat-label">
              当前位置 {lumi.value?.currentPose ? `(${lumi.value.currentPose.x.toFixed(1)}, ${lumi.value.currentPose.y.toFixed(1)})` : ''}
            </div>
          </div>
        </div>

        {/* Lumi 异常指示 */}
        {lumi.value?.estop && (
          <div class="card" style="border-color: var(--danger); background: #fef2f2;">
            <div style="color: var(--danger); font-weight: 600;">
              ⚠️ 急停状态已触发 — 请检查机器人硬件
            </div>
          </div>
        )}

        {/* 配送队列 */}
        <div class="card">
          <div class="card-title">
            <span>配送队列</span>
            <span style="font-size: 12px; color: var(--text-secondary); margin-left: 8px">
              共 {queue.value.length} 个任务
            </span>
            <button class="btn btn-outline btn-sm" onClick={refresh} style="margin-left: auto">
              🔄 刷新
            </button>
          </div>

          {queue.value.length === 0 ? (
            <div class="empty-state">
              <div class="empty-state-icon">📭</div>
              <p>队列为空，暂无配送任务</p>
            </div>
          ) : (
            <div class="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>队列</th>
                    <th>订单号</th>
                    <th>饮品</th>
                    <th>楼层</th>
                    <th>房间</th>
                    <th>等待</th>
                    <th>优先级</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.value.map((item) => (
                    <tr key={item.order_id}>
                      <td>
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: '28px',
                          height: '28px',
                          borderRadius: '50%',
                          background: item.position === 0 ? 'var(--primary)' : '#f1f5f9',
                          color: item.position === 0 ? '#fff' : 'var(--text-secondary)',
                          fontWeight: 600,
                          fontSize: '13px',
                        }}>
                          {item.position + 1}
                        </span>
                      </td>
                      <td style="font-weight: 600">{item.order_id}</td>
                      <td>{item.items.join('、')}</td>
                      <td>{item.floor}F</td>
                      <td>{item.room}</td>
                      <td style={{ color: item.waited_minutes > 10 ? 'var(--danger)' : 'inherit' }}>
                        {item.waited_minutes}分钟
                      </td>
                      <td>
                        <span class={`badge ${item.priority > 0 ? 'badge-warning' : 'badge-info'}`}>
                          {item.priority > 0 ? `加急 P${item.priority}` : '普通'}
                        </span>
                      </td>
                      <td>
                        <div style="display: flex; gap: 8px">
                          {item.priority === 0 && (
                            <button class="btn btn-outline btn-sm" onClick={() => prioritize(item.order_id)}>
                              ⬆️ 加急
                            </button>
                          )}
                          {item.position > 0 && (
                            <button class="btn btn-outline btn-sm" onClick={() => removeFromQueue(item.order_id)}>
                              ❌ 移除
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    )
  },
})
