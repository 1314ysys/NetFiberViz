<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NModal, NButton, NInput, NInputNumber, NSelect, useMessage } from 'naive-ui'
import { useResourceStore } from '../../stores/resource'
import { useWiringStore } from '../../stores/wiring'
import Icon from '../ui/Icon.vue'
import PortShape from '../canvas/PortShape.vue'
import { shapeOf, familyColorOf } from '../../utils/portTypes'

const store = useResourceStore()
const wiring = useWiringStore()
const message = useMessage()

const show = computed({
  get: () => wiring.cordOpen,
  set: (v: boolean) => { wiring.cordOpen = v },
})

const form = ref({ cord_type: 'LC-LC 单模', length_m: 0, remark: '', force: false })
const err = ref('')

watch(show, (v) => {
  if (v) {
    form.value = { cord_type: 'LC-LC 单模', length_m: 0, remark: '', force: false }
    err.value = ''
    wiring.checkCompat()
  }
})

const warn = computed(() =>
  wiring.compat && wiring.compat.level === 'warn' ? wiring.compat.message : '')

async function submit() {
  if (warn.value && !form.value.force) {
    err.value = '接口类型不匹配，请勾选「强制创建」或先取消'
    return
  }
  try {
    const ok = await wiring.createCord({
      cord_type: form.value.cord_type,
      length_m: form.value.length_m,
      remark: form.value.remark,
      force: form.value.force,
    })
    if (ok) {
      message.success('跳纤已创建')
      show.value = false
    }
  } catch (e: any) {
    err.value = e.response?.data?.detail || '创建失败'
  }
}
</script>

<template>
  <n-modal v-model:show="show" :mask-closable="false">
    <div class="cd">
      <header class="cd-head">
        <Icon name="cable" :size="15" />
        <span class="cd-title">新建跳纤</span>
        <span class="cd-x" @click="show = false">✕</span>
      </header>

      <div class="cd-body">
        <!-- 两端端口 -->
        <div class="ends">
          <div class="end">
            <span class="end-tag a">A</span>
            <PortShape :shape="shapeOf(store.portTypes, wiring.aPort?.port_type || '')"
                       :size="20" fill="var(--c-used)"
                       :stroke="familyColorOf(store.portTypes, wiring.aPort?.port_type || '')" />
            <div class="end-txt">
              <b>{{ store.portLabel(wiring.aPort) }}</b>
              <span>{{ wiring.aPort?.port_type }}</span>
            </div>
          </div>
          <span class="arrow">↔</span>
          <div class="end">
            <span class="end-tag b">B</span>
            <PortShape :shape="shapeOf(store.portTypes, wiring.bPort?.port_type || '')"
                       :size="20" fill="var(--c-reserved)"
                       :stroke="familyColorOf(store.portTypes, wiring.bPort?.port_type || '')" />
            <div class="end-txt">
              <b>{{ store.portLabel(wiring.bPort) }}</b>
              <span>{{ wiring.bPort?.port_type }}</span>
            </div>
          </div>
        </div>

        <div v-if="warn" class="warn-box">
          <b>⚠ 接口类型不匹配</b>
          <p>{{ warn }}</p>
          <label class="chk">
            <input type="checkbox" v-model="form.force" />
            确认使用转接跳线强制创建
          </label>
        </div>

        <div class="grid2">
          <div>
            <label>跳纤型号</label>
            <n-input v-model:value="form.cord_type" size="small" placeholder="如 LC-LC 单模" />
          </div>
          <div>
            <label>长度 (m)</label>
            <n-input-number v-model:value="form.length_m" size="small" :min="0"
                            style="width: 100%" />
          </div>
        </div>
        <div>
          <label>备注</label>
          <n-input v-model:value="form.remark" type="textarea"
                   :autosize="{ minRows: 2, maxRows: 3 }" placeholder="选填" />
        </div>

        <p v-if="err" class="err">{{ err }}</p>
      </div>

      <footer class="cd-foot">
        <n-button quaternary @click="show = false">取消</n-button>
        <n-button type="primary" :loading="wiring.busy" @click="submit">创建跳纤</n-button>
      </footer>
    </div>
  </n-modal>
</template>

<style scoped>
.cd {
  width: 560px; max-width: 94vw; background: var(--bg-panel);
  border: 1px solid var(--border-strong); border-radius: 14px;
  box-shadow: var(--shadow-2); overflow: hidden;
}
.cd-head {
  display: flex; align-items: center; gap: 9px; padding: 14px 20px;
  border-bottom: 1px solid var(--border); color: var(--text-2);
}
.cd-title { font-size: 15px; font-weight: 600; color: var(--text-1); }
.cd-x { margin-left: auto; cursor: pointer; color: var(--text-3); font-size: 14px; }
.cd-body { padding: 18px 20px; display: flex; flex-direction: column; gap: 14px; }

.ends { display: flex; align-items: center; gap: 10px; }
.end {
  flex: 1; display: flex; align-items: center; gap: 9px; min-width: 0;
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 9px; padding: 10px 12px;
}
.end-tag {
  font-size: 10px; font-weight: 700; width: 16px; height: 16px; flex: none;
  display: grid; place-items: center; border-radius: 4px;
}
.end-tag.a { background: rgba(34,197,94,.2); color: var(--c-used); }
.end-tag.b { background: rgba(59,130,246,.2); color: var(--c-reserved); }
.end-txt { display: flex; flex-direction: column; line-height: 1.3; min-width: 0; }
.end-txt b {
  font-size: 12px; color: var(--text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.end-txt span { font-size: 10.5px; color: var(--text-3); }
.arrow { color: var(--text-3); font-size: 15px; flex: none; }

.warn-box {
  background: rgba(245,158,11,.10); border: 1px solid rgba(245,158,11,.32);
  border-radius: 9px; padding: 11px 14px; color: var(--warn); font-size: 12px;
}
.warn-box b { display: block; margin-bottom: 3px; }
.warn-box p { margin: 0 0 8px; color: var(--text-2); font-size: 11.5px; line-height: 1.6; }
.chk { display: flex; align-items: center; gap: 7px; font-size: 12px; cursor: pointer;
  color: var(--text-1); }
.chk input { width: 14px; height: 14px; accent-color: var(--accent); }

.grid2 { display: grid; grid-template-columns: 1fr 140px; gap: 12px; }
label { font-size: 11px; color: var(--text-2); display: block; margin-bottom: 5px; }
.err { color: var(--c-fault); font-size: 11.5px; margin: 0; }
.cd-foot {
  display: flex; justify-content: flex-end; gap: 10px; padding: 13px 20px;
  border-top: 1px solid var(--border);
}
</style>
