<template>
  <ContentWrap title="仓库作业">
    <section class="warehouse-surface" aria-label="仓库作业与授权">
      <p class="help"
        >只展示已授权仓库的库存和作业数量，不提供售价、客户隐私或其他仓库明细。操作授权仍需配合相应业务功能权限。</p
      >
      <el-alert
        v-if="scopeError"
        title="仓库范围加载失败，请刷新重试。"
        type="error"
        :closable="false"
      />
      <div class="toolbar"
        ><label for="warehouse-scope">当前仓库</label
        ><el-select
          id="warehouse-scope"
          v-model="warehouseId"
          filterable
          placeholder="选择已授权仓库"
          class="warehouse-select"
          @change="changed"
          ><el-option
            v-for="w in warehouses"
            :key="w.id"
            :label="w.name"
            :value="w.id" /></el-select
        ><span v-if="currentWarehouse">{{
          currentWarehouse.canOperate ? '查看及操作范围' : '仅查看范围'
        }}</span
        ><el-button :disabled="!!working" :loading="loading" @click="refreshScope"
          >刷新仓库范围</el-button
        ></div
      >
      <el-alert
        v-if="!scopeError && !warehouses.length"
        title="当前没有可访问的启用仓库，请联系本租户管理员配置授权。"
        type="info"
        :closable="false"
      />
      <el-tabs v-model="tab" @tab-change="changed">
        <el-tab-pane label="库存 H / R / A" name="stock"
          ><el-alert v-if="error" :title="error" type="error" :closable="false" /><el-table
            v-else
            v-loading="loading"
            :data="stocks"
            empty-text="当前仓库暂无库存记录。"
            class="facts-table"
            ><el-table-column prop="productId" label="商品编号" min-width="130" /><el-table-column
              prop="physical"
              label="实物 H"
              min-width="150"
              align="right" /><el-table-column
              prop="reserved"
              label="预占 R"
              min-width="150"
              align="right" /><el-table-column
              prop="available"
              label="可用 A"
              min-width="150"
              align="right" /></el-table
        ></el-tab-pane>
        <el-tab-pane label="待发预占" name="reservation"
          ><el-alert v-if="error" :title="error" type="error" :closable="false" /><el-table
            v-else
            v-loading="loading"
            :data="reservations"
            empty-text="当前仓库没有尚未发出的预占。"
            class="facts-table"
            ><el-table-column prop="id" label="预占编号" width="110" /><el-table-column
              prop="orderNo"
              label="销售单号"
              min-width="190"
            /><el-table-column prop="productId" label="商品编号" min-width="120" /><el-table-column
              prop="heldQty"
              label="仍占用数量"
              min-width="160"
              align="right"
            /><el-table-column label="到期时间" min-width="190"
              ><template #default="{ row }">{{
                displayTime(row.expireAt)
              }}</template></el-table-column
            ></el-table
          ></el-tab-pane
        >
        <el-tab-pane label="已发货记录" name="shipment"
          ><el-alert v-if="error" :title="error" type="error" :closable="false" /><el-table
            v-else
            v-loading="loading"
            :data="shipments"
            empty-text="当前仓库暂无发货记录。"
            class="facts-table"
            ><el-table-column prop="shipmentNo" label="发货单号" min-width="330" /><el-table-column
              prop="orderId"
              label="履约编号"
              width="110"
            /><el-table-column label="状态" width="110"
              ><template #default="{ row }">{{
                row.status === 'DELIVERED' ? '已签收' : '已发货'
              }}</template></el-table-column
            ><el-table-column label="发货时间" min-width="190"
              ><template #default="{ row }">{{
                displayTime(row.shippedAt)
              }}</template></el-table-column
            ><el-table-column label="操作" width="120" fixed="right"
              ><template #default="{ row }"
                ><el-button link type="primary" @click="openShipment(row.id)"
                  >查看作业明细</el-button
                ></template
              ></el-table-column
            ></el-table
          ></el-tab-pane
        >
        <el-tab-pane v-if="canGrant" label="仓库授权" name="grant">
          <p class="help"
            >授权分为“查看”和“操作”；操作范围包含查看。撤销操作授权后，独立的查看授权仍可能有效。授权仅限本租户用户与仓库。</p
          >
          <el-alert v-if="grantError" :title="grantError" type="error" :closable="false" />
          <el-form label-position="top" class="form-width" @submit.prevent="saveGrant">
            <el-form-item label="用户内部编号"
              ><el-input
                v-model="grant.userId"
                inputmode="numeric"
                placeholder="填写本租户用户编号"
                :disabled="!!working"
            /></el-form-item>
            <el-form-item label="授权仓库"
              ><el-select v-model="grant.warehouseId" filterable :disabled="!!working"
                ><el-option
                  v-for="w in warehouses"
                  :key="w.id"
                  :label="w.name"
                  :value="w.id" /></el-select
            ></el-form-item>
            <el-form-item label="授权类型"
              ><el-select v-model="grant.permission" :disabled="!!working"
                ><el-option label="查看（READ）" value="READ" /><el-option
                  label="查看及操作（OPERATE）"
                  value="OPERATE" /></el-select
            ></el-form-item>
            <el-form-item label="此项授权"
              ><el-switch
                v-model="grant.enabled"
                active-text="启用"
                inactive-text="撤销"
                :disabled="!!working"
            /></el-form-item>
            <el-form-item label="变更原因"
              ><el-input
                v-model="grant.reason"
                :maxlength="256"
                placeholder="记录授权或撤权原因"
                :disabled="!!working"
            /></el-form-item>
            <el-button
              type="primary"
              native-type="submit"
              :disabled="!!working || !grant.reason.trim() || !grant.userId || !grant.warehouseId"
              :loading="working === 'grant'"
              >{{ grantKey ? '重试本次授权变更' : '保存授权变更' }}</el-button
            >
          </el-form>
          <div class="toolbar"
            ><label for="grant-user">查询用户编号</label
            ><el-input
              id="grant-user"
              v-model="queryUser"
              inputmode="numeric"
              class="user-input"
            /><el-button :disabled="!!working || !queryUser" @click="queryGrants"
              >查询授权记录</el-button
            ></div
          >
          <el-alert
            v-if="grantListError"
            title="授权记录加载失败，请检查用户编号并重试。"
            type="error"
            :closable="false"
          />
          <el-table v-else :data="grants" empty-text="输入本租户用户编号查询授权。"
            ><el-table-column prop="warehouseId" label="仓库编号" width="120" /><el-table-column
              prop="permission"
              label="类型"
              width="140"
            /><el-table-column label="当前状态" width="120"
              ><template #default="{ row }">{{
                row.enabled ? '启用' : '已撤销'
              }}</template></el-table-column
            ><el-table-column v-if="canAudit" label="操作" min-width="140"
              ><template #default="{ row }"
                ><el-button link type="primary" @click="openAudit(row.userId, row.warehouseId)"
                  >查看变更审计</el-button
                ></template
              ></el-table-column
            ></el-table
          >
          <div class="pagination-wrap" tabindex="0" aria-label="仓库授权分页"
            ><Pagination
              v-model:page="grantPage"
              :limit="10"
              :total="grantTotal"
              @pagination="loadGrants"
          /></div>
        </el-tab-pane>
      </el-tabs>
      <div v-if="tab !== 'grant'" class="pagination-wrap" tabindex="0" aria-label="仓库作业分页"
        ><Pagination v-model:page="page" :limit="10" :total="total" @pagination="loadData"
      /></div>
    </section>
  </ContentWrap>
  <el-drawer v-model="shipmentOpen" title="仓库发货作业明细" size="min(760px, 100vw)"
    ><div class="warehouse-surface" v-loading="shipmentLoading"
      ><el-alert
        v-if="shipmentError"
        title="发货明细无法读取，请检查当前仓库授权。"
        type="error"
        :closable="false" /><template v-else-if="shipment"
        ><p class="help">发货单 {{ shipment.shipmentNo }}</p
        ><el-table :data="shipment.items"
          ><el-table-column prop="productId" label="商品编号" min-width="130" /><el-table-column
            prop="quantity"
            label="发货数量"
            min-width="160"
            align="right" /></el-table></template></div
  ></el-drawer>
  <el-drawer v-model="auditOpen" title="仓库授权变更审计" size="min(1000px, 100vw)"
    ><div class="warehouse-surface"
      ><p class="help">{{ auditTarget }}</p
      ><el-alert
        v-if="auditError"
        title="审计加载失败，请检查当前审计权限后重试。"
        type="error"
        :closable="false" /><el-table v-else :data="auditRows"
        ><el-table-column prop="actorId" label="操作者" width="110" /><el-table-column
          prop="reason"
          label="原因"
          min-width="230"
        /><el-table-column prop="afterJson" label="变更结果" min-width="260" /><el-table-column
          label="时间"
          min-width="190"
          ><template #default="{ row }">{{ displayTime(row.createdAt) }}</template></el-table-column
        ></el-table
      ><div class="pagination-wrap" tabindex="0" aria-label="授权审计分页"
        ><Pagination
          v-model:page="auditPage"
          :limit="10"
          :total="auditTotal"
          @pagination="loadAudit" /></div></div
  ></el-drawer>
