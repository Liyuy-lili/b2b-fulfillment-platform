<template>
  <section class="workbench" aria-label="履约操作工作台">
    <div class="workbench-heading">
      <h3>履约操作</h3>
      <el-button :loading="loading" :disabled="busy" @click="loadData">刷新记录</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-tabs v-model="tab">
      <el-tab-pane label="分配库存" name="allocation">
        <p class="help">选择参与分配的仓库。预览不会占用库存，确认分配时会重新计算。</p>
        <el-form label-position="top" class="allocation-form" @submit.prevent="previewPlan">
          <el-form-item label="候选仓库">
            <el-select
              v-model="allocation.warehouseIds"
              multiple
              filterable
              placeholder="选择启用仓库（最多 16 个）"
              :multiple-limit="16"
              :disabled="busy"
            >
              <el-option v-for="w in warehouses" :key="w.id" :value="w.id" :label="w.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="分仓策略">
            <el-select v-model="allocation.strategy" :disabled="busy">
              <el-option label="按仓库优先级拆分" value="PRIORITY_SPLIT" />
              <el-option label="优先单仓满足整单" value="SINGLE_FIRST" />
            </el-select>
          </el-form-item>
          <el-form-item label="预占有效期">
            <el-select v-model="allocation.holdSeconds" :disabled="busy">
              <el-option label="24 小时" :value="86400" /><el-option
                label="1 小时"
                :value="3600"
              /><el-option label="2 分钟（演示）" :value="120" />
            </el-select>
          </el-form-item>
        </el-form>
        <div class="actions">
          <el-button
            v-hasPermi="['fulfillment:order:allocate']"
            :disabled="busy || !allocation.warehouseIds.length"
            :loading="doing === 'preview'"
            @click="previewPlan"
            >预览分配</el-button
          >
          <el-button
            v-hasPermi="['fulfillment:order:allocate']"
            type="primary"
            :disabled="busy || !allocation.warehouseIds.length"
            :loading="doing === 'allocate'"
            @click="allocate"
            >确认分配</el-button
          >
        </div>
        <template v-if="preview">
          <p class="preview-result" role="status"
            >{{
              preview.sufficient
                ? '当前库存可满足全部待分配量'
                : '当前库存不足，本次不会产生部分预占'
            }}
            · 策略版本 {{ preview.strategyVersion }}</p
          >
          <el-table :data="preview.stocks" empty-text="没有待分配数量" class="quantities">
            <el-table-column prop="productId" label="商品编号" min-width="100" /><el-table-column
              prop="warehouseId"
              label="仓库编号"
              min-width="100"
            />
            <el-table-column
              prop="physical"
              label="实物 H"
              min-width="140"
              align="right"
            /><el-table-column
              prop="reserved"
              label="预占 R"
              min-width="140"
              align="right"
            /><el-table-column prop="available" label="可用 A" min-width="140" align="right" />
          </el-table>
          <h4>预览计划</h4>
          <el-table :data="preview.plan" empty-text="暂无分配计划" class="quantities">
            <el-table-column prop="orderItemId" label="订单项" /><el-table-column
              prop="warehouseId"
              label="仓库"
            /><el-table-column prop="quantity" label="计划预占量" min-width="150" align="right" />
          </el-table>
        </template>
      </el-tab-pane>
      <el-tab-pane label="预占与发货" name="reservation">
        <p class="help"
          >勾选同一仓库的预占并填写数量。发货会实际出库；释放只将预占转回待分配。到期记录请先释放，再重新分配。</p
        >
        <el-table
          v-loading="loading"
          :data="activeReservations"
          row-key="id"
          empty-text="没有持有中的预占，请先分配库存。"
          class="quantities"
          @selection-change="selected = $event"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="id" label="预占编号" width="90" /><el-table-column
            prop="orderItemId"
            label="订单项"
            width="90"
          />
          <el-table-column label="仓库" min-width="140"
            ><template #default="{ row }">{{
              warehouseName(row.warehouseId)
            }}</template></el-table-column
          >
          <el-table-column prop="heldQty" label="持有量" min-width="130" align="right" />
          <el-table-column label="到期时间" min-width="175"
            ><template #default="{ row }"
              ><span :class="{ expired: expired(row) }"
                >{{ displayTime(row.expireAt) }}{{ expired(row) ? '（已到期）' : '' }}</span
              ></template
            ></el-table-column
          >
          <el-table-column label="本次数量" min-width="150"
            ><template #default="{ row }"
              ><el-input
                v-model="reservationQty[row.id]"
                :aria-label="`预占 ${row.id} 本次数量`"
                inputmode="decimal"
                :disabled="busy" /></template
          ></el-table-column>
        </el-table>
        <el-form label-position="top" class="shipment-form" @submit.prevent="ship">
          <el-form-item label="承运商"
            ><el-input
              v-model="carrier"
              maxlength="64"
              placeholder="例如：本地模拟物流"
              :disabled="busy"
          /></el-form-item>
          <el-form-item label="物流单号"
            ><el-input
              v-model="tracking"
              maxlength="128"
              placeholder="填写本次发货的物流单号"
              :disabled="busy"
          /></el-form-item>
          <el-form-item label="释放原因"
            ><el-input
              v-model="releaseReason"
              maxlength="128"
              placeholder="释放预占时必填"
              :disabled="busy"
          /></el-form-item>
        </el-form>
        <div class="actions">
          <el-button
            v-hasPermi="['fulfillment:shipment:confirm']"
            type="primary"
            :disabled="busy || !selected.length"
            :loading="doing === 'ship'"
            @click="ship"
            >确认发货</el-button
          >
          <el-button
            v-hasPermi="['fulfillment:order:release']"
            :disabled="busy || !selected.length"
            :loading="doing === 'release'"
            @click="release"
            >释放所选预占</el-button
          >
        </div>
        <el-collapse class="history"
          ><el-collapse-item title="全部预占记录（含已消费和已释放）" name="all">
            <el-table :data="reservations" empty-text="暂无预占历史" class="quantities"
              ><el-table-column prop="id" label="预占编号" /><el-table-column
                prop="allocatedQty"
                label="累计分配"
                min-width="140" /><el-table-column
                prop="heldQty"
                label="持有"
                min-width="140" /><el-table-column
                prop="consumedQty"
                label="已消费"
                min-width="140" /><el-table-column
                prop="releasedQty"
                label="已释放"
                min-width="140"
            /></el-table> </el-collapse-item
        ></el-collapse>
      </el-tab-pane>
      <el-tab-pane label="取消未发货量" name="cancel">
        <p class="help"
          >按订单项填写本次取消量；先取消待分配部分，再释放预占。已经发出的数量不能取消。</p
        >
        <el-table :data="order.items" class="quantities"
          ><el-table-column prop="id" label="订单项" width="100" /><el-table-column
            prop="productId"
            label="商品编号"
            width="100" /><el-table-column label="可取消量" min-width="150" align="right"
            ><template #default="{ row }">{{
              remaining(row.openQty, row.reservedQty)
            }}</template></el-table-column
          ><el-table-column label="本次取消量" min-width="170"
            ><template #default="{ row }"
              ><el-input
                v-model="cancelQty[row.id]"
                :aria-label="`订单项 ${row.id} 取消量`"
                inputmode="decimal"
                placeholder="不取消则留空"
                :disabled="busy" /></template></el-table-column
        ></el-table>
        <el-form label-position="top" class="cancel-form" @submit.prevent="cancel"
          ><el-form-item label="取消原因"
            ><el-input
              v-model="cancelReason"
              maxlength="128"
              placeholder="例如：客户调整采购计划"
              :disabled="busy" /></el-form-item
        ></el-form>
        <el-button
          v-hasPermi="['fulfillment:order:cancel']"
          type="danger"
          plain
          :disabled="busy"
          :loading="doing === 'cancel'"
          @click="cancel"
          >确认取消未发货量</el-button
        >
        <h4>最近 100 条取消记录</h4
        ><el-table :data="cancellations" empty-text="暂无取消记录" class="quantities"
          ><el-table-column prop="orderItemId" label="订单项" /><el-table-column
            prop="quantity"
            label="取消量"
            min-width="140"
          /><el-table-column prop="reason" label="原因" min-width="180" /><el-table-column
            label="时间"
            min-width="180"
            ><template #default="{ row }">{{
              displayTime(row.createTime)
            }}</template></el-table-column
          ></el-table
        >
      </el-tab-pane>
      <el-tab-pane v-if="canQueryShipments" label="发货与物流" name="shipment">
        <p class="help"
          >发货记录关联 ERP 出库。物流通知只更新运输状态，不再次扣库存；此处使用本地模拟物流。</p
        >
        <el-table :data="shipments" empty-text="暂无发货记录" class="quantities">
          <el-table-column type="expand"
            ><template #default="{ row }"
              ><div class="shipment-detail"
                ><h4>发货明细</h4
                ><el-table :data="row.items"
                  ><el-table-column prop="reservationId" label="预占编号" /><el-table-column
                    prop="quantity"
                    label="发货量" /><el-table-column
                    prop="erpSaleOutItemId"
                    label="ERP 出库明细" /></el-table
                ><h4>最近 100 条物流事件</h4
                ><el-table :data="row.events" empty-text="尚未收到物流通知"
                  ><el-table-column
                    prop="eventId"
                    label="事件编号"
                    min-width="220"
                  /><el-table-column label="事件" min-width="130"
                    ><template #default="{ row: event }">{{
                      event.eventType === 'DELIVERED' ? '已签收' : '运输中'
                    }}</template></el-table-column
                  ><el-table-column label="处理结果" min-width="160"
                    ><template #default="{ row: event }">{{
                      outcomeName(event.outcome)
                    }}</template></el-table-column
                  ><el-table-column label="发生时间" min-width="180"
                    ><template #default="{ row: event }">{{
                      displayTime(event.occurredAt)
                    }}</template></el-table-column
                  ></el-table
                ></div
              ></template
            ></el-table-column
          >
          <el-table-column prop="shipmentNo" label="发货单号" min-width="340" /><el-table-column
            prop="erpSaleOutId"
            label="ERP 出库"
            min-width="100"
          /><el-table-column label="配送状态" min-width="110"
            ><template #default="{ row }"
              ><el-tag :type="row.status === 'DELIVERED' ? 'success' : 'primary'">{{
                row.status === 'DELIVERED' ? '已签收' : '已发货'
              }}</el-tag></template
            ></el-table-column
          ><el-table-column prop="trackingNo" label="物流单号" min-width="160" /><el-table-column
            label="模拟通知"
            min-width="200"
            ><template #default="{ row }"
              ><el-button
                v-hasPermi="['fulfillment:shipment:simulate']"
                link
                type="primary"
                :disabled="busy"
                @click="simulate(row.id, 'IN_TRANSIT')"
                >运输中</el-button
              ><el-button
                v-hasPermi="['fulfillment:shipment:simulate']"
                link
                type="primary"
                :disabled="busy"
                @click="simulate(row.id, 'DELIVERED')"
                >签收</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <Pagination
          v-model:page="shipmentPage"
          v-model:limit="shipmentLimit"
          :total="shipmentTotal"
          @pagination="loadShipments"
        />
      </el-tab-pane>
      <el-tab-pane v-if="canQueryReturns" label="退货与收货" name="returns">
        <FulfillmentReturns
          ref="returnWorkbench"
          :order="order"
          :disabled="loading || !!doing || messageBusy"
          @busy="returnBusy = $event"
          @changed="emit('changed')"
        />
      </el-tab-pane>
      <el-tab-pane v-if="canQueryMessages" label="消息与读模型" name="messages" lazy>
        <FulfillmentMessages
          ref="messageWorkbench"
          :order="order"
          :disabled="loading || !!doing || returnBusy"
          @busy="messageBusy = $event"
        />
      </el-tab-pane>
    </el-tabs>
  </section>
