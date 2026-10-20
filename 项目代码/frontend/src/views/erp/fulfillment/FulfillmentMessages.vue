<template>
  <section class="message-workbench" aria-label="可靠消息与读模型">
    <p class="help"
      >事件与业务一起保存，后台发布和消费分别显示状态。重新发布保留原事件编号，不会再次执行出库或退货。</p
    >
    <div class="toolbar">
      <label for="message-status">发布状态</label>
      <el-select
        id="message-status"
        v-model="status"
        clearable
        placeholder="全部状态"
        :disabled="busy"
        class="status-picker"
        @change="filter"
      >
        <el-option v-for="(name, code) in publishNames" :key="code" :label="name" :value="code" />
      </el-select>
      <el-button :disabled="busy" :loading="loading" @click="refresh">刷新消息与读模型</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-table
      v-else
      v-loading="loading"
      :data="events"
      empty-text="暂无事件。M5上线前的历史业务不会补造事件；可在下方重建当前读模型。"
      class="facts-table"
    >
      <el-table-column label="事件类型" min-width="160"
        ><template #default="{ row }">{{
          typeNames[row.eventType] || row.eventType
        }}</template></el-table-column
      >
      <el-table-column prop="aggregateVersion" label="订单版本" width="100" />
      <el-table-column label="发布状态" min-width="145"
        ><template #default="{ row }">{{
          publishNames[row.status] || row.status
        }}</template></el-table-column
      >
      <el-table-column label="消费状态" min-width="150"
        ><template #default="{ row }">{{
          row.inbox ? consumeNames[row.inbox.status] || row.inbox.status : '未接收'
        }}</template></el-table-column
      >
      <el-table-column prop="totalAttempts" label="累计发送尝试" width="130" align="right" />
      <el-table-column label="操作" width="100" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" :disabled="busy" @click="select(row.eventId)"
            >查看事件</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <div class="pagination-wrap" tabindex="0" aria-label="事件分页"
      ><Pagination v-model:page="page" :limit="10" :total="total" @pagination="refresh"
    /></div>

    <section v-if="selected" class="event-detail" aria-label="事件详情与重放">
      <h3>事件 {{ selected.eventId }}</h3>
      <el-descriptions :column="width < 640 ? 1 : 2" border>
        <el-descriptions-item label="事件类型">{{
          typeNames[selected.eventType] || selected.eventType
        }}</el-descriptions-item>
        <el-descriptions-item label="订单版本 / 格式版本"
          >{{ selected.aggregateVersion }} / {{ selected.payloadVersion }}</el-descriptions-item
        >
        <el-descriptions-item label="发布状态">{{
          publishNames[selected.status]
        }}</el-descriptions-item>
        <el-descriptions-item label="租约版本">{{ selected.leaseVersion }}</el-descriptions-item>
        <el-descriptions-item label="当前轮 / 累计发送尝试"
          >{{ selected.attempts }} / {{ selected.totalAttempts }}</el-descriptions-item
        >
        <el-descriptions-item label="发布错误">{{
          selected.lastError || '无'
        }}</el-descriptions-item>
        <el-descriptions-item label="消费状态">{{
          selected.inbox ? consumeNames[selected.inbox.status] : '未接收'
        }}</el-descriptions-item>
        <el-descriptions-item label="重复投递计数">{{
          selected.inbox?.duplicateCount ?? 0
        }}</el-descriptions-item>
        <el-descriptions-item label="消费错误">{{
          selected.inbox?.lastError || '无'
        }}</el-descriptions-item>
        <el-descriptions-item label="本地重试时间">{{
          displayTime(selected.inbox?.nextAttemptAt)
        }}</el-descriptions-item>
      </el-descriptions>
      <details class="payload"
        ><summary>查看原始事件内容</summary><pre>{{ pretty(selected.body) }}</pre>
      </details>
      <el-form
        v-hasPermi="['fulfillment:message:replay']"
        label-position="top"
        class="intent-form"
        @submit.prevent="replay"
      >
        <el-form-item label="重放意图"
          ><el-select v-model="action" :disabled="busy" @change="resetReplay"
            ><el-option label="重新发布同一事件" value="REPUBLISH" /><el-option
              label="重试本地消费"
              value="RETRY_CONSUME"
              :disabled="!selected.inbox" /></el-select
        ></el-form-item>
        <el-form-item label="操作原因"
          ><el-input
            v-model="reason"
            type="textarea"
            :rows="2"
            :maxlength="256"
            show-word-limit
            placeholder="说明故障原因、恢复措施与重放目的"
            :disabled="busy"
            @input="resetReplay"
        /></el-form-item>
        <el-button
          type="primary"
          :disabled="busy || !reason.trim()"
          :loading="working === 'replay'"
          @click="replay"
          >{{ replayKey ? '重试本次重放' : '确认重放原事件' }}</el-button
        >
      </el-form>
      <p class="help"
        >Broker已确认不代表消费成功。已处理的事件会被去重；若消费已提交，重试本地消费只返回已处理。</p
      >
      <h3>发布尝试</h3>
      <el-alert
        v-if="deliveryError"
        title="发布尝试加载失败，请重新查看事件。"
        type="error"
        :closable="false"
      />
      <el-table v-else :data="deliveries" empty-text="尚未领取发送。" class="facts-table"
        ><el-table-column prop="leaseVersion" label="租约版本" width="100" /><el-table-column
          prop="result"
          label="尝试结果"
          width="120" /><el-table-column
          prop="error"
          label="错误 / 迟到原因"
          min-width="210" /><el-table-column label="开始时间" min-width="180"
          ><template #default="{ row }">{{ displayTime(row.startedAt) }}</template></el-table-column
        ><el-table-column prop="leaseOwner" label="工作者编号" min-width="300"
      /></el-table>
      <div class="pagination-wrap" tabindex="0" aria-label="发布尝试分页"
        ><Pagination
          v-model:page="deliveryPage"
          :limit="10"
          :total="deliveryTotal"
          @pagination="loadDeliveries"
      /></div>
    </section>

    <section class="projection-section" aria-label="可重建履约读模型">
      <h3>履约执行读模型</h3>
      <p v-if="projection" class="help"
        >业务版本 {{ projection.businessVersion }} · 读模型版本
        {{ projection.observedVersion ?? '尚未建立' }} ·
        {{
          projection.observedVersion === projection.businessVersion
            ? '版本已对齐'
            : '等待异步追平或受权重建'
        }}。此视图用于异步查询，库存分配仍以业务数据库为准。</p
      >
      <details v-if="projection?.snapshotJson" class="payload"
        ><summary>查看读模型快照</summary><pre>{{ pretty(projection.snapshotJson) }}</pre>
      </details>
      <el-form
        v-hasPermi="['fulfillment:message:rebuild']"
        label-position="top"
        class="intent-form"
        @submit.prevent="rebuild"
      >
        <el-form-item label="重建原因"
          ><el-input
            v-model="rebuildReason"
            :maxlength="256"
            placeholder="例如：首次建立历史订单视图，或修复读模型"
            :disabled="busy"
            @input="rebuildKey = ''"
        /></el-form-item>
        <el-button
          :disabled="busy || !rebuildReason.trim()"
          :loading="working === 'rebuild'"
          @click="rebuild"
          >{{ rebuildKey ? '重试本次重建' : '重建当前读模型' }}</el-button
        >
      </el-form>
    </section>
    <h3>人工操作记录</h3>
    <el-alert v-if="actionError" title="操作记录加载失败，请重试。" type="error" :closable="false"
      ><el-button text @click="loadActions">重新加载操作记录</el-button></el-alert
    >
    <el-table :data="actions" empty-text="暂无人工重放或重建操作。" class="facts-table"
      ><el-table-column label="动作" min-width="160"
        ><template #default="{ row }">{{
          actionNames[row.action] || row.action
        }}</template></el-table-column
      ><el-table-column prop="reason" label="操作原因" min-width="240" /><el-table-column
        prop="outcome"
        label="结果"
        min-width="230"
      /><el-table-column prop="actorId" label="操作者" width="100" /><el-table-column
        label="时间"
        min-width="180"
        ><template #default="{ row }">{{ displayTime(row.createdAt) }}</template></el-table-column
      ></el-table
    >
    <div class="pagination-wrap" tabindex="0" aria-label="人工操作分页"
      ><Pagination
        v-model:page="actionPage"
        :limit="10"
        :total="actionTotal"
        @pagination="loadActions"
    /></div>
  </section>
