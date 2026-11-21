<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NInputNumber, NSelect, NButton, NSpace } from 'naive-ui'

export interface FormField {
  key: string
  label: string
  type?: 'text' | 'number' | 'select' | 'textarea'
  options?: { label: string; value: any }[]
  required?: boolean
  placeholder?: string
  default?: any
  hint?: string
  min?: number
}

const props = withDefaults(defineProps<{
  show: boolean
  title: string
  fields: FormField[]
  initial?: Record<string, any>
  width?: number
  submitText?: string
  loading?: boolean
}>(), { width: 460, submitText: '确定', loading: false })

const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'submit', v: Record<string, any>): void
}>()

const model = ref<Record<string, any>>({})
const errors = ref<Record<string, string>>({})

const defaults = computed(() => {
  const o: Record<string, any> = {}
  for (const f of props.fields) o[f.key] = f.default ?? (f.type === 'number' ? null : '')
  return o
})

watch(() => props.show, (v) => {
  if (v) {
    model.value = { ...defaults.value, ...(props.initial || {}) }
    errors.value = {}
  }
})

function validate(): boolean {
  const e: Record<string, string> = {}
  for (const f of props.fields) {
    const v = model.value[f.key]
    if (f.required && (v === '' || v === null || v === undefined)) e[f.key] = '此项必填'
  }
  errors.value = e
  return Object.keys(e).length === 0
}

function submit() {
  if (!validate()) return
  emit('submit', { ...model.value })
}
</script>

<template>
  <n-modal :show="show" :mask-closable="false" @update:show="emit('update:show', $event)">
    <div class="dlg" :style="{ width: width + 'px' }">
      <header class="dlg-head">
        <span>{{ title }}</span>
        <button class="x" @click="emit('update:show', false)">✕</button>
      </header>
      <div class="dlg-body">
        <n-form label-placement="top" :show-feedback="false">
          <n-form-item v-for="f in fields" :key="f.key" :label="f.label">
            <div style="width: 100%">
              <n-input v-if="!f.type || f.type === 'text'" v-model:value="model[f.key]"
                       :placeholder="f.placeholder || f.label" clearable />
              <n-input v-else-if="f.type === 'textarea'" v-model:value="model[f.key]" type="textarea"
                       :autosize="{ minRows: 2, maxRows: 4 }" :placeholder="f.placeholder || f.label" />
              <n-input-number v-else-if="f.type === 'number'" v-model:value="model[f.key]"
                              :min="f.min" style="width: 100%" :placeholder="f.placeholder || f.label" />
              <n-select v-else-if="f.type === 'select'" v-model:value="model[f.key]"
                        :options="f.options || []" :placeholder="f.placeholder || f.label" />
              <div v-if="f.hint" class="hint">{{ f.hint }}</div>
              <div v-if="errors[f.key]" class="err">{{ errors[f.key] }}</div>
            </div>
          </n-form-item>
        </n-form>
      </div>
      <footer class="dlg-foot">
        <n-space justify="end">
          <n-button quaternary @click="emit('update:show', false)">取消</n-button>
          <n-button type="primary" :loading="loading" @click="submit">{{ submitText }}</n-button>
        </n-space>
      </footer>
    </div>
  </n-modal>
</template>

<style scoped>
.dlg {
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2);
  max-width: 92vw;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dlg-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  font-size: 14px; font-weight: 600;
}
.x { background: none; border: none; color: var(--text-3); cursor: pointer; font-size: 13px; }
.x:hover { color: var(--text-1); }
.dlg-body { padding: 18px; overflow: auto; }
.dlg-foot { padding: 12px 18px; border-top: 1px solid var(--border); }
.hint { font-size: 11px; color: var(--text-3); margin-top: 4px; }
.err { font-size: 11px; color: var(--c-fault); margin-top: 4px; }
</style>
