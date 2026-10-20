<template>
  <ContentWrap title="库存与履约核对" class="reconcile-page">
    <p class="help"
      >核对本租户的库存、流水、预占和履约事实。这里只展示你发起的报告，发现差异后由人工排查。</p
    >
    <div class="toolbar">
      <el-button
        v-hasPermi="['fulfillment:reconcile:run']"
        type="primary"
        :loading="running"
        :disabled="running"
        @click="run"
      >
        {{ runKey ? '重试本次核对' : '执行新核对' }}
      </el-button>
      <el-button :disabled="running || loading" @click="load">刷新报告</el-button>
    </div>
    <el-alert v-if="runError" :title="runError" type="error" :closable="false" show-icon />
    <p class="help"
      >报告保留当次观察结果；再次核对会新建报告。超出扫描上限时会明确失败，不生成部分报告。</p
    >
    <el-alert
      v-if="listError"
      title="报告加载失败，请点击刷新报告重试。"
      type="error"
      :closable="false"
      show-icon
    />
    <el-table
      v-else
      v-loading="loading"
      :data="rows"
      empty-text="暂无报告。执行一次核对后，可以查看差异和关联记录。"
      class="facts-table"
    >
      <el-table-column prop="id" label="报告编号" width="100" />
      <el-table-column label="读取起始标记" min-width="195"
        ><template #default="{ row }">{{ displayTime(row.snapshotAt) }}</template></el-table-column
      >
      <el-table-column prop="ruleVersion" label="规则版本" min-width="130" />
      <el-table-column prop="scannedCount" label="读取记录" min-width="110" align="right" />
      <el-table-column label="核对结果" min-width="130"
        ><template #default="{ row }"
          ><span :class="{ 'difference-count': row.differenceCount > 0 }">{{
            row.differenceCount ? `${row.differenceCount} 项差异` : '未发现差异'
          }}</span></template
        ></el-table-column
      >
      <el-table-column label="操作" width="100" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="open(row.id)">查看报告</el-button></template
        ></el-table-column
      >
    </el-table>
    <div class="pagination-wrap" tabindex="0" aria-label="分页操作"
      ><Pagination
        v-model:page="query.pageNo"
        v-model:limit="query.pageSize"
        :total="total"
        @pagination="load"
    /></div>
  </ContentWrap>

  <el-drawer
    v-model="detailOpen"
    title="核对报告"
    size="min(1120px, 100vw)"
    class="reconcile-detail"
    :before-close="closeDetail"
  >
    <div v-loading="detailLoading" class="reconcile-detail-content">
      <el-alert
        v-if="detailError"
        title="报告详情加载失败，请关闭后重新打开。"
        type="error"
        :closable="false"
      />
      <template v-else-if="detail">
        <el-descriptions :column="width < 640 ? 1 : 2" border>
          <el-descriptions-item label="报告编号">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="规则版本">{{ detail.ruleVersion }}</el-descriptions-item>
          <el-descriptions-item label="范围">本租户全部库存与履约</el-descriptions-item>
          <el-descriptions-item label="差异数量">{{ detail.differenceCount }}</el-descriptions-item>
          <el-descriptions-item label="读取起始标记">{{
            displayTime(detail.snapshotAt)
          }}</el-descriptions-item>
          <el-descriptions-item label="报告生成时间">{{
            displayTime(detail.finishedAt)
          }}</el-descriptions-item>
        </el-descriptions>
        <p class="help"
          >时间是读取前的标记，不代表精确提交边界。报告中的各表来自同一次一致性快照，之后发生的变化请执行新核对。</p
        >
        <details class="table-counts"
          ><summary>查看各表读取行数（共 {{ detail.scannedCount }} 条）</summary
          ><dl
            ><template v-for="(count, table) in detail.tableCounts" :key="table"
              ><dt>{{ table }}</dt
              ><dd>{{ count }}</dd></template
            ></dl
          ></details
        >
        <h3>差异记录</h3>
        <div class="toolbar">
          <label for="reconcile-status">确认状态</label>
          <el-select
            id="reconcile-status"
            v-model="itemQuery.status"
            placeholder="全部状态"
            clearable
            :disabled="reviewing || itemLoading"
            class="status-select"
            @change="filterItems"
          >
            <el-option label="待确认" value="OPEN" /><el-option
              label="已确认"
              value="ACKNOWLEDGED"
            />
          </el-select>
          <el-button :disabled="reviewing || itemLoading" @click="loadItems">刷新差异</el-button>
        </div>
        <el-alert
          v-if="itemError"
          title="差异加载失败，请点击刷新差异重试。"
          type="error"
          :closable="false"
        />
        <el-table
          v-else
          v-loading="itemLoading"
          :data="items"
          empty-text="当前筛选下没有差异。确认只记录排查说明，不修改库存。"
          class="facts-table"
        >
          <el-table-column prop="ruleCode" label="核对规则" min-width="235" />
          <el-table-column label="定位对象" min-width="210"
            ><template #default="{ row }"
              >{{ row.objectType }} / {{ row.objectId
              }}<div v-if="row.productId || row.warehouseId"
                >商品 {{ row.productId || '—' }} · 仓库 {{ row.warehouseId || '—' }}</div
              ><div v-if="row.orderId">履约订单 {{ row.orderId }}</div></template
            ></el-table-column
          >
          <el-table-column prop="expectedValue" label="期望值" min-width="130" />
          <el-table-column prop="actualValue" label="实际值" min-width="130" />
          <el-table-column label="状态" width="100"
            ><template #default="{ row }">{{
              row.resolutionStatus === 'ACKNOWLEDGED' ? '已确认' : '待确认'
            }}</template></el-table-column
          >
          <el-table-column label="操作" width="100" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" :disabled="reviewing" @click="selectFinding(row)"
                >查看说明</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <div class="pagination-wrap" tabindex="0" aria-label="分页操作"
          ><Pagination
            v-model:page="itemQuery.pageNo"
            v-model:limit="itemQuery.pageSize"
            :total="itemTotal"
            @pagination="loadItems"
        /></div>
        <section v-if="selected" class="review-section" aria-label="差异确认与排查说明">
          <h3>差异 {{ selected.id }}：{{ selected.ruleCode }}</h3>
          <p>{{ selected.detail }}</p>
          <p class="help"
            >确认仅表示已查看并记录说明，不表示差异已修复。原报告会保留期望值与实际值。</p
          >
          <el-alert v-if="reviewError" :title="reviewError" type="error" :closable="false" />
          <el-form
            v-hasPermi="['fulfillment:reconcile:review']"
            label-position="top"
            @submit.prevent="review"
          >
            <el-form-item label="排查说明"
              ><el-input
                v-model="note"
                type="textarea"
                :rows="3"
                :maxlength="256"
                show-word-limit
                placeholder="记录核实结果、关联工单或下一步排查措施"
                :disabled="reviewing"
                @input="reviewKey = ''"
            /></el-form-item>
            <el-button
              type="primary"
              :loading="reviewing"
              :disabled="reviewing || !note.trim()"
              @click="review"
              >{{ reviewKey ? '重试记录说明' : '确认并记录说明' }}</el-button
            >
          </el-form>
          <h3>说明记录</h3>
          <el-alert
            v-if="trailError"
            title="说明记录加载失败，请重试。"
            type="error"
            :closable="false"
            ><el-button text @click="loadTrail">重新加载说明</el-button></el-alert
          >
          <el-table
            v-else
            v-loading="trailLoading"
            :data="trail"
            empty-text="尚未记录排查说明。"
            class="facts-table"
          >
            <el-table-column prop="note" label="说明" min-width="260" /><el-table-column
              prop="actorId"
              label="操作者编号"
              width="120"
            /><el-table-column label="记录时间" min-width="195"
              ><template #default="{ row }">{{
                displayTime(row.reviewedAt)
              }}</template></el-table-column
            >
          </el-table>
          <div class="pagination-wrap" tabindex="0" aria-label="分页操作"
            ><Pagination
              v-model:page="trailPage"
              :limit="10"
              :total="trailTotal"
              @pagination="loadTrail"
          /></div>
        </section>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import {
  ReconcileApi,
  type ReconcileRun,
  type ReconcileFinding,
  type ReconcileReview
} from '@/api/erp/reconciliation'
import { ElMessage } from 'element-plus'
import { useWindowSize } from '@vueuse/core'
defineOptions({ name: 'ErpReconciliation' })
const { width } = useWindowSize()
const displayTime = (v: string) => new Date(v).toLocaleString('zh-CN', { hour12: false })
const query = reactive({ pageNo: 1, pageSize: 10 })
const rows = ref<ReconcileRun[]>([])
const total = ref(0),
  loading = ref(false),
  listError = ref(false)
