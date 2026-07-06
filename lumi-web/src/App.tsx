import { defineComponent } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

export default defineComponent({
  name: 'App',
  setup() {
    const navItems = [
      { path: '/order', icon: '📋', label: '订单确认' },
      { path: '/queue', icon: '📦', label: '队列状态' },
      { path: '/alerts', icon: '🔔', label: '异常处理' },
      { path: '/calib', icon: '📷', label: '视觉标定' },
    ]

    return () => (
      <div class="app-layout">
        {/* 侧边栏 */}
        <aside class="sidebar">
          <div class="sidebar-header">
            <h1>☕ Lumi 配送</h1>
            <p>咖啡配送调度中心</p>
          </div>
          <nav class="sidebar-nav">
            {navItems.map((item) => (
              <RouterLink key={item.path} to={item.path} class="nav-item">
                <span class="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </RouterLink>
            ))}
          </nav>
          <div style="padding: 16px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-secondary);">
            Lumi Coffee v1.0
          </div>
        </aside>

        {/* 主内容区 */}
        <main class="main-content">
          <RouterView />
        </main>
      </div>
    )
  },
})
