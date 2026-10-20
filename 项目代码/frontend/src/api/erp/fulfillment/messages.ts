import request from '@/config/axios'
export interface MessageInbox {
  id: string
  status: string
  attempts: number
  totalAttempts: number
  duplicateCount: number
  applied: boolean
  nextAttemptAt: string
  processedAt: string | null
  lastError: string | null
}
export interface MessageEvent {
  id: string
  eventId: string
  orderId: string
  aggregateVersion: string
  eventType: string
  payloadVersion: number
  status: string
  attempts: number
  totalAttempts: number
  leaseVersion: string
  leaseUntil: string | null
  nextAttemptAt: string
  lastError: string | null
  createdAt: string
  sentAt: string | null
  inbox: MessageInbox | null
  body: string | null
}
export interface MessageDelivery {
  id: string
  leaseVersion: string
  leaseOwner: string
  result: string
  error: string | null
  startedAt: string
  finishedAt: string | null
}
export interface MessageAction {
  id: string
  eventId: string | null
  actorId: string
  action: string
  reason: string
  outcome: string
  createdAt: string
}
export interface MessageProjection {
  orderId: string
  businessVersion: string
  observedVersion: string | null
  sourceEventId: string | null
  snapshotJson: string | null
  updatedAt: string | null
}
export type ReplayAction = 'REPUBLISH' | 'RETRY_CONSUME'
type Page<T> = { list: T[]; total: number }
const root = '/fulfillment/message'
export const MessageApi = {
  page: (orderId: string, pageNo: number, status?: string): Promise<Page<MessageEvent>> =>
    request.get({ url: root + '/page', params: { orderId, pageNo, pageSize: 10, status } }),
  get: (orderId: string, eventId: string): Promise<MessageEvent> =>
    request.get({ url: root + '/get', params: { orderId, eventId } }),
  deliveries: (orderId: string, eventId: string, pageNo: number): Promise<Page<MessageDelivery>> =>
    request.get({ url: root + '/deliveries', params: { orderId, eventId, pageNo, pageSize: 10 } }),
  actions: (orderId: string, pageNo: number): Promise<Page<MessageAction>> =>
    request.get({ url: root + '/actions', params: { orderId, pageNo, pageSize: 10 } }),
  projection: (orderId: string): Promise<MessageProjection> =>
    request.get({ url: root + '/projection', params: { orderId } }),
  replay: (
    data: { orderId: string; eventId: string; action: ReplayAction; reason: string },
    key: string
  ) => request.post({ url: root + '/replay', data, headers: { 'Idempotency-Key': key } }),
  rebuild: (data: { orderId: string; reason: string }, key: string) =>
    request.post({ url: root + '/rebuild', data, headers: { 'Idempotency-Key': key } })
}
