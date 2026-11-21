<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { useResourceStore, DEVICE_TYPE_LABEL } from '../stores/resource'
import Icon from '../components/ui/Icon.vue'

const route = useRoute()
const router = useRouter()
const store = useResourceStore()

const roomId = ref(Number(route.params.roomId) || 1)
const cords = ref<any[]>([])
const slots = ref<any[]>([])
const clock = ref('')
const lastUpdate = ref('')
let timer: any, clockTimer: any

const stats = computed(() => {
  const racks = store.racksOfRoom(roomId.value)
  const rackIds = new Set(racks.map(r => r.id))
  const devs = store.devices.filter(d => rackIds.has(d.rack_id))
  const odfPorts = store.ports.filter(p => p.owner_type === 'odf_slot')
  const devPorts = store.ports.filter(p => p.owner_type === 'device')
  return {
    racks: racks.length,
    devices: devs.length,
    cabinets: store.cabinets.filter(c => c.room_id === roomId.value).length,
    cords: cords.value.length,
    odfUsed: odfPorts.filter(p => p.status === 'used').length,
    odfTotal: odfPorts.length,
    devUsed: devPorts.filter(p => p.status === 'used').length,
    devTotal: devPorts.length,
    fault: store.ports.filter(p => p.status === 'fault').length,
    reserved: store.ports.filter(p => p.status === 'reserved').length,
  }
})

const odfUsage = computed(() => (stats.value.odfTotal ? stats.value.odfUsed / stats.value.odfTotal : 0))
const devUsage = computed(() => (stats.value.devTotal ? stats.value.devUsed / stats.value.devTotal : 0))