const running = ref(false),
  runError = ref(''),
  runKey = ref('')
const detailOpen = ref(false),
  detailLoading = ref(false),
  detailError = ref(false)
const detail = ref<ReconcileRun>()
const itemQuery = reactive({ pageNo: 1, pageSize: 10, status: '' })
const items = ref<ReconcileFinding[]>([]),
  itemTotal = ref(0),
  itemLoading = ref(false),
  itemError = ref(false)
const selected = ref<ReconcileFinding>()
const note = ref(''),
  reviewKey = ref(''),
  reviewing = ref(false),
  reviewError = ref('')
const trail = ref<ReconcileReview[]>([]),
  trailPage = ref(1),
  trailTotal = ref(0),
  trailLoading = ref(false),
  trailError = ref(false)
let listRequest = 0,
  detailRequest = 0,
  itemRequest = 0,
  trailRequest = 0
async function load() {
  const token = ++listRequest
  loading.value = true
  listError.value = false
  try {
    const data = await ReconcileApi.page(query.pageNo, query.pageSize)
    if (token === listRequest) {
      rows.value = data.list
      total.value = data.total
    }
  } catch {
    if (token === listRequest) listError.value = true
  } finally {
    if (token === listRequest) loading.value = false
  }
}
async function run() {
  if (running.value) return
  running.value = true
  runError.value = ''
  runKey.value ||= crypto.randomUUID()
  try {
    const result = await ReconcileApi.run(runKey.value)
    runKey.value = ''
    query.pageNo = 1
    ElMessage.success(`核对完成，发现 ${result.differenceCount} 项差异。`)
    await load()
    await open(result.id)
  } catch {
    runError.value =
      '核对未能确认完成。可重试本次请求；若提示超出上限，请联系维护人员处理扫描范围。重试不会重复生成报告。'
  } finally {
    running.value = false
  }
}
async function open(id: string) {
  if (reviewing.value) return
  const token = ++detailRequest
  ++itemRequest
  ++trailRequest
  detailOpen.value = true
  detailLoading.value = true
  detailError.value = false
  detail.value = undefined
  selected.value = undefined
  itemQuery.pageNo = 1
  itemQuery.status = ''
  items.value = []
  try {
    const value = await ReconcileApi.get(id)
    if (token !== detailRequest) return
    detail.value = value
    await loadItems()
  } catch {
    if (token === detailRequest) detailError.value = true
  } finally {
    if (token === detailRequest) detailLoading.value = false
  }
}
function closeDetail(done: () => void) {
  if (reviewing.value) return
  ++detailRequest
  ++itemRequest
  ++trailRequest
  done()
}
function filterItems() {
  itemQuery.pageNo = 1
  loadItems()
}
async function loadItems() {
  if (!detail.value) return
  const token = ++itemRequest
  itemLoading.value = true
  itemError.value = false
  try {
    const data = await ReconcileApi.items(
      detail.value.id,
      itemQuery.pageNo,
      itemQuery.pageSize,
      itemQuery.status || undefined
    )
    if (token === itemRequest) {
      items.value = data.list
      itemTotal.value = data.total
    }
  } catch {
    if (token === itemRequest) itemError.value = true
  } finally {
    if (token === itemRequest) itemLoading.value = false
  }
}
function selectFinding(row: ReconcileFinding) {
  selected.value = row
  note.value = ''
  reviewKey.value = ''
  reviewError.value = ''
  trailPage.value = 1
  trail.value = []
  loadTrail()
}
async function loadTrail() {
  if (!detail.value || !selected.value) return
  const token = ++trailRequest
  trailLoading.value = true
  trailError.value = false
  try {
    const data = await ReconcileApi.reviews(detail.value.id, selected.value.id, trailPage.value)
    if (token === trailRequest) {
      trail.value = data.list
      trailTotal.value = data.total
    }
  } catch {
    if (token === trailRequest) trailError.value = true
  } finally {
    if (token === trailRequest) trailLoading.value = false
  }
}
async function review() {
  if (!selected.value || reviewing.value || !note.value.trim()) return
  reviewing.value = true
  reviewError.value = ''
  reviewKey.value ||= crypto.randomUUID()
  try {
    await ReconcileApi.review(selected.value.id, note.value.trim(), reviewKey.value)
    reviewKey.value = ''
    note.value = ''
    ElMessage.success('说明已保存，原始差异保持。')
    trailPage.value = 1
    await Promise.all([loadItems(), loadTrail()])
  } catch {
    reviewError.value = '说明保存未能确认，请重试。相同请求不会重复记录。'
  } finally {
    reviewing.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.reconcile-page,
.reconcile-detail-content {
  --el-color-primary: #2d6fb3;
  --el-text-color-placeholder: #606266;
}

.help {
  margin: 16px 0;
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

.toolbar :deep(.el-button + .el-button) {
  margin-left: 0;
}

.status-select {
  width: 160px;
}

.facts-table {
  font-variant-numeric: tabular-nums;
}

.difference-count {
  font-weight: 600;
  color: var(--el-color-danger-dark-2);
}

.table-counts {
  margin: 20px 0;
  overflow-wrap: anywhere;
}

.table-counts summary {
  cursor: pointer;
}

.table-counts dl {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 20px;
  max-width: 540px;
}

.table-counts dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.review-section {
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color);
}

.reconcile-detail-content h3 {
  margin: 28px 0 12px;
  font-size: 16px;
}

.reconcile-detail-content :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}

.review-section :deep(.el-form) {
  max-width: 640px;
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
</style>
