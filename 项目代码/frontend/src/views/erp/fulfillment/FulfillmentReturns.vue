<template>
  <section class="returns" aria-label="退货申请与收货">
    <p class="help"
      >申请不会增加库存；确认实际收货后退回原发货仓，累计已发货量保持不变，不自动退款。</p
    >
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-if="canCreate && canQueryShipments">
      <h4>申请退货</h4>
      <el-form label-position="top" class="return-form" @submit.prevent="create">
        <el-form-item label="原发货记录">
          <el-select
            v-model="shipmentId"
            placeholder="选择本页发货记录"
            :disabled="busy"
            @change="loadAllowance"
          >
            <el-option
              v-for="s in shipments"
              :key="s.id"
              :value="s.id"
              :label="`${s.shipmentNo} · 仓库 ${s.warehouseId}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="退货原因">
          <el-input
            v-model="reason"
            placeholder="例如：商品型号不符"
            maxlength="128"
            :disabled="busy"
          />
        </el-form-item>
      </el-form>
      <div class="shipment-pages">
        <span>原发货共 {{ shipmentTotal }} 条；每页 10 条</span>
        <el-button :disabled="busy || shipmentPage <= 1" @click="changeShipmentPage(-1)"
          >上一页发货</el-button
        >
        <el-button
          :disabled="busy || shipmentPage * 10 >= shipmentTotal"
          @click="changeShipmentPage(1)"
          >下一页发货</el-button
        >
      </div>
      <p class="help"
        >可退量已扣除申请中和已收货数量，仅供当前参考；提交时会再次校验。无需退货的行留空。</p
      >
      <el-table
        v-loading="allowanceLoading"
        :data="allowance"
        empty-text="选择一条原发货记录后填写退货量。"
        class="quantities"
      >
        <el-table-column prop="shipmentItemId" label="发货项" width="95" />
        <el-table-column label="商品编号" min-width="105"
          ><template #default="{ row }">{{ product(row.orderItemId) }}</template></el-table-column
        >
        <el-table-column prop="shippedQty" label="原发货量" min-width="130" align="right" />
        <el-table-column prop="committedQty" label="已占可退额度" min-width="145" align="right" />
        <el-table-column prop="availableQty" label="可退量" min-width="130" align="right" />
        <el-table-column label="本次申请量" min-width="155"
          ><template #default="{ row }">
            <el-input
              v-model="quantities[row.shipmentItemId]"
              :aria-label="`发货项 ${row.shipmentItemId} 申请退货量`"
              inputmode="decimal"
              placeholder="不退则留空"
              :disabled="busy || row.availableQty === '0.000000'"
            /> </template
        ></el-table-column>
      </el-table>
      <el-button
        type="primary"
        :disabled="busy || !allowance.length"
        :loading="doing === 'create'"
        @click="create"
        >提交退货申请</el-button
      >
    </template>
    <p v-else-if="canCreate" class="help"
      >查询原发货记录后才能申请退货，请联系管理员开通发货查询权限。</p
    >
    <div class="history-heading"
      ><h4>退货记录</h4
      ><el-button :disabled="busy" :loading="loading" @click="refresh">刷新退货记录</el-button></div
    >
    <el-table
      v-loading="loading"
      :data="rows"
      row-key="id"
      empty-text="暂无退货。可先选择原发货记录，提交退货申请。"
      class="quantities"
    >
      <el-table-column type="expand"
        ><template #default="{ row }">
          <div class="return-detail">
            <p>原发货编号：{{ row.shipmentId }} · 原仓库：{{ row.warehouseId }}</p>
            <p>申请原因：{{ row.reason }}</p>
            <p v-if="row.rejectionReason">拒绝原因：{{ row.rejectionReason }}</p>
            <p v-if="row.receivedAt">收货时间：{{ time(row.receivedAt) }}</p>
            <el-table :data="row.items" class="quantities">
              <el-table-column prop="shipmentItemId" label="原发货项" min-width="100" />
              <el-table-column label="商品编号" min-width="100"
                ><template #default="{ row: item }">{{
                  product(item.orderItemId)
                }}</template></el-table-column
              >
              <el-table-column prop="quantity" label="退货量" min-width="130" align="right" />
              <el-table-column prop="erpSaleReturnItemId" label="ERP 退货项" min-width="115" />
              <el-table-column prop="erpStockRecordId" label="入库流水" min-width="110" />
            </el-table>
            <div v-if="row.status === 'REQUESTED'" class="review-actions">
              <el-button
                v-hasPermi="['fulfillment:return:receive']"
                type="primary"
                :disabled="busy"
                :loading="doing === `receive:${row.id}`"
                @click="receive(row)"
                >确认实际收货入库</el-button
              >
              <template v-if="canReject">
                <el-input
                  v-model="rejection[row.id]"
                  :aria-label="`退货 ${row.id} 拒绝原因`"
                  placeholder="拒绝申请时填写原因"
                  maxlength="128"
                  :disabled="busy"
                />
                <el-button
                  type="danger"
                  plain
                  :disabled="busy"
                  :loading="doing === `reject:${row.id}`"
                  @click="reject(row)"
                  >拒绝申请</el-button
                >
              </template>
            </div>
          </div>
        </template></el-table-column
      >
      <el-table-column prop="id" label="退货编号" width="100" />
      <el-table-column label="状态" min-width="120"
        ><template #default="{ row }"
          ><el-tag :type="statusType(row.status)">{{ statusName(row.status) }}</el-tag></template
        ></el-table-column
      >
      <el-table-column prop="shipmentId" label="原发货编号" min-width="115" />
      <el-table-column prop="warehouseId" label="原仓库" min-width="100" />
      <el-table-column prop="erpSaleReturnId" label="ERP 退货单" min-width="120" />
      <el-table-column label="申请时间" min-width="180"
        ><template #default="{ row }">{{ time(row.createTime) }}</template></el-table-column
      >
    </el-table>
    <Pagination v-model:page="page" v-model:limit="limit" :total="total" @pagination="loadRows" />
  </section>
