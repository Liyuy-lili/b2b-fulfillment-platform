<template>
  <ContentWrap title="文件任务">
    <section class="job-surface" aria-label="文件任务工作台">
      <p class="help"
        >导入只创建未审核的销售草稿。取消会保留已成功行；导出反映生成期间的数据，下载时重新检查权限。</p
      >
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-tabs v-model="tab">
        <el-tab-pane label="任务记录" name="list">
          <div class="toolbar">
            <label for="job-status">任务状态</label
            ><el-select
              id="job-status"
              v-model="status"
              clearable
              placeholder="全部状态"
              class="status-select"
              @change="filter"
              ><el-option v-for="(name, code) in states" :key="code" :value="code" :label="name"
            /></el-select>
            <el-button :loading="listLoading" :disabled="!!working" @click="loadList()"
              >刷新任务</el-button
            ><el-checkbox v-model="autoRefresh">自动刷新进行中的任务</el-checkbox>
          </div>
          <el-alert
            v-if="listError"
            title="任务列表加载失败，请刷新重试。"
            type="error"
            :closable="false"
          />
          <el-table
            v-else
            v-loading="listLoading"
            :data="jobs"
            empty-text="暂无文件任务。可从导入草稿或创建导出开始。"
            class="facts-table"
          >
            <el-table-column prop="id" label="任务编号" width="100" /><el-table-column
              label="内容"
              min-width="150"
              ><template #default="{ row }">{{ datasets[row.dataset] }}</template></el-table-column
            >
            <el-table-column label="状态" min-width="145"
              ><template #default="{ row }">{{
                states[row.status] || row.status
              }}</template></el-table-column
            >
            <el-table-column label="成功 / 失败 / 待处理" min-width="175"
              ><template #default="{ row }"
                >{{ row.successRows }} / {{ row.failedRows }} / {{ row.pendingRows }}</template
              ></el-table-column
            >
            <el-table-column label="提交时间" min-width="190"
              ><template #default="{ row }">{{
                displayTime(row.createdAt)
              }}</template></el-table-column
            >
            <el-table-column label="操作" width="100" fixed="right"
              ><template #default="{ row }"
                ><el-button link type="primary" :disabled="!!working" @click="open(row.id)"
                  >查看任务</el-button
                ></template
              ></el-table-column
            >
          </el-table>
          <div class="pagination-wrap" tabindex="0" aria-label="任务分页"
            ><Pagination v-model:page="page" :limit="10" :total="total" @pagination="loadList()"
          /></div>
        </el-tab-pane>
        <el-tab-pane v-if="canImport" label="导入草稿" name="import">
          <p class="help"
            >使用 UTF-8 CSV，每条数据一张单商品草稿；最多 10 MiB、10,000 行。customerCode
            填本租户客户内部编号，productCode 填商品条码。数量必须大于 0，最多六位小数。</p
          >
          <el-button :disabled="!!working" @click="downloadTemplate">下载 CSV 模板</el-button>
          <el-form label-position="top" class="form-width" @submit.prevent="submitImport">
            <el-form-item label="来源系统"
              ><el-input
                v-model="source"
                :maxlength="40"
                placeholder="例如：LOCAL_DEMO，同一来源下外部订单号不能重复创建"
                :disabled="!!working"
                @input="importKey = ''"
            /></el-form-item>
            <label for="import-file">CSV 文件</label
            ><input
              id="import-file"
              type="file"
              accept=".csv,text/csv"
              :disabled="!!working"
              class="file-input"
              @change="chooseFile"
            />
            <p v-if="file" class="help"
              >{{ file.name }} · {{ file.size.toLocaleString('zh-CN') }} 字节</p
            >
            <el-button
              type="primary"
              native-type="submit"
              :disabled="!!working || !file || !source.trim()"
              :loading="working === 'import'"
              >{{ importKey ? '重试本次导入提交' : '上传并提交导入' }}</el-button
            >
          </el-form>
        </el-tab-pane>
        <el-tab-pane v-if="canExport" label="创建导出" name="export">
          <p class="help"
            >导出范围在提交时固定，新增授权不会扩大旧任务；权限撤销后可能无法下载原结果。生成期间数据可能变化，文件附有生成时间窗口说明。</p
          >
          <el-form label-position="top" class="form-width" @submit.prevent="submitExport">
            <el-form-item label="导出内容"
              ><el-select v-model="dataset" :disabled="!!working" @change="exportKey = ''"
                ><el-option
                  label="库存 H / R / A"
                  value="STOCK"
                  :disabled="!canWarehouse" /><el-option
                  label="履约订单（销售视图）"
                  value="ORDER"
                  :disabled="!canOrders" /><el-option
                  label="仓库发货记录"
                  value="SHIPMENT"
                  :disabled="!canWarehouse" /></el-select
            ></el-form-item>
            <el-form-item v-if="dataset !== 'ORDER'" label="仓库范围"
              ><el-select
                v-model="exportWarehouses"
                multiple
                filterable
                :multiple-limit="128"
                placeholder="不选则使用当前全部已授权仓库"
                :disabled="!!working"
                @change="exportKey = ''"
                ><el-option
                  v-for="w in warehouses"
                  :key="w.id"
                  :label="w.name"
                  :value="w.id" /></el-select
            ></el-form-item>
            <el-alert
              v-if="scopeError && dataset !== 'ORDER'"
              title="无法读取仓库范围，请刷新页面重试。"
              type="error"
              :closable="false"
            />
            <el-button
              type="primary"
              native-type="submit"
              :loading="working === 'export'"
              :disabled="!!working || (dataset !== 'ORDER' && (scopeError || !warehouses.length))"
              >{{ exportKey ? '重试本次导出提交' : '提交 Excel 导出' }}</el-button
            >
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </section>
  </ContentWrap>
  <el-drawer
    v-model="detailOpen"
    title="文件任务详情"
    size="min(1080px, 100vw)"
    :before-close="closeDetail"
  >
    <div class="job-surface job-detail" v-loading="detailLoading">
      <el-alert
        v-if="detailError"
        title="任务详情加载失败，请关闭后重新查看。"
        type="error"
        :closable="false"
      />
      <template v-else-if="detail">
        <div class="toolbar"
          ><h3>任务 {{ detail.id }} · {{ datasets[detail.dataset] }}</h3
          ><el-button :disabled="!!working" @click="loadDetail()">刷新任务详情</el-button></div
        >
        <el-descriptions :column="width < 640 ? 1 : 2" border>
          <el-descriptions-item label="状态">{{ states[detail.status] }}</el-descriptions-item
          ><el-descriptions-item label="提交人编号">{{ detail.actorId }}</el-descriptions-item>
          <el-descriptions-item label="已读取 / 成功 / 失败 / 待处理"
            >{{ detail.totalRows }} / {{ detail.successRows }} / {{ detail.failedRows }} /
            {{ detail.pendingRows }}</el-descriptions-item
          >
          <el-descriptions-item label="文件准备">{{
            detail.prepared ? '已完成格式准备' : '尚未完成格式准备'
          }}</el-descriptions-item>
          <el-descriptions-item label="当前轮 / 累计处理尝试"
            >{{ detail.attempts }} / {{ detail.totalAttempts }}</el-descriptions-item
          ><el-descriptions-item label="任务级错误">{{
            jobError(detail.lastError)
          }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{
            displayTime(detail.createdAt)
          }}</el-descriptions-item
          ><el-descriptions-item label="完成时间">{{
            displayTime(detail.completedAt)
          }}</el-descriptions-item>
        </el-descriptions>
        <div class="toolbar"
          ><el-button
            v-if="detail.hasInput && canImport"
            :disabled="!!working"
            @click="downloadFile('INPUT')"
            >下载原始 CSV</el-button
          ><el-button
            v-if="detail.hasResult"
            type="primary"
            :disabled="!!working"
            @click="downloadFile('RESULT')"
            >下载 Excel 结果</el-button
          ><el-button
            v-if="detail.hasErrors && canImport"
            :disabled="!!working"
            @click="downloadFile('ERROR')"
            >下载错误明细 CSV</el-button
          ></div
        >
        <p class="help"
          >取消保留已经提交的成功行。重试保留成功行，只处理失败或待处理行；若需改文件，请修正后新建任务，同一外部订单仍会去重。</p
        >
        <el-alert v-if="controlError" :title="controlError" type="error" :closable="false" />
        <el-form
          v-if="showCancel || showRetry"
          label-position="top"
          class="form-width"
          @submit.prevent
        >
          <el-form-item label="任务操作原因"
            ><el-input
              v-model="controlReason"
              :maxlength="256"
              placeholder="说明取消原因，或故障修复后的重试目的"
              :disabled="!!working"
              @input="controlKey = ''"
          /></el-form-item>
          <div class="toolbar"
            ><el-button
              v-if="showRetry"
              v-hasPermi="['fulfillment:job:retry']"
              type="primary"
              :disabled="!!working || !controlReason.trim()"
              @click="control('retry')"
              >{{
                controlKey && controlIntent === 'retry' ? '重试本次恢复请求' : '重试失败与未处理行'
              }}</el-button
            ><el-button
              v-if="showCancel"
              v-hasPermi="['fulfillment:job:cancel']"
              :disabled="!!working || !controlReason.trim()"
              @click="control('cancel')"
              >{{
                controlKey && controlIntent === 'cancel' ? '重试本次取消请求' : '请求取消任务'
              }}</el-button
            ></div
          >
        </el-form>
        <details
          ><summary>查看提交时固定的数据范围</summary><pre>{{ detail.scopeJson }}</pre>
        </details>
        <section v-if="detail.type === 'IMPORT'" aria-label="导入逐行结果"
          ><h3>逐行结果</h3
          ><el-alert
            v-if="rowError"
            title="行结果无法读取，请检查当前权限后刷新。"
            type="error"
            :closable="false" /><el-table
            v-else
            :data="rowResults"
            empty-text="尚未准备数据行。"
            class="facts-table"
            ><el-table-column prop="rowNo" label="数据行号" width="100" /><el-table-column
              prop="externalNo"
              label="外部订单号"
              min-width="190" /><el-table-column label="状态" width="100"
              ><template #default="{ row }">{{ rowStates[row.status] }}</template></el-table-column
            ><el-table-column
              prop="erpOrderId"
              label="ERP草稿编号"
              min-width="140" /><el-table-column label="处理结果" min-width="145"
              ><template #default="{ row }">{{
                outcomes[row.outcome] || row.outcome || '—'
              }}</template></el-table-column
            ><el-table-column prop="errorCode" label="错误码" min-width="250" /></el-table
          ><div class="pagination-wrap" tabindex="0" aria-label="行结果分页"
            ><Pagination
              v-model:page="rowPage"
              :limit="10"
              :total="rowTotal"
              @pagination="loadDetail()" /></div
        ></section>
        <h3>操作与处理记录</h3
        ><el-alert
          v-if="auditError"
          title="处理记录加载失败，请刷新重试。"
          type="error"
          :closable="false"
        /><el-table v-else :data="audits" empty-text="暂无记录。" class="facts-table"
          ><el-table-column prop="operation" label="动作" min-width="180" /><el-table-column
            prop="reason"
            label="原因"
            min-width="210"
          /><el-table-column prop="actorId" label="操作者" width="110" /><el-table-column
            label="时间"
            min-width="190"
            ><template #default="{ row }">{{
              displayTime(row.createdAt)
            }}</template></el-table-column
          ></el-table
        ><div class="pagination-wrap" tabindex="0" aria-label="处理记录分页"
          ><Pagination
            v-model:page="auditPage"
            :limit="10"
            :total="auditTotal"
            @pagination="loadDetail()"
        /></div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import {
  FileJobApi,
  WarehouseApi,
  savePrivateBlob,
  type FileJob,
  type JobRow,
  type JobAudit,
  type Dataset,
  type WarehouseScope
} from '@/api/erp/fulfillment/jobs'
import { checkPermi } from '@/utils/permission'
import { useWindowSize } from '@vueuse/core'
import { ElMessage } from 'element-plus'
defineOptions({ name: 'ErpFulfillmentJobs' })
const { width } = useWindowSize()
const canImport = checkPermi(['fulfillment:job:import']),
  canExport = checkPermi(['fulfillment:job:export']),
  canWarehouse = checkPermi(['fulfillment:warehouse:query']),
  canOrders = checkPermi(['fulfillment:order:query'])
