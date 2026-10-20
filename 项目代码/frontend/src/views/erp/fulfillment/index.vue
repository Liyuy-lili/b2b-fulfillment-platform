<template>
  <ContentWrap title="履约订单">
    <p class="fulfillment-help"
      >将已审核的销售订单交给履约管理，管理库存分配、部分发货、取消与物流进度。</p
    >
    <el-form :inline="true" :model="query" @submit.prevent="search">
      <el-form-item label="销售单号">
        <el-input
          v-model="query.orderNo"
          placeholder="输入销售单号"
          clearable
          @keyup.enter="search"
        />
      </el-form-item>
      <el-form-item label="履约状态">
        <el-select v-model="query.status" placeholder="全部状态" clearable class="status-filter">
          <el-option v-for="(name, code) in statusNames" :key="code" :label="name" :value="code" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
        <el-button v-hasPermi="['fulfillment:order:bind']" type="primary" plain @click="openBinding"
          >绑定销售单</el-button
        >
      </el-form-item>
    </el-form>
    <el-alert
      v-if="listError"
      title="订单加载失败，请检查连接后重试。"
      type="error"
      :closable="false"
      show-icon
    >
      <el-button text @click="load">重新加载</el-button>
    </el-alert>
    <el-table
      v-else
      v-loading="loading"
      :data="rows"
      empty-text="暂无履约订单。绑定一张已审核、尚未出库的销售单即可开始。"
      class="quantity-table"
    >
      <el-table-column prop="orderNo" label="销售单号" min-width="220" />
      <el-table-column prop="id" label="履约编号" min-width="100" />
      <el-table-column label="履约状态" min-width="130">
        <template #default="{ row }"
          ><el-tag :type="tagType(row.status)">{{
            statusNames[row.status] || row.status
          }}</el-tag></template
        >
      </el-table-column>
      <el-table-column prop="customerId" label="客户编号" min-width="100" />
      <el-table-column prop="totalPrice" label="订单金额（元）" min-width="155" align="right" />
      <el-table-column label="绑定时间" min-width="180">
        <template #default="{ row }">{{ displayTime(row.createTime) }}</template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="85">
        <template #default="{ row }"
          ><el-button link type="primary" @click="showDetail(row.id)">详情</el-button></template
        >
      </el-table-column>
    </el-table>
    <Pagination
      v-model:page="query.pageNo"
      v-model:limit="query.pageSize"
      :total="total"
      @pagination="load"
    />
  </ContentWrap>

  <el-drawer v-model="bindingOpen" title="绑定销售单" size="min(580px, 100vw)">
    <p class="binding-note"
      >请选择已审核、没有出库或退货历史的销售单。绑定后，源单的商品、数量和价格将冻结，出库与退货由履约流程管理。</p
    >
    <el-form label-position="top" @submit.prevent="bind">
      <el-form-item label="选择销售单">
        <el-select
          v-model="sourceId"
          filterable
          remote
          clearable
          :remote-method="loadCandidates"
          :loading="candidatesLoading"
          :disabled="binding"
          placeholder="按销售单号搜索已审核订单"
          class="source-picker"
          @change="bindingChanged"
        >
          <el-option
            v-for="source in candidates"
            :key="source.id"
            :value="String(source.id)"
            :label="`${source.no}（编号 ${source.id}）`"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="销售单编号" :error="bindingError">
        <el-input
          v-model="sourceId"
          :disabled="binding"
          inputmode="numeric"
          placeholder="输入销售订单的数字编号"
          @input="bindingChanged"
        />
      </el-form-item>
      <p class="fulfillment-help">编号是销售订单详情中的记录 ID，与 XSDD 开头的销售单号不同。</p>
      <el-button type="primary" :loading="binding" :disabled="!sourceId || binding" @click="bind"
        >确认绑定</el-button
      >
    </el-form>
  </el-drawer>

  <el-drawer v-model="detailOpen" title="履约订单详情" size="min(1080px, 100vw)">
    <div v-loading="detailLoading" class="detail-content">
      <el-alert
        v-if="detailError"
        title="详情加载失败，请关闭后重试。"
        type="error"
        :closable="false"
      />
      <template v-else-if="detail">
        <el-descriptions :column="viewportWidth < 640 ? 1 : 2" border>
          <el-descriptions-item label="销售单号">{{ detail.orderNo }}</el-descriptions-item>
          <el-descriptions-item label="履约编号">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="履约状态">{{
            statusNames[detail.status] || detail.status
          }}</el-descriptions-item>
          <el-descriptions-item label="订单金额（元）">{{
            detail.totalPrice
          }}</el-descriptions-item>
          <el-descriptions-item label="客户编号">{{ detail.customerId }}</el-descriptions-item>
          <el-descriptions-item label="绑定时间">{{
            displayTime(detail.createTime)
          }}</el-descriptions-item>
        </el-descriptions>
        <h3 class="detail-heading">订单数量</h3>
        <p class="fulfillment-help">每行按商品的基本单位记录；不同商品的数量不合并计算。</p>
        <el-table :data="detail.items" class="quantity-table">
          <el-table-column prop="productId" label="商品编号" width="100" />
          <el-table-column prop="unitId" label="单位编号" width="100" />
          <el-table-column
            v-for="column in quantityColumns"
            :key="column.key"
            :prop="column.key"
            :label="column.label"
            min-width="125"
            align="right"
          />
        </el-table>
        <FulfillmentWorkbench :order="detail" @changed="refreshDetail" />
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { FulfillmentApi, type FulfillmentOrder } from '@/api/erp/fulfillment'
import FulfillmentWorkbench from './FulfillmentWorkbench.vue'
import { SaleOrderApi } from '@/api/erp/sale/order'
import { ElMessage } from 'element-plus'
import { useWindowSize } from '@vueuse/core'

