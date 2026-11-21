<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const message = useMessage()
const session = useSessionStore()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    message.warning('请输入用户名与密码')
    return
  }
  loading.value = true
  try {
    await session.login(username.value, password.value)
    message.success('登录成功')
    router.push('/inventory')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '用户名或密码错误')
  } finally {
    loading.value = false
  }
}

const FEATURES = [
  { t: '拓扑组态', d: '机柜 / ODF / 单元柜 / 盘 自由拖拽布局' },
  { t: '物理连接建模', d: '跳纤 · 盘间熔接法兰 · 纤芯级对接' },
  { t: 'LLDP 自动布线', d: '邻居表导入解析，端到端自动串接' },
  { t: '全量审计', d: '每次变更留痕，可回放可导出' },
]
</script>

<template>
  <div class="login">
    <!-- 左：品牌介绍（固定深色，保证白字可读） -->
    <section class="hero theme-dark">
      <div class="glow"></div>
      <div class="hero-inner">
        <div class="logo-row">
          <div class="logo">◈</div>
          <div>
            <h1>FiberViz</h1>
            <p>机房跳纤布线可视化管理系统</p>
          </div>
        </div>
        <ul class="feats">
          <li v-for="f in FEATURES" :key="f.t">
            <span class="dot"></span>
            <div><b>{{ f.t }}</b><em>{{ f.d }}</em></div>
          </li>
        </ul>
        <div class="ver">v1.0 · 内网部署 · FastAPI + MySQL</div>
      </div>
    </section>

    <!-- 右：登录表单 -->
    <section class="form-side">
      <form class="card" @submit.prevent="submit">
        <h2>登录控制台</h2>
        <p class="sub">使用运维账号访问机房资源台账</p>

        <label>用户名</label>
        <input v-model="username" autocomplete="username" placeholder="请输入用户名" />

        <label>密码</label>
        <input v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
        <button type="submit" :disabled="loading">{{ loading ? '登录中…' : '登 录' }}</button>
        <p class="hint">首次部署请使用管理员账号登录，登录后立即修改初始密码</p>
      </form>
    </section>
  </div>
</template>

<style scoped>
.login { display: flex; height: 100vh; background: var(--bg-app); }

/* 左侧 */
.hero {
  flex: 1.15; position: relative; overflow: hidden;
  background: radial-gradient(1200px 600px at 20% 0%, #0e2a44 0%, #080d16 60%);
  display: flex; align-items: center; padding: 0 8%;
}
.glow {
  position: absolute; width: 520px; height: 520px; border-radius: 50%;
  background: radial-gradient(circle, rgba(56,189,248,.16), transparent 70%);
  top: -120px; right: -100px; filter: blur(20px);
}
.hero-inner { position: relative; z-index: 1; max-width: 460px; }
.logo-row { display: flex; align-items: center; gap: 14px; margin-bottom: 40px; }
.logo {
  width: 46px; height: 46px; border-radius: 13px; display: grid; place-items: center;
  background: var(--brand-grad); color: var(--brand-fg);
  font-size: 22px; font-weight: 700; box-shadow: 0 8px 28px rgba(56,189,248,.4);
}
h1 { margin: 0; font-size: 24px; letter-spacing: .5px; }
.logo-row p { margin: 2px 0 0; font-size: 12.5px; color: var(--text-3); }

.feats { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 18px; }
.feats li { display: flex; gap: 12px; align-items: flex-start; }
.feats .dot {
  width: 7px; height: 7px; margin-top: 6px; border-radius: 50%; flex: none;
  background: var(--accent); box-shadow: 0 0 0 4px rgba(56,189,248,.14);
}
.feats b { display: block; font-size: 13px; font-weight: 600; }
.feats em { font-style: normal; font-size: 12px; color: var(--text-3); }
.ver { margin-top: 44px; font-size: 11px; color: var(--text-3); letter-spacing: .4px; }

/* 右侧 */
.form-side { flex: 1; display: grid; place-items: center; padding: 24px; }
.card {
  width: 100%; max-width: 340px; display: flex; flex-direction: column;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: 30px 28px; box-shadow: var(--shadow-2);
}
.card h2 { margin: 0 0 4px; font-size: 18px; }
.card .sub { margin: 0 0 22px; font-size: 12px; color: var(--text-3); }
label { font-size: 11.5px; color: var(--text-2); margin-bottom: 6px; }
input {
  margin-bottom: 16px; padding: 9px 12px; font-size: 13px;
  background: var(--bg-elevated); color: var(--text-1);
  border: 1px solid var(--border); border-radius: 8px; outline: none; transition: .15s;
}
input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
button {
  margin-top: 6px; padding: 10px; border: none; border-radius: 8px; cursor: pointer;
  background: var(--brand-grad); color: var(--brand-fg);
  font-size: 13px; font-weight: 600; letter-spacing: 1px; transition: .15s;
}
button:hover:not(:disabled) { filter: brightness(1.08); }
button:disabled { opacity: .6; cursor: default; }
.hint { margin: 14px 0 0; font-size: 11px; color: var(--text-3); text-align: center; }

@media (max-width: 900px) {
  .hero { display: none; }
}
</style>
