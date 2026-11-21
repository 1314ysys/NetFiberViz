import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true, chrome: false },
  },
  { path: '/', redirect: '/inventory' },
  {
    path: '/inventory',
    component: () => import('../views/InventoryView.vue'),
    meta: { title: '资源台账', sub: '机房 · 机柜 · 设备 · ODF 孔位' },
  },
  {
    path: '/topology/:roomId',
    component: () => import('../views/TopologyView.vue'),
    meta: { title: '机房画布', sub: '机柜节点 · 跳纤聚合连线 · 右键管理' },
  },
  {
    path: '/interior/rack/:id',
    component: () => import('../views/InteriorView.vue'),
    meta: { title: '机柜内部', sub: '设备按 U 位排列 · 拖拽调整' },
  },
  {
    path: '/interior/odf/:id',
    component: () => import('../views/InteriorView.vue'),
    meta: { title: '配线柜内部', sub: '盘自由拖拽 · 多选组合为单元柜' },
  },
  {
    path: '/ports/:kind/:id',
    component: () => import('../views/PortView.vue'),
    meta: { title: '端口视图', sub: '端口分组成排 · 点击布线' },
  },
  {
    path: '/wiring',
    component: () => import('../views/WiringView.vue'),
    meta: { title: '布线工作台', sub: '跳纤 · 盘间连接 · 纤芯熔接' },
  },
  {
    path: '/lldp',
    component: () => import('../views/LldpView.vue'),
    meta: { title: 'LLDP 自动布线', sub: '邻居表导入 · 匹配预览 · 一键生成' },
  },
  {
    path: '/links',
    component: () => import('../views/LinksView.vue'),
    meta: { title: '链路视图', sub: '端到端物理路径追踪' },
  },
  {
    path: '/changelog',
    component: () => import('../views/ChangelogView.vue'),
    meta: { title: '变更历史', sub: '全操作审计 · 可追溯' },
  },
  {
    path: '/system',
    component: () => import('../views/SystemView.vue'),
    meta: { title: '系统管理', sub: '用户 · 角色 · 机房授权' },
  },
  {
    path: '/screen/:roomId',
    component: () => import('../views/ScreenView.vue'),
    meta: { title: '机房总览大屏', chrome: false },
  },
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  if (!to.meta.public && !localStorage.getItem('token')) return '/login'
  return true
})

export default router