</template>

<script setup lang="ts">
import {
  MessageApi,
  type MessageEvent,
  type MessageDelivery,
  type MessageAction,
  type MessageProjection,
  type ReplayAction
} from '@/api/erp/fulfillment/messages'
import { ElMessage } from 'element-plus'
import { useWindowSize } from '@vueuse/core'
const props = defineProps<{ order: { id: string }; disabled: boolean }>()
const emit = defineEmits<{ busy: [value: boolean] }>()
const { width } = useWindowSize()
const publishNames: Record<string, string> = {
  NEW: '待发布',
  IN_FLIGHT: '发布中',
  RETRY_WAIT: '等待发布重试',
  SENT: 'Broker已确认',
  DEAD: '发布停止重试'
}
const consumeNames: Record<string, string> = {
  NEW: '待处理',
  RETRY_WAIT: '本地等待重试',
  PROCESSED: '已处理',
  DEAD: '本地停止重试'
}
const typeNames: Record<string, string> = {
  ORDER_BOUND: '订单已绑定',
  STOCK_RESERVED: '库存已预占',
  ALLOCATION_ATTEMPTED: '分配已尝试',
  STOCK_RELEASED: '预占已释放',
  SHIPMENT_CONFIRMED: '已确认发货',
  ORDER_CANCELLED: '已取消数量',
  RESERVATION_EXPIRED: '预占已到期释放',
  RETURN_RECEIVED: '已确认退货收货'
}
const actionNames: Record<string, string> = {
  REPUBLISH: '重新发布原事件',
  RETRY_CONSUME: '重试本地消费',
  REBUILD: '重建读模型'
}
const events = ref<MessageEvent[]>([]),
  page = ref(1),
  total = ref(0),
  status = ref('')
