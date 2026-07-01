import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue'
import { alertApi } from '../api'
import type { Alert } from '../api'

export default defineComponent({
  name: 'AlertPanel',
  setup() {
    const alerts = ref<Alert[]>([])
    const filter = ref<'all' | 'unresolved'>('unresolved')
    let timer: ReturnType<typeof setInterval> | null = null

    /** 加载告警列表 */
    const loadAlerts = async () => {
      try {
        const res = await alertApi.getAlerts()
        alerts.value = res.data
      } catch (e) {
        console.error('加载告警失败', e)
      }
    }

    /** 标记已处理 */
    const resolve = async (alertId: string) => {
      try {
        await alertApi.resolveAlert(alertId)
        await loadAlerts()
      } catch (e) {
        console.error('处理告警失败', e)
      }
    }

    /** 过滤后的告警 */
    const filteredAlerts = computed(() => {
      if (filter.value === 'unresolved') {
        return alerts.value.filter((a) => !a.resolved)
      }
      return alerts.value
    })

    /** 统计 */
    const stats = computed(() => {
      const unresolved = alerts.value.filter((a) => !a.resolved)
      return {
        total: alerts.value.length,
        unresolved: unresolved.length,
        warnings: unresolved.filter((a) => a.level === 'warning').length,
        errors: unresolved.filter((a) => a.level === 'error').length,
      }
    })

    /** 级别图标 */
    const levelIcon: Record<string, string> = {
      info: 'ℹ️',
      warning: '⚠️',
      error: '🔴',
    }

    onMounted(() => {
      loadAlerts()
      timer = setInterval(loadAlerts, 10000)
    })

    onUnmounted(() => {
      if (timer) clearInterval(timer)
    })

    return () => (
      <div>
        <div class="page-header">
          <h2>🔔 异常处理</h2>
          <p>查看和处理 Lumi 运行中的异常告警（每 10 秒自动刷新）</p>
        </div>

        {/* 统计卡片 */}
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-value" style={{ color: 'var(--danger)' }}>{stats.value.unresolved}</div>
            <div class="stat-label">待处理告警</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style={{ color: 'var(--warning)' }}>{stats.value.warnings}</div>
            <div class="stat-label">Warning 级别</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style={{ color: 'var(--danger)' }}>{stats.value.errors}</div>
            <div class="stat-label">Error 级别</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{stats.value.total}</div>
            <div class="stat-label">告警总数</div>
          </div>
        </div>

        {/* 告警列表 */}
        <div class="card">
          <div class="card-title">
            <span>告警列表</span>
            <div style="margin-left: auto; display: flex; gap: 8px">
              <button
                class={`btn btn-sm ${filter.value === 'unresolved' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => (filter.value = 'unresolved')}
              >
                待处理 ({stats.value.unresolved})
              </button>
              <button
                class={`btn btn-sm ${filter.value === 'all' ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => (filter.value = 'all')}
              >
                全部
              </button>
              <button class="btn btn-outline btn-sm" onClick={loadAlerts}>
                🔄 刷新
              </button>
            </div>
          </div>

          {filteredAlerts.value.length === 0 ? (
            <div class="empty-state">
              <div class="empty-state-icon">✅</div>
              <p>{filter.value === 'unresolved' ? '没有待处理的告警' : '暂无告警记录'}</p>
            </div>
          ) : (
            <div style="display: flex; flex-direction: column; gap: 12px">
              {filteredAlerts.value.map((alert) => (
                <div
                  key={alert.id}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '16px',
                    borderRadius: '10px',
                    border: `1px solid ${
                      alert.level === 'error' ? '#fecaca' :
                      alert.level === 'warning' ? '#fde68a' : '#bfdbfe'
                    }`,
                    background: alert.resolved ? '#f9fafb' : '#fff',
                    opacity: alert.resolved ? 0.6 : 1,
                  }}
                >
                  <span style="font-size: 20px; flex-shrink: 0">
                    {levelIcon[alert.level] || 'ℹ️'}
                  </span>

                  <div style="flex: 1; min-width: 0">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px">
                      <span class={`badge badge-${alert.level}`}>{alert.level.toUpperCase()}</span>
                      <span style="font-size: 12px; color: var(--text-secondary)">
                        {new Date(alert.timestamp).toLocaleString('zh-CN')}
                      </span>
                      {alert.resolved && (
                        <span class="badge badge-ready">已处理</span>
                      )}
                    </div>
                    <div style="font-size: 14px; font-weight: 500">
                      {alert.description}
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px">
                      代码: {alert.code}
                    </div>
                  </div>

                  {!alert.resolved && (
                    <button
                      class="btn btn-outline btn-sm"
                      onClick={() => resolve(alert.id)}
                      style="flex-shrink: 0"
                    >
                      ✅ 标记处理
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  },
})
