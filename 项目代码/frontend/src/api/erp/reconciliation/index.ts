import request from '@/config/axios'

export interface ReconcileRun {
  id: string
  ruleVersion: string
  scope: string
  snapshotAt: string
  finishedAt: string
  scannedCount: number
  differenceCount: number
  tableCounts: Record<string, number>
}
export interface ReconcileFinding {
  id: string
  runId: string
  ruleCode: string
  objectType: string
  objectId: string
  orderId: string | null
  productId: string | null
  warehouseId: string | null
  expectedValue: string
  actualValue: string
  detail: string
  resolutionStatus: string
}
export interface ReconcileReview {
  id: string
  itemId: string
  actorId: string
  note: string
  reviewedAt: string
}
type Page<T> = { list: T[]; total: number }
const root = '/fulfillment/reconcile'
export const ReconcileApi = {
  run: (key: string): Promise<ReconcileRun> =>
    request.post({
      url: root + '/run',
      data: { scope: 'TENANT' },
      headers: { 'Idempotency-Key': key },
      timeout: 30000
    }),
  page: (pageNo: number, pageSize: number): Promise<Page<ReconcileRun>> =>
    request.get({ url: root + '/page', params: { pageNo, pageSize } }),
  get: (id: string): Promise<ReconcileRun> => request.get({ url: root + '/get', params: { id } }),
  items: (
    runId: string,
    pageNo: number,
    pageSize: number,
    resolutionStatus?: string
  ): Promise<Page<ReconcileFinding>> =>
    request.get({ url: root + '/items', params: { runId, pageNo, pageSize, resolutionStatus } }),
  review: (itemId: string, note: string, key: string): Promise<ReconcileReview> =>
    request.post({
      url: root + '/review',
      data: { itemId, note },
      headers: { 'Idempotency-Key': key }
    }),
  reviews: (runId: string, itemId: string, pageNo: number): Promise<Page<ReconcileReview>> =>
    request.get({ url: root + '/reviews', params: { runId, itemId, pageNo, pageSize: 10 } })
}