const states: Record<string, string> = {
  PENDING: '等待处理',
  RUNNING: '处理中',
  RETRY_WAIT: '等待恢复重试',
  SUCCEEDED: '已完成',
  PARTIAL_FAILED: '含失败行',
  FAILED: '处理失败',
  CANCEL_REQUESTED: '等待处理边界取消',
  CANCELLED: '已取消'
}
const datasets: Record<string, string> = {
    DRAFT: '销售草稿导入',
    STOCK: '库存导出',
    ORDER: '履约订单导出',
    SHIPMENT: '发货导出'
  },
  rowStates: Record<string, string> = { PENDING: '待处理', SUCCEEDED: '成功', FAILED: '失败' },
  outcomes: Record<string, string> = {
    CREATED: '新建草稿',
    EXISTING: '复用原草稿',
    REJECTED: '行校验未通过'
  }
const jobErrorNames: Record<string, string> = {
  IMPORT_ROW_LIMIT: '超过导入行数上限，请拆分文件后提交。',
  EXPORT_ROW_LIMIT: '超过导出行数上限，请缩小数据范围。',
  FILE_CHANGED_OR_MISSING: '原文件缺失或摘要不一致，请联系管理员核查。',
  JOB_InvalidCsv: 'CSV表头或引号格式错误，请使用UTF-8模板。',
  JOB_MalformedInputException: 'CSV编码错误，请保存为UTF-8后新建任务。',
  PERMISSION_OR_TENANT_REVOKED: '用户、租户或数据授权已失效。',
  ACTOR_DISABLED: '任务提交人已停用或删除。',
  FILE_SIZE_LIMIT: '结果文件超过大小上限，请缩小范围。',
  ATTEMPT_LIMIT: '恢复尝试已达到上限，请修复故障后人工重试。'
}
const jobError = (code: string | null) => (code ? jobErrorNames[code] || code : '无')
const active = new Set(['PENDING', 'RUNNING', 'RETRY_WAIT', 'CANCEL_REQUESTED'])
const tab = ref('list'),
  status = ref(''),
  page = ref(1),
  total = ref(0),
  jobs = ref<FileJob[]>([]),
  listLoading = ref(false),
  listError = ref(false),
  autoRefresh = ref(true),
  working = ref(''),
  error = ref('')
