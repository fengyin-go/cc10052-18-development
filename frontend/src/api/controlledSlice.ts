import { request } from './client'

export type ControlledRecord = Record<string, any>

export type ControlledResult = {
  ok: boolean
  message: string
  [key: string]: any
}

async function postJson(path: string, body: ControlledRecord = {}): Promise<ControlledResult> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return (await response.json()) as ControlledResult
}

async function getJson(path: string): Promise<ControlledResult> {
  const response = await request(path)
  return (await response.json()) as ControlledResult
}

export function getCohortControlledDetail(id: number | string): Promise<ControlledResult> {
  return getJson(`/api/cohort_builder/${id}/detail`)
}

export function createShareRequest(code: string, values: ControlledRecord): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/cohorts/${encodeURIComponent(code)}/share-requests`, values)
}

export function grantSliceEligibility(code: string, values: ControlledRecord): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/cohorts/${encodeURIComponent(code)}/grants`, values)
}

export function listGrants(recipient = ''): Promise<ControlledResult> {
  const query = recipient ? `?recipient=${encodeURIComponent(recipient)}` : ''
  return getJson(`/api/controlled-slices/grants${query}`)
}

export function getGrantContext(grantNo: string, recipient = ''): Promise<ControlledResult> {
  const query = recipient ? `?recipient=${encodeURIComponent(recipient)}` : ''
  return getJson(`/api/controlled-slices/grants/${encodeURIComponent(grantNo)}${query}`)
}

export function revokeGrant(grantNo: string, reason = ''): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/grants/${encodeURIComponent(grantNo)}/revoke`, { reason })
}

export function claimTicket(grantNo: string, values: ControlledRecord = {}): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/grants/${encodeURIComponent(grantNo)}/tickets`, values)
}

export function getTicket(ticketNo: string): Promise<ControlledResult> {
  return getJson(`/api/controlled-slices/tickets/${encodeURIComponent(ticketNo)}`)
}

export function getTicketMembers(ticketNo: string, keyword = ''): Promise<ControlledResult> {
  const query = keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''
  return getJson(`/api/controlled-slices/tickets/${encodeURIComponent(ticketNo)}/members${query}`)
}

export function continueTicket(ticketNo: string, values: ControlledRecord = { auto_compute: true }): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/tickets/${encodeURIComponent(ticketNo)}/continue`, values)
}

export function terminateTicket(ticketNo: string, reason = ''): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/tickets/${encodeURIComponent(ticketNo)}/terminate`, { reason })
}

export function computeTicket(ticketNo: string, use = 'delivered'): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/tickets/${encodeURIComponent(ticketNo)}/compute`, { use })
}

export function getCredential(credentialNo: string): Promise<ControlledResult> {
  return getJson(`/api/controlled-slices/credentials/${encodeURIComponent(credentialNo)}`)
}

export function recomputeCredential(credentialNo: string): Promise<ControlledResult> {
  return postJson(`/api/controlled-slices/credentials/${encodeURIComponent(credentialNo)}/recompute`)
}
