<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../../stores/session'
import { useResourceStore } from '../../stores/resource'
import { useUiStore } from '../../stores/ui'
import Icon from '../ui/Icon.vue'
import GlobalSearch from '../ui/GlobalSearch.vue'
import PendingPortDock from '../wiring/PendingPortDock.vue'
import PeerPicker from '../wiring/PeerPicker.vue'
import CordCreateDialog from '../wiring/CordCreateDialog.vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const resource = useResourceStore()
const ui = useUiStore()

interface NavItem { path: string; label: string; icon: string; group: string; coreOnly?: boolean }
const NAV: NavItem[] = [
  { path: '/inventory', label: '资源台账', icon: 'grid', group: '资源' },
  { path: '/topology', label: '机房画布', icon: 'topology', group: '资源' },
  { path: '/wiring', label: '布线工作台', icon: 'cable', group: '布线' },
  { path: '/lldp', label: 'LLDP 自动布线', icon: 'radar', group: '布线' },
  { path: '/links', label: '链路视图', icon: 'link', group: '布线' },
  { path: '/changelog', label: '变更历史', icon: 'history', group: '审计' },
  { path: '/system', label: '系统管理', icon: 'shield', group: '系统', coreOnly: true },
]

const groups = computed(() => {
  const m = new Map<string, NavItem[]>()
  for (const n of NAV) {
    if (n.coreOnly && !session.isCore) continue
    if (!m.has(n.group)) m.set(n.group, [])
    m.get(n.group)!.push(n)
  }
  return [...m.entries()]
})

const title = computed(() => (route.meta.title as string) || '机房跳纤布线')
const subtitle = computed(() => (route.meta.sub as string) || '')
const activePath = computed(() => {
  const seg = '/' + route.path.split('/')[1]
  if (seg === '/interior' || seg === '/ports') return '/topology'
  return seg
})

function go(path: string) {
  if (path === '/topology') {
    const rid = route.params.roomId || resource.rooms[0]?.id || 1
    router.push(`/topology/${rid}`)
  } else router.push(path)
}

async function refresh() {
  await resource.loadBase()
}

onMounted(async () => {
  if (!session.user) await session.fetchMe()
  if (!resource.rooms.length) await resource.loadBase()
})
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand">
        <div class="logo">◈</div>
        <div class="brand-txt">
          <b>FiberViz</b>
          <span>机房跳纤管理</span>
        </div>
      </div>

      <nav class="nav">
        <div v-for="[group, items] in groups" :key="group" class="nav-group">
          <div class="nav-label">{{ group }}</div>
          <button v-for="it in items" :key="it.path" class="nav-item"
                  :class="{ active: activePath === it.path }" @click="go(it.path)">
            <Icon :name="it.icon" :size="15" />
            <span>{{ it.label }}</span>
          </button>
        </div>
      </nav>

      <div class="side-foot">
        <div class="user">
          <div class="avatar">{{ (session.user?.display_name || session.user?.username || 'U').slice(0, 1).toUpperCase() }}</div>
          <div class="user-txt">
            <b>{{ session.user?.display_name || session.user?.username || '未登录' }}</b>
            <span :class="session.isCore ? 'role-core' : 'role-site'">
              {{ session.isCore ? '核心机房管理员' : '前端机房管理员' }}
            </span>
          </div>
          <button class="icon-btn" title="退出登录" @click="session.logout()"><Icon name="logout" :size="15" /></button>
        </div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div>
          <div class="page-title">{{ title }}</div>
          <div v-if="subtitle" class="page-sub">{{ subtitle }}</div>
        </div>
        <div class="grow"></div>
        <GlobalSearch />
        <button class="icon-btn" :title="ui.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
                @click="ui.toggle()">
          <Icon :name="ui.theme === 'dark' ? 'sun' : 'moon'" :size="15" />
        </button>
        <button class="icon-btn" title="刷新数据" :disabled="resource.loading" @click="refresh">
          <Icon name="refresh" :size="15" />
        </button>
        <router-link v-if="resource.rooms.length" :to="`/screen/${route.params.roomId || resource.rooms[0].id}`"
                     class="screen-link" title="进入大屏">
          <Icon name="screen" :size="15" /><span>大屏</span>
        </router-link>
      </header>

      <div class="content">
        <slot />
      </div>
    </div>

    <!-- 全局布线：A 端悬浮窗 + 跨机柜选择器 + 新建跳纤弹窗 -->
    <PendingPortDock />
    <PeerPicker />
    <CordCreateDialog />
  </div>