defineOptions({ name: 'ErpFulfillment' })
const { width: viewportWidth } = useWindowSize()
const statusNames: Record<string, string> = {
  NEW: '待分配',
  WAIT_STOCK: '待补货',
  RESERVED: '已预占',
  PARTIALLY_SHIPPED: '部分发货',
  FULFILLED: '已完成',
  CANCELLED: '已取消',
  PARTIALLY_CLOSED: '部分关闭'
}
const quantityColumns = [
  { key: 'orderedQty', label: '订购量' },
  { key: 'openQty', label: '待分配' },
  { key: 'reservedQty', label: '已预占' },
  { key: 'shippedQty', label: '已发货' },
  { key: 'cancelledQty', label: '已取消' },
  { key: 'returnedQty', label: '已退货' }
]
const query = reactive({ pageNo: 1, pageSize: 10, orderNo: '', status: '' })
const rows = ref<FulfillmentOrder[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref(false)
const bindingOpen = ref(false)
const binding = ref(false)
const sourceId = ref('')
const bindingError = ref('')
const candidates = ref<{ id: number; no: string }[]>([])
const candidatesLoading = ref(false)
let bindingKey = ''
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref(false)
const detail = ref<FulfillmentOrder>()
const tagType = (status: string) =>
  status === 'FULFILLED' ? 'success' : status === 'CANCELLED' ? 'info' : 'primary'
const displayTime = (value: string) => new Date(value).toLocaleString('zh-CN', { hour12: false })
async function load() {
  loading.value = true
  listError.value = false
  try {
    const data = await FulfillmentApi.page({
      ...query,
      orderNo: query.orderNo || undefined,
      status: query.status || undefined
    })
    rows.value = data.list
    total.value = data.total
  } catch {
    listError.value = true
  } finally {
    loading.value = false
  }
}
function search() {
  query.pageNo = 1
  load()
}
function reset() {
  query.orderNo = ''
  query.status = ''
  search()
}
function bindingChanged() {
  bindingKey = ''
  bindingError.value = ''
}
function openBinding() {
  sourceId.value = ''
  bindingChanged()
  bindingOpen.value = true
  loadCandidates('')
}
let candidateRequest = 0
async function loadCandidates(no: string) {
  const current = ++candidateRequest
  candidatesLoading.value = true
  try {
    const data = await SaleOrderApi.getSaleOrderPage({
      pageNo: 1,
      pageSize: 20,
      status: 20,
      no: no || undefined
    })
    if (current === candidateRequest)
      candidates.value = data.list.filter((row: { id: number }) => Number.isSafeInteger(row.id))
  } catch {
    if (current === candidateRequest) candidates.value = []
  } finally {
    if (current === candidateRequest) candidatesLoading.value = false
  }
}
async function bind() {
  if (binding.value) return
  if (!/^[1-9][0-9]{0,18}$/.test(sourceId.value)) {
    bindingError.value = '请输入有效的销售单数字编号。'
    return
  }
  binding.value = true
  bindingError.value = ''
  bindingKey ||= crypto.randomUUID()
  try {
    const result = await FulfillmentApi.bind(sourceId.value, bindingKey)
    bindingOpen.value = false
    ElMessage.success('销售单已绑定，执行快照已保存。')
    await load()
    await showDetail(result.orderId)
  } catch {
    bindingError.value = '未能完成绑定，请检查销售单是否已审核、是否有出库历史，或重试。'
  } finally {
    binding.value = false
  }
}
async function showDetail(id: string) {
  detailOpen.value = true
  detailLoading.value = true
  detailError.value = false
  detail.value = undefined
  try {
    detail.value = await FulfillmentApi.get(id)
  } catch {
    detailError.value = true
  } finally {
    detailLoading.value = false
  }
}
async function refreshDetail() {
  if (!detail.value) return
  detail.value = await FulfillmentApi.get(detail.value.id)
  await load()
}
onMounted(load)
</script>

<style scoped>
.fulfillment-help,
.binding-note {
  margin: 0 0 20px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.status-filter {
  width: 180px;
}

.source-picker {
  width: 100%;
}

.detail-heading {
  margin: 28px 0 8px;
  font-size: 16px;
  font-weight: 600;
}

.detail-content {
  min-height: 200px;
}

.quantity-table {
  font-variant-numeric: tabular-nums;
}
</style>