/** ODF 按单元柜字母聚合占用率 */
const unitHeat = computed(() => {
  const m = new Map<string, { used: number; total: number }>()
  for (const p of store.ports) {
    if (p.owner_type !== 'odf_slot') continue
    const u = (p.port_no || '?').charAt(0)
    if (!m.has(u)) m.set(u, { used: 0, total: 0 })
    const e = m.get(u)!
    e.total++
    if (p.status === 'used') e.used++
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
    .map(([unit, v]) => ({ unit, ...v, pct: v.total ? v.used / v.total : 0 }))
})

/** 端口占用 Top 设备 */
const topDevices = computed(() => {
  const racks = store.racksOfRoom(roomId.value)
  const rackIds = new Set(racks.map(r => r.id))
  return store.devices
    .filter(d => rackIds.has(d.rack_id))
    .map(d => {
      const ps = store.portsOfDevice(d.id)
      return { name: d.name, type: d.device_type, used: ps.filter(p => p.status === 'used').length, total: ps.length }
    })
    .filter(d => d.total > 0)
    .sort((a, b) => b.used / b.total - a.used / a.total)
    .slice(0, 6)
})

const alarms = computed(() =>
  store.ports.filter(p => p.status === 'fault')
    .map(p => ({ label: p.port_no, owner: p.owner_type === 'device' ? '设备端口' : 'ODF 孔位' }))
    .slice(0, 8))

async function refresh() {
  await store.loadBase()
  cords.value = (await api.get('/patch-cords')).data
  lastUpdate.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function tick() {
  clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

onMounted(async () => {
  tick()
  clockTimer = setInterval(tick, 1000)
  await refresh()
  timer = setInterval(refresh, 30000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearInterval(clockTimer)
})

function exit() { router.push('/inventory') }
</script>

<template>
  <div class="screen theme-dark">
    <div class="bg-grid"></div>
    <div class="bg-glow"></div>

    <header class="sc-head">
      <div class="sc-brand">
        <div class="logo">◈</div>
        <div>
          <h1>{{ store.rooms.find(r => r.id === roomId)?.name || '机房' }} · 跳纤布线总览</h1>
          <p>FiberViz Operations Console</p>
        </div>
      </div>
      <div class="sc-right">
        <span class="live"><i></i>实时</span>
        <span class="clock mono">{{ clock }}</span>
        <button class="exit" @click="exit"><Icon name="close" :size="14" />退出大屏</button>
      </div>
    </header>

    <main class="sc-body">
      <!-- 统计卡 -->
      <section class="stat-row">
        <div class="s-card">
          <div class="s-ico"><Icon name="server" :size="17" /></div>
          <div class="s-num">{{ stats.racks }}</div><div class="s-lab">机柜</div>
        </div>
        <div class="s-card">
          <div class="s-ico"><Icon name="box" :size="17" /></div>
          <div class="s-num">{{ stats.devices }}</div><div class="s-lab">设备</div>
        </div>
        <div class="s-card">
          <div class="s-ico"><Icon name="grid" :size="17" /></div>
          <div class="s-num">{{ stats.cabinets }}</div><div class="s-lab">ODF 配线柜</div>
        </div>
        <div class="s-card accent">
          <div class="s-ico"><Icon name="cable" :size="17" /></div>
          <div class="s-num">{{ stats.cords }}</div><div class="s-lab">在用跳纤</div>
        </div>
        <div class="s-card danger">
          <div class="s-ico"><Icon name="warn" :size="17" /></div>
          <div class="s-num">{{ stats.fault }}</div><div class="s-lab">故障端口</div>
        </div>
      </section>

      <!-- 主体三栏 -->
      <section class="sc-main">
        <!-- 左：端口占用率 -->
        <div class="sc-panel">
          <h3>端口资源占用</h3>
          <div class="gauge-block">
            <div class="gauge-label"><span>ODF 孔位</span><b>{{ stats.odfUsed }}/{{ stats.odfTotal }}</b></div>
            <div class="bar"><div class="bar-fill odf" :style="{ width: odfUsage * 100 + '%' }"></div></div>
            <div class="gauge-label"><span>设备端口</span><b>{{ stats.devUsed }}/{{ stats.devTotal }}</b></div>
            <div class="bar"><div class="bar-fill dev" :style="{ width: devUsage * 100 + '%' }"></div></div>
          </div>

          <h3 style="margin-top: 22px">ODF 单元柜占用热力</h3>
          <div class="heat-list">
            <div v-for="u in unitHeat" :key="u.unit" class="heat-row">
              <span class="h-unit">{{ u.unit }}</span>
              <div class="h-bar"><div class="h-fill" :style="{ width: u.pct * 100 + '%' }"></div></div>
              <span class="h-num">{{ u.used }}/{{ u.total }}</span>
            </div>
            <div v-if="!unitHeat.length" class="dim">暂无 ODF 数据</div>
          </div>
        </div>

        <!-- 中：设备占用 Top -->
        <div class="sc-panel">
          <h3>设备端口占用 Top</h3>
          <div class="top-list">
            <div v-for="d in topDevices" :key="d.name" class="top-row">
              <div class="t-head">
                <span class="t-name">{{ d.name }}</span>
                <span class="t-type">{{ DEVICE_TYPE_LABEL[d.type] || d.type }}</span>
                <span class="t-num">{{ d.used }}/{{ d.total }}</span>
              </div>
              <div class="bar sm"><div class="bar-fill dev" :style="{ width: (d.used / d.total) * 100 + '%' }"></div></div>
            </div>
            <div v-if="!topDevices.length" class="dim">暂无设备数据</div>
          </div>
        </div>

        <!-- 右：告警 -->
        <div class="sc-panel">
          <h3>异常与预留</h3>
          <div class="alarm-summary">
            <div class="al-item danger">
              <b>{{ stats.fault }}</b><span>故障</span>
            </div>
            <div class="al-item warn">
              <b>{{ stats.reserved }}</b><span>预留</span>
            </div>
          </div>
          <div class="alarm-list">
            <div v-for="(a, i) in alarms" :key="i" class="alarm-row">
              <i class="al-dot"></i>
              <span class="mono">{{ a.label }}</span>
              <span class="dim">{{ a.owner }}</span>
            </div>
            <div v-if="!alarms.length" class="ok-state">
              <Icon name="check" :size="16" />全部正常，无故障端口
            </div>
          </div>
        </div>
      </section>

      <footer class="sc-foot">数据每 30 秒自动刷新 · 最后更新 {{ lastUpdate }}</footer>
    </main>
  </div>
</template>

<style scoped>
.screen {
  position: relative; min-height: 100vh; overflow: hidden;
  background: radial-gradient(1400px 700px at 50% -10%, #0d2036 0%, #050a12 65%);
  color: var(--text-1); padding: 26px 34px; display: flex; flex-direction: column;
}
.bg-grid {
  position: absolute; inset: 0; pointer-events: none; opacity: .35;
  background-image: linear-gradient(rgba(56,189,248,.06) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(56,189,248,.06) 1px, transparent 1px);
  background-size: 46px 46px;
  mask-image: radial-gradient(ellipse at 50% 0%, #000 20%, transparent 75%);
}
.bg-glow {
  position: absolute; width: 700px; height: 700px; border-radius: 50%;
  background: radial-gradient(circle, rgba(56,189,248,.13), transparent 68%);
  top: -280px; left: 50%; transform: translateX(-50%); filter: blur(24px); pointer-events: none;
}

.sc-head { position: relative; display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.sc-brand { display: flex; align-items: center; gap: 14px; }
.logo {
  width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center;
  background: linear-gradient(135deg, #38bdf8, #6366f1); color: #041018; font-size: 20px; font-weight: 700;
  box-shadow: 0 6px 24px rgba(56,189,248,.4);
}
.sc-brand h1 { margin: 0; font-size: 21px; letter-spacing: .6px; }
.sc-brand p { margin: 2px 0 0; font-size: 11px; color: var(--text-3); letter-spacing: 1.2px; }
.sc-right { display: flex; align-items: center; gap: 16px; }
.live { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #22c55e; }
.live i { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; animation: pulse 1.6s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(34,197,94,.5) } 50% { opacity: .55; box-shadow: 0 0 0 6px rgba(34,197,94,0) } }
.clock { font-size: 15px; color: var(--text-2); letter-spacing: 1px; }
.exit { display: inline-flex; align-items: center; gap: 5px; background: transparent;
  border: 1px solid var(--border-strong); color: var(--text-2); padding: 5px 11px;
  border-radius: 8px; font-size: 12px; cursor: pointer; }
.exit:hover { color: var(--text-1); border-color: var(--accent); }

.sc-body { position: relative; flex: 1; display: flex; flex-direction: column; gap: 16px; }

.stat-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.s-card {
  background: rgba(15,22,35,.75); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 16px 18px; position: relative; overflow: hidden; backdrop-filter: blur(6px);
}
.s-card::after { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #334155; }
.s-card.accent::after { background: #38bdf8; }
.s-card.danger::after { background: #ef4444; }
.s-ico { color: var(--text-3); margin-bottom: 6px; }
.s-num { font-size: 30px; font-weight: 700; line-height: 1.1; letter-spacing: -.5px; }
.s-card.accent .s-num { color: #38bdf8; }
.s-card.danger .s-num { color: #ef4444; }
.s-lab { font-size: 11.5px; color: var(--text-3); margin-top: 3px; }

.sc-main { flex: 1; display: grid; grid-template-columns: 1.05fr 1fr 0.85fr; gap: 14px; min-height: 0; }
.sc-panel {
  background: rgba(15,22,35,.72); border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 16px 18px; backdrop-filter: blur(6px); overflow: auto;
}
.sc-panel h3 { margin: 0 0 14px; font-size: 12.5px; font-weight: 600; color: var(--text-2);
  letter-spacing: .4px; display: flex; align-items: center; gap: 7px; }
.sc-panel h3::before { content: ''; width: 3px; height: 12px; border-radius: 2px; background: var(--accent); }

.gauge-label { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-2); margin-bottom: 6px; }
.gauge-label b { color: var(--text-1); font-family: monospace; }
.bar { height: 8px; background: #0b1220; border-radius: 5px; overflow: hidden; margin-bottom: 16px; }
.bar.sm { height: 5px; margin-bottom: 0; margin-top: 6px; }
.bar-fill { height: 100%; border-radius: 5px; transition: width .6s ease; }
.bar-fill.odf { background: linear-gradient(90deg, #0ea5e9, #38bdf8); }
.bar-fill.dev { background: linear-gradient(90deg, #22c55e, #4ade80); }

.heat-list { display: flex; flex-direction: column; gap: 9px; }
.heat-row { display: flex; align-items: center; gap: 10px; }
.h-unit { width: 16px; font-size: 12px; color: var(--text-2); font-weight: 600; }
.h-bar { flex: 1; height: 7px; background: #0b1220; border-radius: 4px; overflow: hidden; }
.h-fill { height: 100%; background: linear-gradient(90deg, #22c55e, #eab308, #ef4444); transition: width .6s; }
.h-num { width: 52px; text-align: right; font-size: 11px; color: var(--text-3); font-family: monospace; }

.top-list { display: flex; flex-direction: column; gap: 13px; }
.t-head { display: flex; align-items: baseline; gap: 8px; }
.t-name { font-size: 12.5px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-type { font-size: 10.5px; color: var(--accent); background: rgba(56,189,248,.1); padding: 1px 7px; border-radius: 999px; }
.t-num { font-size: 11px; color: var(--text-3); font-family: monospace; }

.alarm-summary { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.al-item { border-radius: var(--radius); padding: 12px; text-align: center; border: 1px solid; }
.al-item.danger { border-color: rgba(239,68,68,.35); background: rgba(239,68,68,.07); }
.al-item.warn { border-color: rgba(245,158,11,.35); background: rgba(245,158,11,.07); }
.al-item b { display: block; font-size: 22px; }
.al-item.danger b { color: #ef4444; }
.al-item.warn b { color: #f59e0b; }
.al-item span { font-size: 11px; color: var(--text-3); }

.alarm-list { display: flex; flex-direction: column; gap: 6px; }
.alarm-row { display: flex; align-items: center; gap: 8px; font-size: 12px;
  padding: 6px 9px; border-radius: 6px; background: rgba(239,68,68,.05); }
.al-dot { width: 6px; height: 6px; border-radius: 50%; background: #ef4444; flex: none; }
.alarm-row .dim { margin-left: auto; font-size: 10.5px; }
.ok-state { display: flex; align-items: center; gap: 8px; color: #22c55e; font-size: 12.5px;
  padding: 16px 0; justify-content: center; }

.sc-foot { text-align: center; font-size: 11px; color: var(--text-3); padding-top: 14px; letter-spacing: .5px; }

@media (max-width: 1400px) {
  .sc-main { grid-template-columns: 1fr 1fr; }
  .sc-main > :last-child { grid-column: span 2; }
}
</style>
