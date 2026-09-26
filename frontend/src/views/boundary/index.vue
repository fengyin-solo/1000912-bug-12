<template>
  <section class="page" data-module="boundary">
    <header class="page-head">
      <div>
        <h2>分包检测管理</h2>
        <p class="page-desc">送样、回样、验收三段数据分开登记：回样日期只落在对应分包编号上，验收后回样记录锁定不可改。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记分包记录</button>
        <button class="btn" type="button" @click="toggleBatchMode">
          {{ batchMode ? '退出批量补录' : '批量补录回样' }}
        </button>
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
        <input v-model="keyword" placeholder="按分包编号检索" />
      </label>
      <label class="filter-item">
        <span>分包状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="batchMode" class="batch-bar">
      <label class="filter-item">
        <span>本次回样日期</span>
        <input v-model="batchDate" type="date" />
      </label>
      <label class="batch-pick">
        <input type="checkbox" :checked="allBatchSelected" @change="toggleSelectAll" />
        全选可登记记录
      </label>
      <button class="btn primary" type="button" :disabled="!batchSelections.length" @click="submitBatch">
        补录选中的 {{ batchSelections.length }} 条
      </button>
      <span class="batch-hint">仅「分包中 / 已回样」且分包项目不为空的记录可被补录；已验收的记录不参与。</span>
    </div>

    <div v-if="batchResults.length" class="batch-result">
      <p>补录结果：成功 {{ batchSuccessCount }} 条，被阻断 {{ batchFailCount }} 条，可只重试失败的记录。</p>
      <ul>
        <li v-for="item in batchResults" :key="String(item.id)" :class="{ blocked: !item.ok }">
          <span>{{ item.message }}</span>
          <button
            v-if="!item.ok"
            class="link"
            type="button"
            @click="retryBatchItem(item.id)"
          >
            只重试这一条
          </button>
        </li>
      </ul>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-if="batchMode" class="col-check">选择</th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-if="batchMode" class="col-check">
            <input
              type="checkbox"
              :checked="batchSelections.includes(Number(row.id))"
              :disabled="!canRegisterReturn(row)"
              @change="toggleSelect(Number(row.id))"
            />
          </td>
          <td v-for="column in columns" :key="column">
            <button v-if="column === '分包编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button
              v-if="canDispatch(row)"
              class="link"
              type="button"
              @click="openDispatch(row)"
            >
              送样分包
            </button>
            <button
              v-if="canRegisterReturn(row)"
              class="link"
              type="button"
              @click="openReturn(row)"
            >
              {{ row['分包状态'] === '已回样' ? '修改回样日期' : '回样登记' }}
            </button>
            <button v-if="canAccept(row)" class="link" type="button" @click="openAccept(row)">
              验收完成
            </button>
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <span v-if="!canDispatch(row) && !canRegisterReturn(row) && !canAccept(row)" class="muted-text">
              流程已完结
            </span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + (batchMode ? 2 : 1)" class="empty-state">
            暂无分包检测数据，可先登记分包记录
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条分包检测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记分包记录 -->
    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>登记分包记录</h3>
        <div v-for="field in createFields" :key="field" class="form-item">
          <label>{{ field }}<em>*</em></label>
          <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
        </div>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" @click="submitCreate">提交登记</button>
        </div>
      </div>
    </div>

    <!-- 送样分包 -->
    <div v-if="dispatchVisible" class="modal-mask" @click.self="closeDispatch">
      <div class="modal">
        <h3>送样分包 · {{ activeRow?.['分包编号'] }}</h3>
        <dl class="stage-readonly">
          <div><dt>分包方名称</dt><dd>{{ activeRow?.['分包方名称'] }}</dd></div>
          <div><dt>分包项目</dt><dd>{{ activeRow?.['分包项目'] }}</dd></div>
        </dl>
        <div class="form-item">
          <label>送样日期<em>*</em></label>
          <input v-model="dispatchDate" type="date" />
        </div>
        <p v-if="dispatchError" class="error-text">{{ dispatchError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDispatch">取消</button>
          <button class="btn primary" type="button" @click="submitDispatch">确认送样</button>
        </div>
      </div>
    </div>

    <!-- 回样登记：日期只写当前这条分包编号 -->
    <div v-if="returnVisible" class="modal-mask" @click.self="closeReturn">
      <div class="modal">
        <h3>回样登记 · {{ activeRow?.['分包编号'] }}</h3>
        <dl class="stage-readonly">
          <div><dt>分包方名称</dt><dd>{{ activeRow?.['分包方名称'] }}</dd></div>
          <div><dt>分包项目</dt><dd>{{ activeRow?.['分包项目'] }}</dd></div>
          <div><dt>送样日期</dt><dd>{{ activeRow?.['送样日期'] ?? '—' }}</dd></div>
        </dl>
        <div class="form-item">
          <label>回样日期<em>*</em></label>
          <input v-model="returnDate" type="date" />
        </div>
        <p v-if="returnError" class="error-text">{{ returnError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeReturn">取消</button>
          <button class="btn primary" type="button" @click="submitReturn">确认回样</button>
        </div>
      </div>
    </div>

    <!-- 验收弹窗：回样日期只读，验收只写验收日期 -->
    <div v-if="acceptVisible" class="modal-mask" @click.self="closeAccept">
      <div class="modal">
        <h3>验收完成 · {{ activeRow?.['分包编号'] }}</h3>
        <dl class="stage-readonly">
          <div><dt>分包方名称</dt><dd>{{ activeRow?.['分包方名称'] }}</dd></div>
          <div><dt>送样日期</dt><dd>{{ activeRow?.['送样日期'] ?? '—' }}</dd></div>
          <div><dt>回样日期</dt><dd>{{ activeRow?.['回样日期'] ?? '—' }}</dd></div>
        </dl>
        <div class="form-item">
          <label>验收日期<em>*</em></label>
          <input v-model="acceptDate" type="date" />
        </div>
        <p class="modal-tip">验收完成后回样日期将锁定，不允许再修改。</p>
        <p v-if="acceptError" class="error-text">{{ acceptError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeAccept">取消</button>
          <button class="btn primary" type="button" @click="submitAccept">确认验收</button>
        </div>
      </div>
    </div>

    <!-- 详情：与列表、验收弹窗同一进度口径 -->
    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal modal-wide">
        <h3>分包记录详情 · {{ detailRow?.['分包编号'] }}</h3>
        <table class="data-table detail-table">
          <tbody>
            <tr v-for="field in detailFields" :key="field">
              <th>{{ field }}</th>
              <td>{{ detailRow?.[field] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface BatchResultItem {
  id: number
  ok: boolean
  message: string
}

const ENDPOINT = '/api/boundary'
const columns = ['分包编号', '分包原因', '分包方名称', '资质编号', '分包项目', '送样日期', '回样日期', '验收日期', '分包状态']
const detailFields = columns
const createFields = ['分包编号', '分包原因', '分包方名称', '资质编号', '分包项目']
const statuses = ['待送样', '分包中', '已回样', '已验收']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const statsDefinition = [
  { label: '待送样分包', status: '待送样' },
  { label: '分包中记录', status: '分包中' },
  { label: '已回样记录', status: '已回样' },
  { label: '已验收分包', status: '已验收' },
]
const stats = computed(() =>
  statsDefinition.map((item) => ({
    label: item.label,
    value: rows.value.filter((row) => row['分包状态'] === item.status).length,
  })),
)

function today(): string {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

// ---------- 列表 ----------
function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  // 一次取回做统计卡片，分页口径与后端保持一致（上限 200）
  params.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('分包记录列表读取失败')
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分包记录列表读取失败'
  }
}

// ---------- 动作可用性：三处共用同一状态判断 ----------
function canDispatch(row: Row): boolean {
  return row['分包状态'] === '待送样'
}
function canRegisterReturn(row: Row): boolean {
  return row['分包状态'] === '分包中' || row['分包状态'] === '已回样'
}
function canAccept(row: Row): boolean {
  return row['分包状态'] === '已回样'
}

// ---------- 登记分包记录 ----------
const createVisible = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

function openCreate() {
  createForm.value = Object.fromEntries(createFields.map((field) => [field, '']))
  createError.value = ''
  createVisible.value = true
}
function closeCreate() {
  createVisible.value = false
}
async function submitCreate() {
  createError.value = ''
  const empty = createFields.filter((field) => !createForm.value[field]?.trim())
  if (empty.length) {
    createError.value = `${empty.join('、')}不能为空，请补全后再提交（分包编号尚未生成，登记成功后才会占用编号）`
    return
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      createError.value = payload.message || '分包记录登记失败'
      return
    }
    createVisible.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '分包记录登记失败'
  }
}

// ---------- 分段操作共用的当前行 ----------
const activeRow = ref<Row | null>(null)
const dispatchVisible = ref(false)
const returnVisible = ref(false)
const acceptVisible = ref(false)
const dispatchDate = ref('')
const returnDate = ref('')
const acceptDate = ref('')
const dispatchError = ref('')
const returnError = ref('')
const acceptError = ref('')

function openDispatch(row: Row) {
  activeRow.value = row
  dispatchDate.value = today()
  dispatchError.value = ''
  dispatchVisible.value = true
}
function closeDispatch() {
  dispatchVisible.value = false
  activeRow.value = null
}
async function submitDispatch() {
  if (!activeRow.value) return
  dispatchError.value = ''
  if (!dispatchDate.value) {
    dispatchError.value = '送样日期不能为空'
    return
  }
  const response = await request(`${ENDPOINT}/${activeRow.value.id}/dispatch`, {
    method: 'POST',
    body: JSON.stringify({ date: dispatchDate.value }),
  })
  const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
  if (!response.ok || payload?.ok === false) {
    dispatchError.value = payload?.message || '送样分包失败'
    return
  }
  dispatchVisible.value = false
  await reload()
}

function openReturn(row: Row) {
  activeRow.value = row
  returnDate.value = (row['回样日期'] as string) || today()
  returnError.value = ''
  returnVisible.value = true
}
function closeReturn() {
  returnVisible.value = false
  activeRow.value = null
}
async function submitReturn() {
  if (!activeRow.value) return
  returnError.value = ''
  if (!String(activeRow.value['分包项目'] ?? '').trim()) {
    returnError.value = `分包编号 ${activeRow.value['分包编号']} 的分包项目为空，不允许登记回样，请先补全分包项目`
    return
  }
  if (!returnDate.value) {
    returnError.value = '回样日期不能为空'
    return
  }
  const response = await request(`${ENDPOINT}/${activeRow.value.id}/return`, {
    method: 'POST',
    body: JSON.stringify({ id: Number(activeRow.value.id), 回样日期: returnDate.value }),
  })
  const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
  if (!response.ok || payload?.ok === false) {
    returnError.value = payload?.message || '回样登记失败'
    return
  }
  returnVisible.value = false
  await reload()
}

function openAccept(row: Row) {
  activeRow.value = row
  acceptDate.value = today()
  acceptError.value = ''
  acceptVisible.value = true
}
function closeAccept() {
  acceptVisible.value = false
  activeRow.value = null
}
async function submitAccept() {
  if (!activeRow.value) return
  acceptError.value = ''
  if (!acceptDate.value) {
    acceptError.value = '验收日期不能为空'
    return
  }
  const response = await request(`${ENDPOINT}/${activeRow.value.id}/accept`, {
    method: 'POST',
    body: JSON.stringify({ date: acceptDate.value }),
  })
  const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
  if (!response.ok || payload?.ok === false) {
    acceptError.value = payload?.message || '验收完成失败'
    return
  }
  acceptVisible.value = false
  await reload()
}

// ---------- 详情 ----------
const detailVisible = ref(false)
const detailRow = ref<Row | null>(null)

async function openDetail(row: Row) {
  detailRow.value = row
  detailVisible.value = true
  // 详情始终重新拉取单条最新数据，进度口径与列表一致
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (response.ok) {
      detailRow.value = (await response.json()) as Row
    }
  } catch {
    // 拉取失败时保留列表行数据展示
  }
}
function closeDetail() {
  detailVisible.value = false
  detailRow.value = null
}

// ---------- 批量补录回样：失败可单条重试 ----------
const batchMode = ref(false)
const batchDate = ref(today())
const batchSelections = ref<number[]>([])
const batchResults = ref<BatchResultItem[]>([])

const batchCandidates = computed(() => rows.value.filter((row) => canRegisterReturn(row)))
const allBatchSelected = computed(
  () =>
    batchCandidates.value.length > 0 &&
    batchCandidates.value.every((row) => batchSelections.value.includes(Number(row.id))),
)
const batchSuccessCount = computed(() => batchResults.value.filter((item) => item.ok).length)
const batchFailCount = computed(() => batchResults.value.filter((item) => !item.ok).length)

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  batchSelections.value = []
  batchResults.value = []
}
function toggleSelect(id: number) {
  if (batchSelections.value.includes(id)) {
    batchSelections.value = batchSelections.value.filter((item) => item !== id)
  } else {
    batchSelections.value = [...batchSelections.value, id]
  }
}
function toggleSelectAll() {
  if (allBatchSelected.value) {
    batchSelections.value = []
  } else {
    batchSelections.value = batchCandidates.value.map((row) => Number(row.id))
  }
}

async function postBatch(ids: number[]): Promise<BatchResultItem[]> {
  const response = await request(`${ENDPOINT}/returns/batch`, {
    method: 'POST',
    body: JSON.stringify({
      items: ids.map((id) => ({ id, 回样日期: batchDate.value })),
    }),
  })
  const payload = (await response.json()) as { results?: BatchResultItem[]; message?: string }
  if (!response.ok) {
    throw new Error(payload.message || '批量补录回样失败')
  }
  return payload.results ?? []
}

async function submitBatch() {
  errorMessage.value = ''
  // 提交前先做一次分包项目为空的阻断校验，并列出被阻断的分包编号
  const blocked = rows.value.filter(
    (row) =>
      batchSelections.value.includes(Number(row.id)) &&
      !String(row['分包项目'] ?? '').trim(),
  )
  if (blocked.length) {
    const codes = blocked.map((row) => String(row['分包编号'])).join('、')
    errorMessage.value = `分包项目为空，不允许提交回样登记；被阻断的分包编号：${codes}`
    return
  }
  if (!batchDate.value) {
    errorMessage.value = '回样日期不能为空，请先选择本次回样日期'
    return
  }
  try {
    batchResults.value = await postBatch(batchSelections.value)
    batchSelections.value = []
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量补录回样失败'
  }
}

async function retryBatchItem(id: number) {
  errorMessage.value = ''
  if (!batchDate.value) {
    errorMessage.value = '回样日期不能为空，请先选择本次回样日期'
    return
  }
  try {
    const results = await postBatch([id])
    batchResults.value = batchResults.value.map((item) =>
      item.id === id && results[0] ? results[0] : item,
    )
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '单条重试失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
}
.col-check {
  width: 40px;
  text-align: center;
}
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.batch-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.batch-pick {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.batch-hint {
  color: var(--muted);
  font-size: 12px;
}
.batch-result {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.batch-result ul {
  margin: 6px 0 0;
  padding-left: 18px;
}
.batch-result li.blocked {
  color: #b42318;
}
.batch-result li button {
  margin-left: 8px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  background: #fff;
  border-radius: 10px;
  width: 460px;
  max-width: calc(100vw - 32px);
  padding: 18px 20px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}
.modal-wide {
  width: 620px;
}
.modal h3 {
  margin: 0 0 14px;
  font-size: 16px;
}
.form-item {
  margin-bottom: 12px;
}
.form-item label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item em {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.form-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.stage-readonly {
  margin: 0 0 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.stage-readonly div {
  display: flex;
  font-size: 13px;
}
.stage-readonly dt {
  width: 96px;
  background: #f8fafc;
  color: var(--muted);
  padding: 6px 10px;
  margin: 0;
  border-bottom: 1px solid var(--border);
}
.stage-readonly dd {
  margin: 0;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  flex: 1;
}
.stage-readonly div:last-child dt,
.stage-readonly div:last-child dd {
  border-bottom: none;
}
.modal-tip {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 8px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}
.detail-table th {
  width: 120px;
  background: #f8fafc;
}
</style>
