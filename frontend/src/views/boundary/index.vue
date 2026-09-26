<template>
  <section class="page" data-module="boundary">
    <header class="page-head">
      <div>
        <h2>分包检测管理</h2>
        <p class="page-desc">送样、回样、验收三段数据分开存放，进度由三段记录统一推导，列表、详情与验收弹窗看到的口径一致。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记分包记录</button>
        <button class="btn" type="button" @click="openBatch">批量补录回样</button>
        <button class="btn" type="button" @click="exportRows">导出分包检测清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>分包编号</span>
        <input v-model="filters.keyword" placeholder="按分包编号检索" />
      </label>
      <label class="filter-item">
        <span>分包状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button v-if="row['分包状态'] === '待送样'" class="link" type="button" @click="quickDispatch(row)">送样分包</button>
            <button v-if="row['分包状态'] === '分包中'" class="link" type="button" @click="openReturn(row)">回样登记</button>
            <button v-if="row['分包状态'] === '已回样'" class="link" type="button" @click="openAccept(row)">验收</button>
            <span v-if="row['分包状态'] === '已验收'" class="muted-text">已验收归档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无分包检测数据，可先登记分包记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条分包检测记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记分包记录 -->
    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal-card">
        <h3>登记分包记录</h3>
        <label v-for="field in createFields" :key="field.name" class="form-item">
          <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
          <input v-model="createForm[field.name]" :placeholder="field.required ? `必填，请填写${field.label}` : `选填，请填写${field.label}`" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitCreate">提交登记</button>
          <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
        </div>
      </div>
    </div>

    <!-- 分包记录详情 -->
    <div v-if="detailEntry" class="modal-mask" @click.self="detailEntry = null">
      <div class="modal-card">
        <h3>分包记录详情 · {{ detailEntry['分包编号'] }}</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detailEntry[field] ?? '—' }}</dd>
          </template>
        </dl>
        <div class="stage-row">
          <div class="stage-card" :class="{ done: stageDone('送样') }">
            <strong>送样段</strong>
            <span>送样日期：{{ detailEntry['送样日期'] ?? '未送样' }}</span>
          </div>
          <div class="stage-card" :class="{ done: stageDone('回样') }">
            <strong>回样段</strong>
            <span>回样日期：{{ detailEntry['回样日期'] ?? '未回样' }}</span>
          </div>
          <div class="stage-card" :class="{ done: stageDone('验收') }">
            <strong>验收段</strong>
            <span>验收日期：{{ detailEntry['验收日期'] ?? '未验收' }}</span>
            <span v-if="detailEntry['验收结论']">验收结论：{{ detailEntry['验收结论'] }}</span>
          </div>
        </div>
        <p class="muted-text">当前进度：{{ detailEntry['分包状态'] }}（与列表页、验收弹窗一致）</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="detailEntry = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 回样登记 -->
    <div v-if="returnTarget" class="modal-mask" @click.self="returnTarget = null">
      <div class="modal-card">
        <h3>回样登记 · {{ returnTarget['分包编号'] }}</h3>
        <p class="muted-text">分包方：{{ returnTarget['分包方名称'] }} · 送样日期：{{ returnTarget['送样日期'] ?? '—' }}</p>
        <label class="form-item">
          <span>回样日期<em class="required-mark">*</em></span>
          <input v-model="returnDate" type="date" :min="returnTarget['送样日期'] ?? undefined" />
        </label>
        <p v-if="returnError" class="error-text">{{ returnError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitReturn">确认回样</button>
          <button class="btn ghost" type="button" @click="returnTarget = null">取消</button>
        </div>
      </div>
    </div>

    <!-- 验收弹窗 -->
    <div v-if="acceptTarget" class="modal-mask" @click.self="acceptTarget = null">
      <div class="modal-card">
        <h3>验收确认 · {{ acceptTarget['分包编号'] }}</h3>
        <div class="stage-row">
          <div class="stage-card done">
            <strong>送样段</strong>
            <span>送样日期：{{ acceptTarget['送样日期'] ?? '—' }}</span>
          </div>
          <div class="stage-card done">
            <strong>回样段</strong>
            <span>回样日期：{{ acceptTarget['回样日期'] ?? '—' }}</span>
          </div>
          <div class="stage-card">
            <strong>验收段</strong>
            <span>当前进度：{{ acceptTarget['分包状态'] }}</span>
          </div>
        </div>
        <label class="form-item">
          <span>验收日期</span>
          <input v-model="acceptDate" type="date" />
        </label>
        <label class="form-item">
          <span>验收结论</span>
          <select v-model="acceptVerdict">
            <option value="合格">合格</option>
            <option value="不合格">不合格</option>
          </select>
        </label>
        <p v-if="acceptError" class="error-text">{{ acceptError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitAccept">确认验收完成</button>
          <button class="btn ghost" type="button" @click="acceptTarget = null">取消</button>
        </div>
      </div>
    </div>

    <!-- 批量补录回样 -->
    <div v-if="batchVisible" class="modal-mask" @click.self="batchVisible = false">
      <div class="modal-card wide">
        <h3>批量补录回样</h3>
        <p class="muted-text">每行按分包编号独立落回样日期，互不影响；被阻断的行会列出原因，可只重试这一行。</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>分包编号</th>
              <th>回样日期</th>
              <th>处理结果</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in batchRows" :key="index">
              <td><input v-model="item.分包编号" placeholder="如 BOUN-0002" :disabled="item.state === 'ok'" /></td>
              <td><input v-model="item.回样日期" type="date" :disabled="item.state === 'ok'" /></td>
              <td>
                <span v-if="item.state === 'ok'" class="ok-text">{{ item.message }}</span>
                <span v-else-if="item.state === 'fail'" class="error-text">{{ item.message }}</span>
                <span v-else class="muted-text">待提交</span>
              </td>
              <td>
                <button v-if="item.state === 'fail'" class="link" type="button" :disabled="item.retrying" @click="retryBatchRow(item)">
                  {{ item.retrying ? '重试中…' : '仅重试本条' }}
                </button>
                <button v-if="item.state === 'idle' && batchRows.length > 1" class="link" type="button" @click="batchRows.splice(index, 1)">移除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="batchMessage" :class="batchOk ? 'ok-text' : 'error-text'">{{ batchMessage }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="batchRows.push({ 分包编号: '', 回样日期: '', state: 'idle', message: '', retrying: false })">加一行</button>
          <button class="btn primary" type="button" :disabled="batchSubmitting" @click="submitBatch">
            {{ batchSubmitting ? '提交中…' : '提交补录' }}
          </button>
          <button class="btn ghost" type="button" @click="closeBatch">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { id: number }

interface BatchRow {
  分包编号: string
  回样日期: string
  state: 'idle' | 'ok' | 'fail'
  message: string
  retrying: boolean
}

interface BatchResult {
  分包编号: string
  ok: boolean
  message: string
}

const ENDPOINT = '/api/boundary'
const columns = ['分包编号', '分包原因', '分包方名称', '资质编号', '分包项目', '送样日期', '回样日期', '分包状态']
const statuses = ['待送样', '分包中', '已回样', '已验收']
const detailFields = ['分包编号', '分包原因', '分包方名称', '资质编号', '分包项目']
const createFields = [
  { name: '分包编号', label: '分包编号', required: true },
  { name: '分包原因', label: '分包原因', required: true },
  { name: '分包方名称', label: '分包方名称', required: true },
  { name: '资质编号', label: '资质编号', required: false },
  { name: '分包项目', label: '分包项目', required: true },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref(statuses.map((status) => ({ label: status, value: 0 })))
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ keyword: '', status: '' })

const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')

const detailEntry = ref<Row | null>(null)

const returnTarget = ref<Row | null>(null)
const returnDate = ref('')
const returnError = ref('')

const acceptTarget = ref<Row | null>(null)
const acceptDate = ref('')
const acceptVerdict = ref('合格')
const acceptError = ref('')

const batchVisible = ref(false)
const batchRows = ref<BatchRow[]>([])
const batchMessage = ref('')
const batchOk = ref(false)
const batchSubmitting = ref(false)

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function stageDone(stage: '送样' | '回样' | '验收'): boolean {
  const entry = detailEntry.value
  if (!entry) return false
  if (stage === '送样') return Boolean(entry['送样日期'])
  if (stage === '回样') return Boolean(entry['回样日期'])
  return Boolean(entry['验收日期'])
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  createVisible.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const result = await postAction(`${ENDPOINT}`, createForm.value)
    if (!result.ok) {
      createError.value = result.message
      return
    }
    createVisible.value = false
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '分包记录登记失败'
  }
}

async function openDetail(row: Row) {
  // 详情重新拉一次单条记录，保证和列表、验收弹窗看到的是同一份三段数据
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('分包记录详情读取失败')
    detailEntry.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分包记录详情读取失败'
  }
}

async function quickDispatch(row: Row) {
  await runRowAction(row, { action: '送样分包', 送样日期: today() })
}

function openReturn(row: Row) {
  returnTarget.value = row
  returnDate.value = today()
  returnError.value = ''
}

async function submitReturn() {
  if (!returnTarget.value) return
  returnError.value = ''
  const result = await runRowAction(returnTarget.value, { action: '回样接收', 回样日期: returnDate.value })
  if (result) returnTarget.value = null
  else returnError.value = errorMessage.value
}

function openAccept(row: Row) {
  acceptTarget.value = row
  acceptDate.value = today()
  acceptVerdict.value = '合格'
  acceptError.value = ''
}

async function submitAccept() {
  if (!acceptTarget.value) return
  acceptError.value = ''
  const result = await runRowAction(acceptTarget.value, {
    action: '验收完成',
    验收日期: acceptDate.value,
    验收结论: acceptVerdict.value,
  })
  if (result) acceptTarget.value = null
  else acceptError.value = errorMessage.value
}

async function runRowAction(row: Row, values: Record<string, string>): Promise<boolean> {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const result = await postAction(`${ENDPOINT}/${row.id}/actions`, values)
    if (!result.ok) {
      errorMessage.value = result.message
      return false
    }
    noticeMessage.value = result.message
    await reload()
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分包检测操作失败'
    return false
  }
}

function openBatch() {
  batchRows.value = [
    { 分包编号: '', 回样日期: today(), state: 'idle', message: '', retrying: false },
    { 分包编号: '', 回样日期: today(), state: 'idle', message: '', retrying: false },
  ]
  batchMessage.value = ''
  batchOk.value = false
  batchVisible.value = true
}

function closeBatch() {
  batchVisible.value = false
  void reload()
}

async function submitBatch() {
  const pending = batchRows.value.filter((item) => item.state !== 'ok')
  if (!pending.length) {
    batchMessage.value = '没有待提交的行'
    batchOk.value = false
    return
  }
  batchSubmitting.value = true
  try {
    await postBatch(pending)
  } finally {
    batchSubmitting.value = false
  }
}

async function retryBatchRow(item: BatchRow) {
  // 只重试这一条：其他行的成功与失败状态都不受影响
  item.retrying = true
  try {
    await postBatch([item])
  } finally {
    item.retrying = false
  }
}

async function postBatch(targets: BatchRow[]) {
  batchMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/return-samples`, {
      method: 'POST',
      body: JSON.stringify({ items: targets.map(({ 分包编号, 回样日期 }) => ({ 分包编号, 回样日期 })) }),
    })
    if (!response.ok) throw new Error(`接口返回 ${response.status}，补录未生效`)
    const payload = (await response.json()) as { ok: boolean; message: string; results: BatchResult[] }
    for (const result of payload.results ?? []) {
      const target = targets.find((item) => item.分包编号.trim() === result.分包编号)
        ?? (result.分包编号 === '' ? targets.find((item) => !item.分包编号.trim()) : undefined)
      if (!target) continue
      target.state = result.ok ? 'ok' : 'fail'
      target.message = result.message
    }
    batchOk.value = payload.ok
    batchMessage.value = payload.message
    if (payload.ok) await reload()
  } catch (error) {
    batchOk.value = false
    batchMessage.value = error instanceof Error ? error.message : '批量补录回样失败'
  }
}

async function postAction(path: string, values: Record<string, unknown>): Promise<{ ok: boolean; message: string }> {
  const response = await request(path, { method: 'POST', body: JSON.stringify({ values }) })
  if (!response.ok) throw new Error(`接口返回 ${response.status}，操作未生效`)
  return (await response.json()) as { ok: boolean; message: string }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok) throw new Error('分包记录列表读取失败')
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (summaryResponse.ok) {
      const summary = (await summaryResponse.json()) as Record<string, number>
      stats.value = statuses.map((status) => ({ label: status, value: summary[status] ?? 0 }))
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分包检测列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  width: 460px;
  max-width: 92vw;
  max-height: 86vh;
  overflow: auto;
}
.modal-card.wide {
  width: 720px;
}
.modal-card h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.form-item {
  display: block;
  margin-bottom: 10px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item input,
.form-item select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.required-mark {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 14px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 6px 12px;
  margin: 0 0 12px;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.stage-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}
.stage-card {
  flex: 1;
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.stage-card.done {
  border-style: solid;
  border-color: #12b76a;
  color: #1f2937;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.notice-text {
  color: #067647;
}
.ok-text {
  color: #067647;
  font-size: 12px;
}
</style>
