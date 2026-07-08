import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue'
import { alertApi, lumiApi } from '../api'
import type { Alert } from '../api'

type ErrorAction = 'skip_current_cup' | 'cancel_current_cup'

interface ErrorCup {
  drink: string
  tray_slot: number
}

interface ErrorContext {
  source: string | null
  actionPending: boolean
  availableActions: ErrorAction[]
  cup: ErrorCup | null
  message: string | null
}

interface LumiState {
  robotState: string
  currentTask: string | null
  targetFloor: number | null
  targetRoom: string | null
  queueLength: number
  errorContext?: ErrorContext
}

export default defineComponent({
  name: 'AlertPanel',
  setup() {
    const actionableErrorSources = ['placing_coffee', 'navigating_to_room', 'returning'] as const
    const alerts = ref<Alert[]>([])
    const filter = ref<'all' | 'unresolved'>('unresolved')
    const lumiState = ref<LumiState | null>(null)
    const actionLoading = ref<ErrorAction | null>(null)
    let timer: ReturnType<typeof setInterval> | null = null

    const loadPageData = async () => {
      try {
        const [alertRes, stateRes] = await Promise.all([
          alertApi.getAlerts(),
          lumiApi.getState(),
        ])
        alerts.value = alertRes.data
        lumiState.value = stateRes.data
      } catch (e) {
        console.error('加载异常页数据失败', e)
      }
    }

    const resolveAlert = async (alertId: string) => {
      try {
        await alertApi.resolveAlert(alertId)
        await loadPageData()
      } catch (e) {
        console.error('处理告警失败', e)
      }
    }

    const submitErrorAction = async (action: ErrorAction) => {
      try {
        actionLoading.value = action
        await lumiApi.submitErrorAction(action)
        await loadPageData()
      } catch (e) {
        console.error('提交人工干预动作失败', e)
      } finally {
        actionLoading.value = null
      }
    }

    const filteredAlerts = computed(() => {
      if (filter.value === 'unresolved') {
        return alerts.value.filter((a) => !a.resolved)
      }
      return alerts.value
    })

    const stats = computed(() => {
      const unresolved = alerts.value.filter((a) => !a.resolved)
      return {
        total: alerts.value.length,
        unresolved: unresolved.length,
        warnings: unresolved.filter((a) => a.level === 'warning').length,
        errors: unresolved.filter((a) => a.level === 'error').length,
      }
    })

    const errorContext = computed(() => lumiState.value?.errorContext ?? null)

    const showRobotActionPanel = computed(() => {
      return (
        lumiState.value?.robotState === 'error' &&
        !!errorContext.value?.source &&
        actionableErrorSources.includes(errorContext.value.source as typeof actionableErrorSources[number])
      )
    })

    const canCancelCurrentCup = computed(() => {
      if (
        !!errorContext.value?.source &&
        actionableErrorSources.includes(errorContext.value.source as typeof actionableErrorSources[number])
      ) {
        return true
      }
      return !!errorContext.value?.availableActions?.includes('cancel_current_cup')
    })

    const canSkipCurrentCup = computed(() => {
      if (
        !!errorContext.value?.source &&
        actionableErrorSources.includes(errorContext.value.source as typeof actionableErrorSources[number])
      ) {
        return true
      }
      return !!errorContext.value?.availableActions?.includes('skip_current_cup')
    })

    const levelIcon: Record<string, string> = {
      info: 'ℹ️',
      warning: '⚠️',
      error: '🔴',
    }

    onMounted(() => {
      loadPageData()
      timer = setInterval(loadPageData, 10000)
    })

    onUnmounted(() => {
      if (timer) clearInterval(timer)
    })

    return () => (
      <div>
        <div class="page-header">
          <h2>异常处理</h2>
          <p>查看告警，并在放杯异常时进行人工处置</p>
        </div>

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

        {showRobotActionPanel.value && (
          <div class="card" style={{ borderColor: '#f59e0b', background: '#fffaf0' }}>
            <div class="card-title">当前机器人异常处置</div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '14px' }}>
              <div>
                当前任务：{lumiState.value?.currentTask || '--'}
              </div>
              <div>
                目标位置：
                {lumiState.value?.targetFloor && lumiState.value?.targetRoom
                  ? `${lumiState.value.targetFloor}F-${lumiState.value.targetRoom}`
                  : '--'}
              </div>
              <div>
                错误来源：{errorContext.value?.source || '--'}
              </div>
              <div>
                错误信息：{errorContext.value?.message || '--'}
              </div>
              <div>
                当前杯：
                {errorContext.value?.cup
                  ? `${errorContext.value.cup.drink} / 托盘第 ${errorContext.value.cup.tray_slot} 格`
                  : '--'}
              </div>
              {errorContext.value?.actionPending && (
                <div style={{ color: 'var(--warning)', fontWeight: 600 }}>
                  人工动作已提交，等待状态机处理
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
              {canCancelCurrentCup.value && (
                <button
                  class="btn btn-outline btn-sm"
                  disabled={actionLoading.value !== null || errorContext.value?.actionPending}
                  onClick={() => submitErrorAction('cancel_current_cup')}
                >
                  {actionLoading.value === 'cancel_current_cup' ? '提交中...' : '取消当前杯'}
                </button>
              )}

              {canSkipCurrentCup.value && (
                <button
                  class="btn btn-primary btn-sm"
                  disabled={actionLoading.value !== null || errorContext.value?.actionPending}
                  onClick={() => submitErrorAction('skip_current_cup')}
                >
                  {actionLoading.value === 'skip_current_cup' ? '提交中...' : '下一杯'}
                </button>
              )}
            </div>
          </div>
        )}

        <div class="card">
          <div class="card-title">
            <span>告警列表</span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
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
              <button class="btn btn-outline btn-sm" onClick={loadPageData}>
                刷新
              </button>
            </div>
          </div>

          {filteredAlerts.value.length === 0 ? (
            <div class="empty-state">
              <div class="empty-state-icon">✓</div>
              <p>{filter.value === 'unresolved' ? '没有待处理的告警' : '暂无告警记录'}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
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
                  <span style={{ fontSize: '20px', flexShrink: 0 }}>
                    {levelIcon[alert.level] || 'ℹ️'}
                  </span>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span class={`badge badge-${alert.level}`}>{alert.level.toUpperCase()}</span>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {new Date(alert.timestamp).toLocaleString('zh-CN')}
                      </span>
                      {alert.resolved && (
                        <span class="badge badge-ready">已处理</span>
                      )}
                    </div>
                    <div style={{ fontSize: '14px', fontWeight: 500 }}>
                      {alert.description}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      代码: {alert.code}
                    </div>
                  </div>

                  {!alert.resolved && (
                    <button
                      class="btn btn-outline btn-sm"
                      onClick={() => resolveAlert(alert.id)}
                      style={{ flexShrink: 0 }}
                    >
                      标记处理
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
