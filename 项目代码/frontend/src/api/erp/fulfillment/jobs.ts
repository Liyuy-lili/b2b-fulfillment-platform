import request from '@/config/axios'
export type Dataset = 'STOCK' | 'ORDER' | 'SHIPMENT'
export interface FileJob {
  id: string
  actorId: string
  type: 'IMPORT' | 'EXPORT'
  dataset: string
  status: string
  sourceSystem: string
  totalRows: number
  successRows: number
  failedRows: number
  pendingRows: number
  prepared: boolean
  attempts: number
  totalAttempts: number
  sourceCursor: string
  leaseVersion: string
  lastError: string | null
  hasInput: boolean
  hasResult: boolean
  hasErrors: boolean
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  leaseUntil: string | null
  scopeJson: string
}
export interface JobRow {
  rowNo: number
  status: string
  externalNo: string
  erpOrderId: string | null
  outcome: string | null
  errorCode: string | null
}
export interface JobAudit {
  id: string
  actorId: string
  operation: string
  objectType: string
  objectId: string
  reason: string
  beforeJson: string
  afterJson: string
  requestId: string
  createdAt: string
}
export interface WarehouseScope {
  id: string
  name: string
  canOperate: boolean
}
export interface WarehouseGrant {
  id: string
  userId: string
  warehouseId: string
  permission: 'READ' | 'OPERATE'
  enabled: boolean
}
export interface WarehouseStock {
  id: string
  productId: string
  warehouseId: string
  physical: string
  reserved: string
  available: string
}
export interface WarehouseReservation {
  id: string
  orderId: string
  orderNo: string
  warehouseId: string
  productId: string
  heldQty: string
  expireAt: string
}
export interface WarehouseShipment {
  id: string
  shipmentNo: string
  orderId: string
  warehouseId: string
  status: string
  shippedAt: string
}
interface Page<T> {
  list: T[]
  total: number
}
export const FileJobApi = {
  page: (pageNo: number, status?: string) =>
    request.get<Page<FileJob>>({
      url: '/fulfillment/job/page',
      params: { pageNo, pageSize: 10, status }
    }),
  get: (id: string) => request.get<FileJob>({ url: '/fulfillment/job/get', params: { id } }),
  rows: (id: string, pageNo: number) =>
    request.get<Page<JobRow>>({
      url: '/fulfillment/job/rows',
      params: { id, pageNo, pageSize: 10 }
    }),
  audits: (id: string, pageNo: number) =>
    request.get<Page<JobAudit>>({
      url: '/fulfillment/job/audits',
      params: { id, pageNo, pageSize: 10 }
    }),
  upload: async (file: File) => {
    const data = new FormData()
    data.append('file', file)
    const result = await request.upload<{
      data: { fileId: string; sha256: string; byteSize: number }
    }>({ url: '/fulfillment/job/upload', data })
    return result.data
  },
  import: (data: { fileId: string; sourceSystem: string }, key: string) =>
    request.post<{ jobId: string; outcome: string }>({
      url: '/fulfillment/job/import',
      data,
      headers: { 'Idempotency-Key': key }
    }),
  export: (data: { dataset: Dataset; warehouseIds: string[]; orderStatus?: string }, key: string) =>
    request.post<{ jobId: string; outcome: string }>({
      url: '/fulfillment/job/export',
      data,
      headers: { 'Idempotency-Key': key }
    }),
  control: (id: string, action: 'retry' | 'cancel', reason: string, key: string) =>
    request.post({
      url: '/fulfillment/job/' + action,
      data: { jobId: id, reason },
      headers: { 'Idempotency-Key': key }
    }),
  download: (id: string, kind: 'INPUT' | 'RESULT' | 'ERROR') =>
    request.download<Blob>({ url: '/fulfillment/job/download', params: { id, kind } }),
  template: () => request.download<Blob>({ url: '/fulfillment/job/template' })
}
export const WarehouseApi = {
  scope: () => request.get<WarehouseScope[]>({ url: '/fulfillment/warehouse/scope' }),
  stocks: (warehouseId: string, pageNo: number) =>
    request.get<Page<WarehouseStock>>({
      url: '/fulfillment/warehouse/stock-page',
      params: { warehouseId, pageNo, pageSize: 10 }
    }),
  reservations: (warehouseId: string, pageNo: number) =>
    request.get<Page<WarehouseReservation>>({
      url: '/fulfillment/warehouse/reservation-page',
      params: { warehouseId, pageNo, pageSize: 10 }
    }),
  shipments: (warehouseId: string, pageNo: number) =>
    request.get<Page<WarehouseShipment>>({
      url: '/fulfillment/warehouse/shipment-page',
      params: { warehouseId, pageNo, pageSize: 10 }
    }),
  shipment: (id: string) =>
    request.get<{
      id: string
      shipmentNo: string
      items: { id: string; productId: string; quantity: string }[]
    }>({ url: '/fulfillment/warehouse/shipment-get', params: { id } }),
  grants: (userId: string, pageNo: number) =>
    request.get<Page<WarehouseGrant>>({
      url: '/fulfillment/warehouse/grants',
      params: { userId, pageNo, pageSize: 10 }
    }),
  grant: (
    data: {
      userId: string
      warehouseId: string
      permission: string
      enabled: boolean
      reason: string
    },
    key: string
  ) =>
    request.post<string>({
      url: '/fulfillment/warehouse/grant',
      data,
      headers: { 'Idempotency-Key': key }
    }),
  audits: (objectType: string, objectId: string, pageNo: number) =>
    request.get<Page<JobAudit>>({
      url: '/fulfillment/warehouse/audit-page',
      params: { objectType, objectId, pageNo, pageSize: 10 }
    })
}
export async function savePrivateBlob(blob: Blob, name: string) {
  if (blob.type.includes('json')) throw new Error('文件未能下载，请检查当前权限和任务状态。')
  const url = URL.createObjectURL(blob),
    link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