</template>
<script setup lang="ts">
import {
  FulfillmentApi,
  type FulfillmentOrder,
  type Reservation,
  type Shipment,
  type Cancellation,
  type Preview,
  type QuantityLine
} from '@/api/erp/fulfillment'
import { checkPermi } from '@/utils/permission'
import { ElMessage } from 'element-plus'
import FulfillmentReturns from './FulfillmentReturns.vue'
import FulfillmentMessages from './FulfillmentMessages.vue'
const props = defineProps<{ order: FulfillmentOrder }>()
const emit = defineEmits<{ changed: [] }>()
const tab = ref('allocation')
const error = ref('')
const loading = ref(false)
const doing = ref('')
const returnBusy = ref(false)
const messageBusy = ref(false)
const messageWorkbench = ref<InstanceType<typeof FulfillmentMessages>>()
const canQueryMessages = checkPermi(['fulfillment:message:query'])
const returnWorkbench = ref<InstanceType<typeof FulfillmentReturns>>()
const busy = computed(() => loading.value || !!doing.value || returnBusy.value || messageBusy.value)
const canQueryReturns = checkPermi(['fulfillment:return:query'])
const canQueryShipments = checkPermi(['fulfillment:shipment:query'])
const warehouses = ref<{ id: string; name: string }[]>([])
const reservations = ref<Reservation[]>([])
const selected = ref<Reservation[]>([])
const reservationQty = reactive<Record<string, string>>({})
const cancelQty = reactive<Record<string, string>>({})
const shipments = ref<Shipment[]>([])
const cancellations = ref<Cancellation[]>([])
const shipmentPage = ref(1)
const shipmentLimit = ref(10)
const shipmentTotal = ref(0)
const preview = ref<Preview>()
const allocation = reactive({
  warehouseIds: [] as string[],
  strategy: 'PRIORITY_SPLIT',
  holdSeconds: 86400
})
const carrier = ref('本地模拟物流')
const tracking = ref('')
const releaseReason = ref('')
const cancelReason = ref('')
const keys = new Map<string, string>()
const units = (q: string) => {
  if (!/^[0-9]{1,18}(\.[0-9]{1,6})?$/.test(q)) throw new Error('数量须为最多六位小数的正数。')
  const [whole, fraction = ''] = q.split('.')
  return BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, '0'))
}
const positive = (q: string) => units(q) > 0n
const activeReservations = computed(() => reservations.value.filter((r) => positive(r.heldQty)))
const remaining = (a: string, b: string) => {
  const q = units(a) + units(b)
  return `${q / 1000000n}.${(q % 1000000n).toString().padStart(6, '0')}`
}
const expired = (r: Reservation) => new Date(r.expireAt).getTime() <= Date.now()
const warehouseName = (id: string) =>
  warehouses.value.find((w) => w.id === id)?.name || `仓库 ${id}`