const file = ref<File>(),
  source = ref('LOCAL_DEMO'),
  fileId = ref(''),
  importKey = ref(''),
  exportKey = ref(''),
  dataset = ref<Dataset>(canWarehouse ? 'STOCK' : 'ORDER'),
  exportWarehouses = ref<string[]>([]),
  warehouses = ref<WarehouseScope[]>([]),
  scopeError = ref(false)
const detailOpen = ref(false),
  detail = ref<FileJob>(),
  selectedId = ref(''),
  detailLoading = ref(false),
  detailError = ref(false),
  rowResults = ref<JobRow[]>([]),
  rowPage = ref(1),
  rowTotal = ref(0),
  rowError = ref(false),
  audits = ref<JobAudit[]>([]),
  auditPage = ref(1),
  auditTotal = ref(0),
  auditError = ref(false),
  controlReason = ref(''),
  controlKey = ref(''),
  controlIntent = ref<'retry' | 'cancel'>('retry'),
  controlError = ref('')
const showRetry = computed(
  () =>
    !!detail.value &&
    (['FAILED', 'PARTIAL_FAILED'].includes(detail.value.status) ||
      (!!controlKey.value && controlIntent.value === 'retry'))
)
const showCancel = computed(
  () =>
    !!detail.value &&
    (active.has(detail.value.status) || (!!controlKey.value && controlIntent.value === 'cancel'))
)
let listRequest = 0,
  detailRequest = 0,
  fetching = false,
  detailFetching = false,
  disposed = false,
  timer: ReturnType<typeof setInterval> | undefined