const selected = ref<MessageEvent>(),
  deliveries = ref<MessageDelivery[]>([]),
  deliveryPage = ref(1),
  deliveryTotal = ref(0),
  deliveryError = ref(false)
const projection = ref<MessageProjection>(),
  actions = ref<MessageAction[]>([]),
  actionPage = ref(1),
  actionTotal = ref(0)
const loading = ref(false),
  working = ref(''),
  error = ref('')
const action = ref<ReplayAction>('REPUBLISH'),
  reason = ref(''),
  replayKey = ref(''),
  rebuildReason = ref(''),
  rebuildKey = ref('')
const actionError = ref(false),
  actionLoading = ref(false)
const busy = computed(() => props.disabled || loading.value || !!working.value)
watch([loading, working], () => emit('busy', loading.value || !!working.value))
let generation = 0,
  detailRequest = 0,
  actionRequest = 0,
  deliveryRequest = 0
const displayTime = (v?: string | null) =>
  v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '—'
function pretty(v: string | null) {
  if (!v) return ''
  try {
    return JSON.stringify(JSON.parse(v), null, 2)
  } catch {
    return v
  }
}
function resetReplay() {
  replayKey.value = ''
}
function filter() {
  page.value = 1
  refresh()
}
async function loadActions() {
  const token = ++actionRequest
  actionError.value = false
  actionLoading.value = true
  try {
    const data = await MessageApi.actions(props.order.id, actionPage.value)
    if (token !== actionRequest) return
    actions.value = data.list
    actionTotal.value = data.total
  } catch {
    if (token === actionRequest) actionError.value = true
  } finally {
    if (token === actionRequest) actionLoading.value = false
  }
}
async function loadDeliveries() {
  if (!selected.value) return
  const token = ++deliveryRequest,
    orderId = props.order.id,
    eventId = selected.value.eventId
  deliveryError.value = false
  try {
    const data = await MessageApi.deliveries(orderId, eventId, deliveryPage.value)
    if (
      token !== deliveryRequest ||
      props.order.id !== orderId ||
      selected.value?.eventId !== eventId
    )
      return
    deliveries.value = data.list
    deliveryTotal.value = data.total
  } catch {
    if (token === deliveryRequest) deliveryError.value = true
  }
}
async function refresh() {
  const token = ++generation
  loading.value = true
  error.value = ''
  try {
    const [rows, model, audit] = await Promise.all([
      MessageApi.page(props.order.id, page.value, status.value || undefined),
      MessageApi.projection(props.order.id),
      MessageApi.actions(props.order.id, actionPage.value)
    ])
    if (token !== generation) return
    actionError.value = false
    events.value = rows.list
    total.value = rows.total
    projection.value = model
    actions.value = audit.list
    actionTotal.value = audit.total
    if (selected.value) {
      const event = await MessageApi.get(props.order.id, selected.value.eventId)
      if (token !== generation) return
      selected.value = event
      await loadDeliveries()
    }
  } catch {
    if (token === generation) error.value = '消息或读模型加载失败，请刷新后重试。'
  } finally {
    if (token === generation) loading.value = false
  }
}
async function select(eventId: string) {
  const token = ++detailRequest
  ++deliveryRequest
  loading.value = true
  error.value = ''
  reason.value = ''
  replayKey.value = ''
  deliveryPage.value = 1
  try {
    const event = await MessageApi.get(props.order.id, eventId)
    if (token !== detailRequest) return
    selected.value = event
    await loadDeliveries()
  } catch {
    error.value = '事件详情加载失败，请重新查看。'
  } finally {
    if (token === detailRequest) loading.value = false
  }
}
async function replay() {
  if (busy.value || !selected.value || !reason.value.trim()) return
  working.value = 'replay'
  error.value = ''
  replayKey.value ||= crypto.randomUUID()
  try {
    await MessageApi.replay(
      {
        orderId: props.order.id,
        eventId: selected.value.eventId,
        action: action.value,
        reason: reason.value.trim()
      },
      replayKey.value
    )
    replayKey.value = ''
    reason.value = ''
    actionPage.value = 1
    ElMessage.success('恢复意图已记录，可刷新观察后台处理结果。')
    await refresh()
  } catch {
    error.value = '本次重放未能确认完成，请检查错误提示后重试原请求。'
  } finally {
    working.value = ''
  }
}
async function rebuild() {
  if (busy.value || !rebuildReason.value.trim()) return
  working.value = 'rebuild'
  error.value = ''
  rebuildKey.value ||= crypto.randomUUID()
  try {
    await MessageApi.rebuild(
      { orderId: props.order.id, reason: rebuildReason.value.trim() },
      rebuildKey.value
    )
    rebuildKey.value = ''
    rebuildReason.value = ''
    actionPage.value = 1
    ElMessage.success('读模型重建操作已完成，业务库存保持。')
    await refresh()
  } catch {
    error.value = '本次重建未能确认完成，可使用原请求重试。'
  } finally {
    working.value = ''
  }
}
watch(
  () => props.order.id,
  () => {
    ++detailRequest
    selected.value = undefined
    page.value = 1
    actionPage.value = 1
    replayKey.value = ''
    rebuildKey.value = ''
    refresh()
  }
)
onMounted(refresh)
onBeforeUnmount(() => {
  ++generation
  ++detailRequest
  ++deliveryRequest
  ++actionRequest
  emit('busy', false)
})
defineExpose({ refresh })
</script>

<style scoped>
.message-workbench {
  --el-color-primary: #2d6fb3;
  --el-text-color-placeholder: #606266;

  min-width: 0;
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

.status-picker {
  width: 190px;
}

.facts-table {
  font-variant-numeric: tabular-nums;
}

.message-workbench h3 {
  margin: 28px 0 12px;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.event-detail,
.projection-section {
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color);
}

.intent-form {
  max-width: 640px;
  margin: 20px 0;
}

.intent-form :deep(.el-select) {
  width: 100%;
}

.payload {
  margin: 20px 0;
}

.payload summary {
  cursor: pointer;
}

.payload pre {
  max-height: 360px;
  padding: 12px;
  overflow: auto;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--el-fill-color-light);
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