const displayTime = (v: string) =>
  new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
const outcomeNames: Record<string, string> = {
  DELIVERED: '已更新签收',
  IGNORED_AFTER_DELIVERED: '保留签收状态',
  RECORDED_IN_TRANSIT: '已记录运输中'
}
const outcomeName = (value: string) => outcomeNames[value] || value

watch(
  allocation,
  () => {
    preview.value = undefined
  },
  { deep: true }
)
async function loadShipments() {
  if (!canQueryShipments) return
  const data = await FulfillmentApi.shipments(
    props.order.id,
    shipmentPage.value,
    shipmentLimit.value
  )
  shipments.value = data.list
  shipmentTotal.value = data.total
}
async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [warehouseRows, reservationRows, cancellationRows] = await Promise.all([
      FulfillmentApi.warehouses(),
      FulfillmentApi.reservations(props.order.id),
      FulfillmentApi.cancellations(props.order.id)
    ])
    warehouses.value = warehouseRows
    reservations.value = reservationRows
    cancellations.value = cancellationRows
    selected.value = []
    reservationRows.forEach((r) => {
      reservationQty[r.id] = r.heldQty
    })
    await loadShipments()
    await returnWorkbench.value?.refresh()
    await messageWorkbench.value?.refresh()
  } catch {
    error.value = '操作记录加载失败，请点击刷新记录重试。'
  } finally {
    loading.value = false
  }
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
    ElMessage.success(success)
    preview.value = undefined
    emit('changed')
    await loadData()
  } catch {
    error.value = '操作未确认完成。请先刷新核对记录；相同内容重试会复用本次请求编号。'
  } finally {
    doing.value = ''
  }
}
function allocationInput() {
  return {
    orderId: props.order.id,
    ...allocation,
    warehouseIds: [...allocation.warehouseIds].sort()
  }
}
async function previewPlan() {
  if (busy.value) return
  doing.value = 'preview'
  error.value = ''
  try {
    preview.value = await FulfillmentApi.preview(allocationInput())
  } catch {
    error.value = '分配预览失败，请检查仓库选择后重试。'
  } finally {
    doing.value = ''
  }
}
async function allocate() {
  const data = allocationInput()
  await perform(
    'allocate',
    data,
    async (key) => {
      const result = await FulfillmentApi.allocate(data, key)
      if (result.outcome === 'INSUFFICIENT_STOCK')
        ElMessage.info('库存不足，本次没有新增预占。补货后可再次分配。')
    },
    '分配请求已处理，请查看最新订单数量。'
  )
}
function selectedLines(): QuantityLine[] {
  if (!selected.value.length) throw new Error('请先勾选预占记录。')
  return selected.value
    .map((r) => {
      const quantity = reservationQty[r.id]?.trim() || ''
      if (!positive(quantity) || units(quantity) > units(r.heldQty))
        throw new Error(`预占 ${r.id} 的数量须大于零且不超过持有量。`)
      return { id: r.id, quantity }
    })
    .sort((a, b) => a.id.localeCompare(b.id))
}
function inputError(e: unknown) {
  error.value = e instanceof Error ? e.message : '请检查输入。'
}
async function ship() {
  try {
    const items = selectedLines()
    const warehouseId = selected.value[0].warehouseId
    if (selected.value.some((r) => r.warehouseId !== warehouseId))
      throw new Error('一次发货只能选择同一仓库的预占。')
    if (selected.value.some(expired)) throw new Error('所选预占已到期，请先释放，再重新分配。')
    if (!carrier.value.trim() || !tracking.value.trim()) throw new Error('请填写承运商和物流单号。')
    const data = {
      orderId: props.order.id,
      warehouseId,
      items,
      carrierCode: carrier.value.trim(),
      trackingNo: tracking.value.trim()
    }
    await perform(
      'ship',
      data,
      (key) => FulfillmentApi.ship(data, key),
      '发货完成，ERP 出库已审核。'
    )
  } catch (e) {
    inputError(e)
  }
}
async function release() {
  try {
    if (!releaseReason.value.trim()) throw new Error('请填写释放原因。')
    const data = {
      orderId: props.order.id,
      items: selectedLines().map((i) => ({ reservationId: i.id, quantity: i.quantity })),
      reason: releaseReason.value.trim()
    }
    await perform(
      'release',
      data,
      (key) => FulfillmentApi.release(data, key),
      '预占已释放，实物库存保持不变。'
    )
  } catch (e) {
    inputError(e)
  }
}
async function cancel() {
  try {
    const items = props.order.items
      .filter((i) => cancelQty[i.id]?.trim())
      .map((i) => {
        const quantity = cancelQty[i.id].trim()
        if (!positive(quantity) || units(quantity) > units(i.openQty) + units(i.reservedQty))
          throw new Error(`订单项 ${i.id} 的取消量超过可取消量或格式错误。`)
        return { id: i.id, quantity }
      })
    if (!items.length || !cancelReason.value.trim()) throw new Error('请填写本次取消量和取消原因。')
    const data = { orderId: props.order.id, items, reason: cancelReason.value.trim() }
    await perform('cancel', data, (key) => FulfillmentApi.cancel(data, key), '未发货数量已取消。')
  } catch (e) {
    inputError(e)
  }
}
async function simulate(shipmentId: string, eventType: string) {
  if (busy.value) return
  doing.value = 'simulate'
  error.value = ''
  try {
    await FulfillmentApi.simulate(shipmentId, eventType)
    await loadShipments()
    ElMessage.success('模拟物流通知已处理。')
  } catch {
    error.value = '模拟通知失败，请刷新物流记录后重试。'
  } finally {
    doing.value = ''
  }
}
watch(
  () => props.order.id,
  () => {
    keys.clear()
    shipmentPage.value = 1
    loadData()
  },
  { immediate: true }
)
</script>
<style scoped>
.workbench {
  padding-top: 20px;
  margin-top: 32px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.workbench-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.workbench-heading h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.help {
  max-width: 72ch;
  margin: 8px 0 20px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.allocation-form,
.shipment-form {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) repeat(2, minmax(160px, 1fr));
  gap: 16px;
}

.allocation-form :deep(.el-select) {
  width: 100%;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 8px 0 24px;
}

.actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.quantities {
  font-variant-numeric: tabular-nums;
}

.shipment-form,
.cancel-form {
  margin-top: 20px;
}

.cancel-form {
  max-width: 560px;
}

.preview-result {
  margin: 24px 0 12px;
  color: var(--el-text-color-primary);
}

h4 {
  margin: 28px 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.history {
  margin-top: 28px;
}

.shipment-detail {
  padding: 4px 20px 20px;
}

.expired {
  color: var(--el-color-danger);
}

@media (width <= 640px) {
  .allocation-form,
  .shipment-form {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .workbench-heading {
    align-items: flex-start;
  }
}
</style>