const displayTime = (value?: string | null) =>
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
  fileId.value = ''
  importKey.value = ''
  error.value = ''
}
function filter() {
  page.value = 1
  loadList()
}
async function loadList(silent = false) {
  if (fetching) return
  fetching = true
  const token = ++listRequest
  if (!silent) listLoading.value = true
  try {
    const result = await FileJobApi.page(page.value, status.value || undefined)
    if (token !== listRequest) return
    jobs.value = result.list
    total.value = result.total
    listError.value = false
  } catch {
    if (token === listRequest) listError.value = true
  } finally {
    if (token === listRequest) {
      listLoading.value = false
      fetching = false
    }
  }
}
async function open(id: string) {
  ++detailRequest
  detailFetching = false
  selectedId.value = id
  rowPage.value = auditPage.value = 1
  controlKey.value = controlReason.value = controlError.value = ''
  detail.value = undefined
  detailOpen.value = true
  await loadDetail()
}
async function loadDetail(silent = false) {
  if (!detailOpen.value || detailFetching) return
  detailFetching = true
  const token = ++detailRequest,
    id = selectedId.value
  if (!silent) detailLoading.value = true
  try {
    const current = await FileJobApi.get(id)
    if (token !== detailRequest || selectedId.value !== id) return
    detail.value = current
    detailError.value = false
    const [rowResult, auditResult] = await Promise.allSettled([
      current.type === 'IMPORT'
        ? FileJobApi.rows(id, rowPage.value)
        : Promise.resolve({ list: [] as JobRow[], total: 0 }),
      FileJobApi.audits(id, auditPage.value)
    ])
    if (token !== detailRequest || selectedId.value !== id) return
    rowError.value = rowResult.status === 'rejected'
    auditError.value = auditResult.status === 'rejected'
    if (rowResult.status === 'fulfilled') {
      rowResults.value = rowResult.value.list
      rowTotal.value = rowResult.value.total
    }
    if (auditResult.status === 'fulfilled') {
      audits.value = auditResult.value.list
      auditTotal.value = auditResult.value.total
    }
  } catch {
    if (token === detailRequest) detailError.value = true
  } finally {
    if (token === detailRequest) {
      detailFetching = false
      detailLoading.value = false
    }
  }
}
async function submitImport() {
  if (working.value || !file.value) return
  if (
    !/^[A-Za-z0-9._-]{1,40}$/.test(source.value) ||
    !file.value.name.toLowerCase().endsWith('.csv') ||
    file.value.size > 10485760 ||
    !file.value.size
  ) {
    error.value = '请选择不超过10 MiB的CSV文件；来源系统只允许字母、数字、点、下划线和短横线。'
    return
  }
  working.value = 'import'
  error.value = ''
  importKey.value ||= crypto.randomUUID()
  try {
    fileId.value ||= (await FileJobApi.upload(file.value)).fileId
    const result = await FileJobApi.import(
      { fileId: fileId.value, sourceSystem: source.value },
      importKey.value
    )
    importKey.value = ''
    ElMessage.success('导入任务已提交：' + result.jobId)
    tab.value = 'list'
    await loadList()
    await open(result.jobId)
  } catch {
    error.value = '本次导入提交未确认完成，请检查错误提示后用相同内容重试。'
  } finally {
    working.value = ''
  }
}
async function submitExport() {
  if (working.value) return
  working.value = 'export'
  error.value = ''
  exportKey.value ||= crypto.randomUUID()
  try {
    const result = await FileJobApi.export(
      {
        dataset: dataset.value,
        warehouseIds: dataset.value === 'ORDER' ? [] : exportWarehouses.value
      },
      exportKey.value
    )
    exportKey.value = ''
    ElMessage.success('导出任务已提交：' + result.jobId)
    tab.value = 'list'
    await loadList()
    await open(result.jobId)
  } catch {
    error.value = '本次导出提交未确认完成，请检查数据范围后重试原请求。'
  } finally {
    working.value = ''
  }
}
async function control(action: 'retry' | 'cancel') {
  if (working.value || !detail.value || !controlReason.value.trim()) return
  working.value = action
  controlError.value = ''
  if (controlIntent.value !== action) controlKey.value = ''
  controlIntent.value = action
  controlKey.value ||= crypto.randomUUID()
  try {
    await FileJobApi.control(detail.value.id, action, controlReason.value.trim(), controlKey.value)
    controlKey.value = controlReason.value = ''
    auditPage.value = 1
    ElMessage.success(action === 'retry' ? '恢复请求已保存。' : '取消请求已保存。')
    await loadDetail()
    await loadList()
  } catch {
    controlError.value = '本次操作未确认完成，请检查当前权限和状态；可重试本次请求。'
  } finally {
    working.value = ''
  }
}
async function downloadFile(kind: 'INPUT' | 'RESULT' | 'ERROR') {
  if (working.value || !detail.value) return
  working.value = 'download'
  controlError.value = ''
  try {
    await savePrivateBlob(
      await FileJobApi.download(detail.value.id, kind),
      'fulfillment-' +
        detail.value.id +
        '-' +
        kind.toLowerCase() +
        (kind === 'RESULT' ? '.xlsx' : '.csv')
    )
    await loadDetail()
  } catch {
    controlError.value = '文件下载失败，请刷新任务，并检查当前功能和仓库授权。'
  } finally {
    working.value = ''
  }
}
async function downloadTemplate() {
  try {
    await savePrivateBlob(await FileJobApi.template(), 'fulfillment-import-v1.csv')
  } catch {
    error.value = '模板下载失败，请检查导入权限。'
  }
}
function closeDetail(done: () => void) {
  if (working.value) return
  ++detailRequest
  detailFetching = false
  detailLoading.value = false
  done()
}
onMounted(async () => {
  loadList()
  if (canWarehouse)
    try {
      warehouses.value = await WarehouseApi.scope()
    } catch {
      scopeError.value = true
    }
  if (disposed) return
  timer = setInterval(() => {
    if (!autoRefresh.value || working.value || document.visibilityState !== 'visible') return
    if (jobs.value.some((j) => active.has(j.status))) loadList(true)
    if (detailOpen.value && detail.value && active.has(detail.value.status)) loadDetail(true)
  }, 3000)
})
onBeforeUnmount(() => {
  disposed = true
  ++listRequest
  ++detailRequest
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.job-surface {
  --el-color-primary: #2d6fb3;
  --el-text-color-placeholder: #606266;

  min-width: 0;
}

.help {
  overflow-wrap: anywhere;
  max-width: 75ch;
  margin: 12px 0 24px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 16px 0;
}

.status-select {
  width: 220px;
}

.form-width {
  max-width: 640px;
  margin: 24px 0;
}

.form-width :deep(.el-select) {
  width: 100%;
}

.file-input {
  display: block;
  width: 100%;
  margin: 8px 0 24px;
  font: inherit;
  box-sizing: border-box;
}

.facts-table {
  font-variant-numeric: tabular-nums;
}

.job-surface h3 {
  margin: 28px 0 12px;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.job-surface pre {
  max-height: 200px;
  overflow: auto;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.job-surface summary {
  margin: 20px 0;
  cursor: pointer;
}

.pagination-wrap {
  overflow-x: auto;
  clear: both;
}

.pagination-wrap :deep(.el-pagination) {
  float: none;
  justify-content: flex-end;
  width: max-content;
  min-width: 100%;
  margin: 16px 0;
}

@media (width <= 640px) {
  .job-surface :deep(.el-button) {
    min-height: 44px;
  }
}
</style>