</template>

<script setup lang="ts">
import {
  WarehouseApi,
  type WarehouseScope,
  type WarehouseStock,
  type WarehouseReservation,
  type WarehouseShipment,
  type WarehouseGrant,
  type JobAudit
} from '@/api/erp/fulfillment/jobs'
import { checkPermi, checkRole } from '@/utils/permission'
import { ElMessage } from 'element-plus'
defineOptions({ name: 'ErpFulfillmentWarehouse' })
const canGrant =
    checkPermi(['fulfillment:warehouse:grant']) && checkRole(['super_admin', 'tenant_admin']),
  canAudit = checkPermi(['fulfillment:audit:query'])
const warehouses = ref<WarehouseScope[]>([]),
  warehouseId = ref(''),
  scopeError = ref(false),
  tab = ref('stock'),
  page = ref(1),
  total = ref(0),
  stocks = ref<WarehouseStock[]>([]),
  reservations = ref<WarehouseReservation[]>([]),
  shipments = ref<WarehouseShipment[]>([]),
  loading = ref(false),
  working = ref(''),
  error = ref('')
const currentWarehouse = computed(() => warehouses.value.find((w) => w.id === warehouseId.value))
const grant = reactive({
    userId: '',
    warehouseId: '',
    permission: 'READ',
    enabled: true,
    reason: ''
  }),
  grantKey = ref(''),
  grantError = ref(''),
  queryUser = ref(''),
  grants = ref<WarehouseGrant[]>([]),
  grantPage = ref(1),
  grantTotal = ref(0),
  grantListError = ref(false)
