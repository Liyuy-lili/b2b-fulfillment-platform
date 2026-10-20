import request from '@/config/axios'

export interface FulfillmentItem {
  id: string
  erpOrderItemId: string
  productId: string
  unitId: string
  price: string
  taxPercent: string
  taxPrice: string
  totalPrice: string
  orderedQty: string
  openQty: string
  reservedQty: string
  shippedQty: string
  cancelledQty: string
  returnedQty: string
}
export interface FulfillmentOrder {
  id: string
  erpOrderId: string
  orderNo: string
  customerId: string
  ownerUserId: string
  status: string
  allocationAttempted: boolean
  totalPrice: string
  discountPercent: string
  discountPrice: string
  depositPrice: string
  createTime: string
  items: FulfillmentItem[]
}
export interface Reservation {
  id: string
  orderItemId: string
  productId: string
  warehouseId: string
  allocatedQty: string
  heldQty: string
  consumedQty: string
  releasedQty: string
  expireAt: string
}
export interface AllocationInput {
  orderId: string
  strategy: string
  warehouseIds: string[]
  holdSeconds: number
}
export interface QuantityLine {
  id: string
  quantity: string
}
export interface Preview {
  strategy: string
  strategyVersion: number
  sufficient: boolean
  notice: string
  plan: { orderItemId: string; productId: string; warehouseId: string; quantity: string }[]
  stocks: {
    productId: string
    warehouseId: string
    physical: string
    reserved: string
    available: string
  }[]
}
export interface Shipment {
  id: string
  shipmentNo: string
  orderId: string
  warehouseId: string
  erpSaleOutId: string
  status: string
  carrierCode: string
  trackingNo: string
  shippedAt: string
  deliveredAt?: string
  items: {
    id: string
    orderItemId: string
    reservationId: string
    quantity: string
    erpSaleOutItemId: string
  }[]
  events: {
    eventId: string
    eventType: string
    outcome: string
    occurredAt: string
    receivedAt: string
    conflictCount: number
  }[]
}
export interface Cancellation {
  id: string
  orderItemId: string
  quantity: string
  reason: string
  createTime: string
}
export interface ReturnAllowance {
  shipmentItemId: string
  orderItemId: string
  shippedQty: string
  committedQty: string
  availableQty: string
}
export interface FulfillmentReturn {
  id: string
  returnNo: string
  orderId: string
  shipmentId: string
  warehouseId: string
  status: 'REQUESTED' | 'RECEIVED' | 'REJECTED'
  reason: string
  erpSaleReturnId?: string
  receivedAt?: string
  rejectedAt?: string
  rejectionReason?: string
  createTime: string
  items: {
    id: string
    shipmentItemId: string
    orderItemId: string
    quantity: string
    erpSaleReturnItemId?: string
    erpStockRecordId?: string
  }[]
}
const command = <T = any>(url: string, data: unknown, key: string): Promise<T> =>
  request.post({ url, data, headers: { 'Idempotency-Key': key } })
export const FulfillmentApi = {
  returnAllowance: (orderId: string, shipmentId: string): Promise<ReturnAllowance[]> =>
    request.get({ url: '/fulfillment/return/allowance', params: { orderId, shipmentId } }),
  returns: (
    orderId: string,
    pageNo = 1,
    pageSize = 10
  ): Promise<{ list: FulfillmentReturn[]; total: number }> =>
    request.get({ url: '/fulfillment/return/page', params: { orderId, pageNo, pageSize } }),
  createReturn: (
    data: { orderId: string; shipmentId: string; items: QuantityLine[]; reason: string },
    key: string
  ) => command('/fulfillment/return/create', data, key),
  receiveReturn: (data: { orderId: string; returnId: string }, key: string) =>
    command('/fulfillment/return/receive', data, key),
  rejectReturn: (data: { orderId: string; returnId: string; reason: string }, key: string) =>
    command('/fulfillment/return/reject', data, key),
  warehouses: (): Promise<{ id: string; name: string; priority: number }[]> =>
    request.get({ url: '/fulfillment/warehouses' }),
  preview: (data: AllocationInput): Promise<Preview> =>
    request.post({ url: '/fulfillment/order/preview', data }),
  allocate: (data: AllocationInput, key: string) =>
    command<{ outcome: string }>('/fulfillment/order/allocate', data, key),
  release: (
    data: { orderId: string; items: { reservationId: string; quantity: string }[]; reason: string },
    key: string
  ) => command('/fulfillment/order/release', data, key),
  cancel: (data: { orderId: string; items: QuantityLine[]; reason: string }, key: string) =>
    command('/fulfillment/order/cancel', data, key),
  ship: (
    data: {
      orderId: string
      warehouseId: string
      items: QuantityLine[]
      carrierCode: string
      trackingNo: string
    },
    key: string
  ) => command<{ shipmentNo: string }>('/fulfillment/shipment/confirm', data, key),
  reservations: (orderId: string): Promise<Reservation[]> =>
    request.get({ url: '/fulfillment/order/reservations', params: { orderId } }),
  shipments: (
    orderId: string,
    pageNo = 1,
    pageSize = 10
  ): Promise<{ list: Shipment[]; total: number }> =>
    request.get({ url: '/fulfillment/shipment/page', params: { orderId, pageNo, pageSize } }),
  cancellations: (orderId: string): Promise<Cancellation[]> =>
    request.get({ url: '/fulfillment/order/cancellations', params: { orderId } }),
  simulate: (shipmentId: string, eventType: string) =>
    request.post({ url: '/fulfillment/logistics/simulate', data: { shipmentId, eventType } }),
  page: (params: object): Promise<{ list: FulfillmentOrder[]; total: number }> =>
    request.get({ url: '/fulfillment/order/page', params }),
  get: (id: string): Promise<FulfillmentOrder> =>
    request.get({ url: '/fulfillment/order/get', params: { id } }),
  bind: (erpOrderId: string, key: string): Promise<{ orderId: string; status: string }> =>
    request.post({
      url: '/fulfillment/order/bind',
      data: { erpOrderId },
      headers: { 'Idempotency-Key': key }
    })
}