</template>

<style scoped>
.shell { display: flex; height: 100vh; overflow: hidden; }

/* 侧边栏 */
.side {
  width: 208px; flex: none; display: flex; flex-direction: column;
  background: var(--side-bg);
  border-right: 1px solid var(--side-border);
}
.brand { display: flex; align-items: center; gap: 10px; padding: 16px 16px 14px; }
.logo {
  width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
  background: var(--brand-grad); color: var(--brand-fg);
  font-size: 15px; font-weight: 700; box-shadow: 0 4px 14px rgba(56,189,248,.28);
}
.brand-txt { display: flex; flex-direction: column; line-height: 1.25; }
.brand-txt b { font-size: 14px; letter-spacing: .3px; }
.brand-txt span { font-size: 10.5px; color: var(--text-3); }

.nav { flex: 1; overflow-y: auto; padding: 6px 10px; }
.nav-group { margin-bottom: 14px; }
.nav-label {
  font-size: 10.5px; color: var(--text-3); letter-spacing: .8px;
  padding: 6px 8px; text-transform: uppercase;
}
.nav-item {
  width: 100%; display: flex; align-items: center; gap: 9px;
  padding: 7px 10px; margin-bottom: 2px; border: none; border-radius: 8px;
  background: transparent; color: var(--text-2); font-size: 12.5px;
  cursor: pointer; text-align: left; transition: background .12s, color .12s;
  position: relative;
}
.nav-item:hover { background: var(--bg-hover); color: var(--text-1); }
.nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 500; }
.nav-item.active::before {
  content: ''; position: absolute; left: -10px; top: 50%; transform: translateY(-50%);
  width: 3px; height: 16px; border-radius: 0 3px 3px 0; background: var(--accent);
}

.side-foot { padding: 10px; border-top: 1px solid var(--side-border); }
.user { display: flex; align-items: center; gap: 8px; padding: 6px; border-radius: 8px; }
.user:hover { background: var(--bg-hover); }
.avatar {
  width: 26px; height: 26px; border-radius: 50%; flex: none; display: grid; place-items: center;
  background: var(--avatar-bg); color: var(--accent);
  font-size: 11px; font-weight: 700; border: 1px solid var(--border-strong);
}
.user-txt { display: flex; flex-direction: column; line-height: 1.25; overflow: hidden; }
.user-txt b { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-txt span { font-size: 10.5px; color: var(--text-3); }
.user-txt .role-core { color: var(--accent); }
.user-txt .role-site { color: #f59e0b; }

/* 主区 */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.topbar {
  height: 54px; flex: none; display: flex; align-items: center; gap: 10px;
  padding: 0 20px; border-bottom: 1px solid var(--border);
  background: var(--topbar-bg); backdrop-filter: blur(8px);
}
.icon-btn {
  width: 30px; height: 30px; display: grid; place-items: center;
  background: transparent; border: 1px solid var(--border); border-radius: 8px;
  color: var(--text-2); cursor: pointer; transition: .12s;
}
.icon-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--accent); border-color: var(--border-strong); }
.icon-btn:disabled { opacity: .45; cursor: default; }
.screen-link {
  display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 12px;
  border-radius: 8px; border: 1px solid var(--border); color: var(--text-2);
  text-decoration: none; font-size: 12px;
}
.screen-link:hover { color: var(--accent); border-color: var(--border-strong); background: var(--bg-hover); }

.content { flex: 1; overflow: auto; padding: 18px 20px 24px; }
</style>