</template>
<script setup lang="ts">
import {
  FulfillmentApi,
  type FulfillmentOrder,
  type FulfillmentReturn,
  type ReturnAllowance,
  type Shipment
} from '@/api/erp/fulfillment'
import { checkPermi } from '@/utils/permission'
import { ElMessage, ElMessageBox } from 'element-plus'
const props = defineProps<{ order: FulfillmentOrder; disabled: boolean }>()
const emit = defineEmits<{ changed: []; busy: [value: boolean] }>()
const canCreate = checkPermi(['fulfillment:return:create'])
const canReject = checkPermi(['fulfillment:return:reject'])
const canQueryShipments = checkPermi(['fulfillment:shipment:query'])
const loading = ref(false)
const allowanceLoading = ref(false)
const doing = ref('')
const busy = computed(
  () => props.disabled || loading.value || allowanceLoading.value || !!doing.value
)
watch([loading, allowanceLoading, doing], () =>
  emit('busy', loading.value || allowanceLoading.value || !!doing.value)
)
onBeforeUnmount(() => emit('busy', false))
const error = ref('')
const reason = ref('')
const shipmentId = ref('')
const shipments = ref<Shipment[]>([])
const shipmentPage = ref(1)
const shipmentTotal = ref(0)
const allowance = ref<ReturnAllowance[]>([])
const quantities = reactive<Record<string, string>>({})
const rejection = reactive<Record<string, string>>({})
const rows = ref<FulfillmentReturn[]>([])
const page = ref(1)
const limit = ref(10)
const total = ref(0)
const keys = new Map<string, string>()
const product = (item: string) => props.order.items.find((i) => i.id === item)?.productId || '—'
const time = (value: string) =>
  new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
const statuses: Record<string, string> = {
  REQUESTED: '待收货',
  RECEIVED: '已收货入库',
  REJECTED: '已拒绝'
}
const statusName = (s: string) => statuses[s] || s
const statusType = (s: string) =>
  s === 'RECEIVED' ? 'success' : s === 'REJECTED' ? 'info' : 'warning'