const shipmentOpen = ref(false),
  shipment = ref<Awaited<ReturnType<typeof WarehouseApi.shipment>>>(),
  shipmentLoading = ref(false),
  shipmentError = ref(false),
  auditOpen = ref(false),
  auditTarget = ref(''),
  auditRows = ref<JobAudit[]>([]),
  auditPage = ref(1),
  auditTotal = ref(0),
  auditError = ref(false)
let dataRequest = 0,
  scopeRequest = 0,
  grantRequest = 0,
  shipmentRequest = 0,
  auditRequest = 0
const displayTime = (value?: string | null) =>
  value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
watch(
  grant,
  () => {
    grantKey.value = ''
  },
  { deep: true }
)
function changed() {
  ++dataRequest
  page.value = 1
  stocks.value = []
  reservations.value = []
  shipments.value = []
  total.value = 0
  loadData()
}
async function refreshScope() {
  const token = ++scopeRequest
  scopeError.value = false
  try {
    const rows = await WarehouseApi.scope()
    if (token !== scopeRequest) return
    warehouses.value = rows
    if (!rows.some((w) => w.id === warehouseId.value)) warehouseId.value = rows[0]?.id || ''
    await loadData()
  } catch {
    if (token === scopeRequest) {
      scopeError.value = true
      warehouses.value = []
      warehouseId.value = ''
      stocks.value = []
      reservations.value = []
      shipments.value = []
    }
  }
}
async function loadData() {
  if (!warehouseId.value || tab.value === 'grant') return
  const token = ++dataRequest,
    id = warehouseId.value,
    selected = tab.value
  loading.value = true
  error.value = ''
  try {
    const result =
      selected === 'stock'
        ? await WarehouseApi.stocks(id, page.value)
        : selected === 'reservation'
          ? await WarehouseApi.reservations(id, page.value)
          : await WarehouseApi.shipments(id, page.value)
    if (token !== dataRequest || id !== warehouseId.value || selected !== tab.value) return
    total.value = result.total
    if (selected === 'stock') stocks.value = result.list as WarehouseStock[]
    else if (selected === 'reservation') reservations.value = result.list as WarehouseReservation[]
    else shipments.value = result.list as WarehouseShipment[]
  } catch {
    if (token === dataRequest) error.value = '当前仓库数据无法读取，请刷新范围并检查授权。'
  } finally {
    if (token === dataRequest) loading.value = false
  }
}
async function saveGrant() {
  if (working.value) return
  if (!/^[1-9][0-9]{0,18}$/.test(grant.userId) || !grant.warehouseId || !grant.reason.trim()) {
    grantError.value = '请填写本租户用户编号、仓库和变更原因。'
    return
  }
  working.value = 'grant'
  grantError.value = ''
  grantKey.value ||= crypto.randomUUID()
  try {
    await WarehouseApi.grant({ ...grant, reason: grant.reason.trim() }, grantKey.value)
    grantKey.value = ''
    queryUser.value = grant.userId
    grantPage.value = 1
    ElMessage.success('仓库授权变更已保存并记录审计。')
    await loadGrants()
  } catch {
    grantError.value = '授权变更未确认完成，请检查权限和归属后重试本次请求。'
  } finally {
    working.value = ''
  }
}
function queryGrants() {
  grantPage.value = 1
  loadGrants()
}
async function loadGrants() {
  if (!/^[1-9][0-9]{0,18}$/.test(queryUser.value)) {
    grantListError.value = true
    return
  }
  const token = ++grantRequest
  grantListError.value = false
  try {
    const result = await WarehouseApi.grants(queryUser.value, grantPage.value)
    if (token !== grantRequest) return
    grants.value = result.list
    grantTotal.value = result.total
  } catch {
    if (token === grantRequest) grantListError.value = true
  }
}
async function openShipment(id: string) {
  const token = ++shipmentRequest
  shipmentOpen.value = true
  shipment.value = undefined
  shipmentLoading.value = true
  shipmentError.value = false
  try {
    const result = await WarehouseApi.shipment(id)
    if (token === shipmentRequest) shipment.value = result
  } catch {
    if (token === shipmentRequest) shipmentError.value = true
  } finally {
    if (token === shipmentRequest) shipmentLoading.value = false
  }
}
async function openAudit(user: string, warehouse: string) {
  auditTarget.value = user + ':' + warehouse
  auditPage.value = 1
  auditOpen.value = true
  await loadAudit()
}
async function loadAudit() {
  const token = ++auditRequest
  auditError.value = false
  try {
    const result = await WarehouseApi.audits('GRANT', auditTarget.value, auditPage.value)
    if (token !== auditRequest) return
    auditRows.value = result.list
    auditTotal.value = result.total
  } catch {
    if (token === auditRequest) auditError.value = true
  }
}
onMounted(refreshScope)
onBeforeUnmount(() => {
  ++dataRequest
  ++scopeRequest
  ++grantRequest
  ++shipmentRequest
  ++auditRequest
})
</script>

<style scoped>
.warehouse-surface {
  --el-color-primary: #2d6fb3;
  --el-text-color-placeholder: #606266;

  min-width: 0;
}

.help {
  max-width: 75ch;
  margin: 12px 0 24px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  overflow-wrap: anywhere;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 16px 0;
}

.warehouse-select {
  width: 270px;
  max-width: 100%;
}

.user-input {
  width: 200px;
}

.form-width {
  max-width: 640px;
  margin: 24px 0;
}

.form-width :deep(.el-select) {
  width: 100%;
}

.facts-table {
  font-variant-numeric: tabular-nums;
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
  .warehouse-surface :deep(.el-button) {
    min-height: 44px;
  }
}
</style>
