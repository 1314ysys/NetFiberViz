<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { NButton, NDataTable, NTag, useMessage, useDialog } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { api } from '../api/client'
import { useResourceStore } from '../stores/resource'
import { roomPath, roomSelectOptions } from '../utils/rooms'
import Icon from '../components/ui/Icon.vue'
import DialogForm from '../components/ui/DialogForm.vue'
import type { FormField } from '../components/ui/DialogForm.vue'

const message = useMessage()
const dialog = useDialog()
const store = useResourceStore()

const users = ref<any[]>([])
const loading = ref(false)

const roomOptions = computed(() => roomSelectOptions(store.rooms as any))

async function load() {
  loading.value = true
  try {
    users.value = (await api.get('/auth/users')).data
  } catch (e: any) {
    message.error(e.response?.data?.detail || '无权限访问')
  } finally {
    loading.value = false
  }
}

const dlg = ref<{ show: boolean; title: string; fields: FormField[]; initial: any; submit: (v: any) => Promise<void> }>(
  { show: false, title: '', fields: [], initial: {}, submit: async () => {} })

function openDlg(title: string, fields: FormField[], initial: any, submit: (v: any) => Promise<void>) {
  dlg.value = { show: true, title, fields, initial, submit }
}

const roleOptions = [
  { label: '核心机房管理员（全量读写）', value: 'core_admin' },
  { label: '前端机房管理员（仅写授权机房）', value: 'site_admin' },
]

function newUser() {
  openDlg('新建用户', [
    { key: 'username', label: '用户名', required: true, placeholder: '登录账号' },
    { key: 'password', label: '初始密码', required: true, placeholder: '至少 8 位' },
    { key: 'display_name', label: '显示名' },
    { key: 'role', label: '角色', type: 'select', required: true, default: 'site_admin', options: roleOptions },
    {
      key: 'room_ids', label: '授权机房', type: 'select', options: roomOptions.value,
      hint: '站点管理员可写所选机房及其所有子机房；核心管理员无需选择',
    },
  ], { room_ids: [] }, async (v) => {
    try {
      await api.post('/auth/users', {
        username: v.username, password: v.password, display_name: v.display_name || '',
        role: v.role, room_ids: v.role === 'core_admin' ? [] : (v.room_ids || []),
      })
      message.success('用户已创建')
      dlg.value.show = false
      await load()
    } catch (e: any) { message.error(e.response?.data?.detail || '创建失败') }
  })
}

function editUser(u: any) {
  openDlg(`编辑用户 · ${u.username}`, [
    { key: 'display_name', label: '显示名' },
    { key: 'role', label: '角色', type: 'select', required: true, options: roleOptions },
    {
      key: 'room_ids', label: '授权机房', type: 'select', options: roomOptions.value,
      hint: '作用域含所选机房的所有子机房',
    },
    { key: 'password', label: '重置密码', placeholder: '留空则不修改' },
    {
      key: 'is_active', label: '账号状态', type: 'select', default: 'true',
      options: [{ label: '启用', value: 'true' }, { label: '禁用', value: 'false' }],
    },
  ], {
    display_name: u.display_name, role: u.role, room_ids: u.room_ids,
    is_active: String(u.is_active), password: '',
  }, async (v) => {
    try {
      await api.put(`/auth/users/${u.id}`, {
        display_name: v.display_name || '',
        role: v.role,
        room_ids: v.role === 'core_admin' ? [] : (v.room_ids || []),
        password: v.password || undefined,
        is_active: v.is_active === 'true',
      })
      message.success('已保存')
      dlg.value.show = false
      await load()
    } catch (e: any) { message.error(e.response?.data?.detail || '保存失败') }
  })
}

function removeUser(u: any) {
  dialog.warning({
    title: '删除用户', content: `确认删除「${u.username}」？`,
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/auth/users/${u.id}`)
        message.success('已删除')
        await load()
      } catch (e: any) { message.error(e.response?.data?.detail || '删除失败') }
    },
  })
}

const columns = computed<DataTableColumns<any>>(() => [
  { title: '用户名', key: 'username', width: 140, render: (r) => h('span', { class: 'mono' }, r.username) },
  { title: '显示名', key: 'display_name', width: 140, render: (r) => r.display_name || h('span', { class: 'dim' }, '—') },
  {
    title: '角色', key: 'role', width: 170,
    render: (r) => h(NTag, {
      size: 'small', bordered: false,
      type: r.role === 'core_admin' ? 'primary' : 'warning',
    }, { default: () => (r.role === 'core_admin' ? '核心机房管理员' : '前端机房管理员') }),
  },
  {
    title: '授权机房', key: 'room_ids', minWidth: 280,
    render: (r) => {
      if (r.role === 'core_admin') return h('span', { class: 'dim' }, '全部机房')
      if (!r.room_ids?.length) return h('span', { class: 'dim' }, '未授权（只读）')
      return h('span', {}, r.room_ids.map((id: number) => roomPath(store.rooms as any, id)).join('；'))
    },
  },
  {
    title: '状态', key: 'is_active', width: 90,
    render: (r) => h(NTag, { size: 'small', bordered: false, type: r.is_active ? 'success' : 'default' },
      { default: () => (r.is_active ? '启用' : '禁用') }),
  },
  {
    title: '操作', key: 'act', width: 150,
    render: (r) => h('div', { class: 'row' }, [
      h(NButton, { size: 'tiny', quaternary: true, type: 'primary', onClick: () => editUser(r) },
        { default: () => '编辑' }),
      h(NButton, { size: 'tiny', quaternary: true, type: 'error', onClick: () => removeUser(r) },
        { default: () => '删除' }),
    ]),
  },
])

onMounted(async () => {
  if (!store.rooms.length) await store.loadBase()
  await load()
})
</script>

<template>
  <div class="sys">
    <section class="panel">
      <div class="panel-head">
        <Icon name="users" :size="14" />
        <span class="grow">用户与权限</span>
        <span class="dim">{{ users.length }} 个账号</span>
        <n-button size="small" type="primary" secondary @click="newUser">
          <template #icon><Icon name="plus" :size="12" /></template>新建用户
        </n-button>
      </div>
      <div class="panel-body no-pad">
        <n-data-table :columns="columns" :data="users" :loading="loading" size="small"
                      :bordered="false" :row-key="(r: any) => r.id" />
      </div>
    </section>

    <section class="panel tip-panel">
      <div class="panel-head"><Icon name="shield" :size="14" /><span class="grow">权限模型说明</span></div>
      <div class="panel-body">
        <ul class="rules">
          <li><b>核心机房管理员</b>：可查看并修改全部机房、机柜、设备、ODF、跳纤与链路，可管理用户。</li>
          <li><b>前端机房管理员</b>：可<b>查看全部</b>资源；写操作仅限被授权机房<b>及其所有子机房</b>。</li>
          <li>跨机房跳纤/盘间连接/纤芯熔接仅核心管理员可建立（避免写入他人机房端口状态）。</li>
          <li>所有写接口在服务端统一校验资源所属机房，不依赖前端隐藏按钮。</li>
        </ul>
      </div>
    </section>

    <DialogForm v-model:show="dlg.show" :title="dlg.title" :fields="dlg.fields"
                :initial="dlg.initial" @submit="dlg.submit" />
  </div>
</template>

<style scoped>
.sys { display: flex; flex-direction: column; gap: 14px; }
.panel-body.no-pad { padding: 0; }
.tip-panel { max-width: 100%; }
.rules { margin: 0; padding-left: 18px; line-height: 2; color: var(--text-2); font-size: 12.5px; }
.rules b { color: var(--text-1); }
</style>
