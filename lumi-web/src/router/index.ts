import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/order',
  },
  {
    path: '/order',
    name: 'OrderConfirm',
    component: () => import('../views/OrderConfirm'),
    meta: { title: '订单确认' },
  },
  {
    path: '/queue',
    name: 'QueueStatus',
    component: () => import('../views/QueueStatus'),
    meta: { title: '队列状态' },
  },
  {
    path: '/alerts',
    name: 'AlertPanel',
    component: () => import('../views/AlertPanel'),
    meta: { title: '异常处理' },
  },
  {
    path: '/calib',
    name: 'VisionCalib',
    component: () => import('../views/VisionCalib'),
    meta: { title: '视觉标定' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