function units(value: string) {
  if (!/^[0-9]{1,18}(\.[0-9]{1,6})?$/.test(value)) throw new Error('退货量须为最多六位小数的正数。')
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, '0'))
}
const amount = (q: bigint) => `${q / 1000000n}.${(q % 1000000n).toString().padStart(6, '0')}`
async function loadRows() {
  const result = await FulfillmentApi.returns(props.order.id, page.value, limit.value)
  rows.value = result.list
  total.value = result.total
}
async function loadShipments() {
  if (!canCreate || !canQueryShipments) return
  const result = await FulfillmentApi.shipments(props.order.id, shipmentPage.value, 10)
  shipments.value = result.list
  shipmentTotal.value = result.total
}
async function loadAllowance() {
  allowance.value = []
  if (!shipmentId.value) return
  allowanceLoading.value = true
  try {
    allowance.value = await FulfillmentApi.returnAllowance(props.order.id, shipmentId.value)
  } catch {
    error.value = '可退额度加载失败，请刷新退货记录后重试。'
  } finally {
    allowanceLoading.value = false
  }
}
async function changeShipmentPage(delta: number) {
  shipmentPage.value += delta
  shipmentId.value = ''
  allowance.value = []
  loading.value = true
  try {
    await loadShipments()
  } catch {
    error.value = '发货记录加载失败，请刷新退货记录后重试。'
  } finally {
    loading.value = false
  }
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadRows(), loadShipments()])
    await loadAllowance()
  } catch {
    error.value = '退货记录加载失败，请刷新退货记录重试。'
  } finally {
    loading.value = false
  }
}
async function refresh() {
  if (!loading.value && !allowanceLoading.value && !doing.value) await load()
}
async function perform(
  action: string,
  data: unknown,
  request: (key: string) => Promise<unknown>,
  success: string
) {
  if (busy.value) return
  doing.value = action
  error.value = ''
  const fingerprint = `${action}:${JSON.stringify(data)}`
  let key = keys.get(fingerprint)
  if (!key) {
    key = crypto.randomUUID()
    keys.set(fingerprint, key)
  }
  try {
    await request(key)
    keys.delete(fingerprint)
    if (action === 'create') Object.keys(quantities).forEach((id) => delete quantities[id])
    ElMessage.success(success)
    emit('changed')
    await load()
  } catch {
    error.value = '操作尚未确认完成，请先刷新核对。相同内容重试会复用本次请求编号，避免重复处理。'
  } finally {
    doing.value = ''
  }
}
async function create() {
  try {
    if (!shipmentId.value || !reason.value.trim())
      throw new Error('请选择原发货记录并填写退货原因。')
    const items = allowance.value
      .filter((r) => quantities[r.shipmentItemId]?.trim())
      .map((r) => {
        const q = units(quantities[r.shipmentItemId].trim())
        if (q <= 0n || q > units(r.availableQty))
          throw new Error(`发货项 ${r.shipmentItemId} 的申请量须大于零且不超过当前可退量。`)
        return { id: r.shipmentItemId, quantity: amount(q) }
      })
      .sort((a, b) => a.id.localeCompare(b.id))
    if (!items.length) throw new Error('请至少填写一项退货量。')
    const data = {
      orderId: props.order.id,
      shipmentId: shipmentId.value,
      items,
      reason: reason.value.trim()
    }
    await perform(
      'create',
      data,
      (key) => FulfillmentApi.createReturn(data, key),
      '退货申请已提交，库存尚未入库。'
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : '请检查申请内容。'
  }
}
async function receive(row: FulfillmentReturn) {
  try {
    await ElMessageBox.confirm(
      '请确认货物已实际收到。确认后将退回原发货仓，增加实物库存；不会自动退款。',
      '确认退货收货',
      {
        confirmButtonText: '确认已收到货物',
        confirmButtonClass: 'return-receipt-confirm',
        cancelButtonText: '暂不入库',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  const data = { orderId: props.order.id, returnId: row.id }
  await perform(
    `receive:${row.id}`,
    data,
    (key) => FulfillmentApi.receiveReturn(data, key),
    '退货已收货入库，累计发货量保持不变。'
  )
}
async function reject(row: FulfillmentReturn) {
  const reason = rejection[row.id]?.trim()
  if (!reason) {
    error.value = '拒绝申请前请填写原因。'
    return
  }
  const data = { orderId: props.order.id, returnId: row.id, reason }
  await perform(
    `reject:${row.id}`,
    data,
    (key) => FulfillmentApi.rejectReturn(data, key),
    '申请已拒绝，可退额度已释放，库存保持不变。'
  )
}
watch(
  () => props.order.id,
  () => {
    page.value = 1
    shipmentPage.value = 1
    shipmentId.value = ''
    void load()
  },
  { immediate: true }
)
defineExpose({ refresh })
</script>
<style scoped lang="scss">
.returns {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.returns > .el-button {
  justify-self: start;
}

.returns h4,
.returns p {
  margin: 0;
}

.help {
  max-width: 70ch;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.return-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.return-form :deep(.el-select) {
  width: 100%;
}

.shipment-pages,
.history-heading,
.review-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.shipment-pages {
  color: var(--el-text-color-regular);
}

.history-heading {
  justify-content: space-between;
  margin-top: 12px;
}

.return-detail {
  display: grid;
  min-width: 0;
  padding: 16px;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  overflow-wrap: anywhere;
}

.review-actions :deep(.el-input) {
  flex: 1 1 220px;
}

.quantities :deep(.cell) {
  font-variant-numeric: tabular-nums;
}

.returns :deep(input::placeholder),
.returns :deep(.el-table th.el-table__cell) {
  color: var(--el-text-color-regular);
  opacity: 1;
}

.returns :deep(.el-tag) {
  --el-tag-text-color: var(--el-text-color-primary);
}

.returns :deep(.el-button--primary),
:global(.return-receipt-confirm.el-button--primary) {
  --el-button-bg-color: color-mix(in srgb, var(--el-color-primary) 70%, black);
  --el-button-border-color: var(--el-button-bg-color);
  --el-button-hover-bg-color: color-mix(in srgb, var(--el-color-primary) 60%, black);
  --el-button-hover-border-color: var(--el-button-hover-bg-color);
  --el-button-active-bg-color: var(--el-button-hover-bg-color);
  --el-button-active-border-color: var(--el-button-hover-bg-color);
}

@media (width <= 640px) {
  .return-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .return-detail {
    max-width: calc(100vw - 80px);
    padding: 8px;
  }
}
</style>
