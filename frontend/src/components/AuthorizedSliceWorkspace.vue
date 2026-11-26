<template>
  <section class="controlled-panel" data-testid="authorized-slice-panel">
    <header class="panel-head">
      <div>
        <h3>授权切片工作台</h3>
        <p class="hint">接收者从授权记录进入；服务端按授权范围和密封快照取数，页面筛选不能扩权。</p>
      </div>
      <div class="grant-open-form">
        <label><span>授权凭证</span><input v-model="grantNo" data-testid="grant-no-input" /></label>
        <label><span>接收者</span><input v-model="recipient" data-testid="recipient-input" /></label>
        <button class="btn primary" type="button" data-testid="open-grant-record" @click="openGrant">从授权记录打开切片</button>
      </div>
    </header>

    <section class="grant-records" data-testid="grant-records">
      <h4>可打开的授权记录</h4>
      <table class="mini-table">
        <thead><tr><th>授权凭证</th><th>人群包</th><th>包归属</th><th>接收者</th><th>允许范围</th><th>状态</th><th>打开切片</th></tr></thead>
        <tbody>
          <tr v-for="grant in grants" :key="grant.grant_no" :data-testid="`grant-record-row-${grant.grant_no}`">
            <td>{{ grant.grant_no }}</td>
            <td>{{ grant.人群编码 }}</td>
            <td>{{ grant.归属项目 }}</td>
            <td>{{ grant.接收者 }}（{{ grant.接收项目 }}）</td>
            <td>{{ grant.授权范围 }}</td>
            <td>{{ grant.status }} · v{{ grant.version }}</td>
            <td>
              <button
                class="link"
                type="button"
                :data-testid="`open-grant-${grant.grant_no}`"
                @click="chooseGrant(grant)"
              >
                从授权记录打开切片
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <p v-if="pageMessage" class="form-message" :class="{ error: !messageOk }" data-testid="slice-page-message">{{ pageMessage }}</p>

    <article v-if="deniedSlice" class="denied-card" data-testid="denied-slice-result">
      <strong>新切片取数已被服务端拒绝</strong>
      <p>批次：{{ deniedSlice.切片批次 }}；状态：{{ deniedSlice.status }}；实际成员数：
        <span data-testid="denied-actual-count">{{ deniedSlice.实际成员数 ?? 0 }}</span>
      </p>
      <p>{{ deniedSlice.失败原因 || pageMessage }}</p>
    </article>

    <template v-if="context?.ok">
      <div class="scope-card" data-testid="grant-context" :data-status="context.grant.status">
        <div class="scope-title">
          <strong>{{ context.grant.grant_no }}</strong>
          <span class="badge" :class="context.grant.status === '有效' ? 'ok' : 'revoked'">
            {{ context.grant.status }} · v{{ context.grant.version }}
          </span>
        </div>
        <dl class="detail-grid">
          <div><dt>包归属</dt><dd data-testid="scope-owner">{{ context.grant.归属项目 }} / {{ context.grant.归属人 }}（{{ context.grant.包归属凭证 }}）</dd></div>
          <div><dt>接收者</dt><dd data-testid="scope-recipient">{{ context.grant.接收者 }} / {{ context.grant.接收项目 }}</dd></div>
          <div class="wide"><dt>允许计算范围</dt><dd data-testid="grant-scope">{{ context.scope_text }}<br /><span class="hint">接收者可从授权记录和本面板知道哪些范围允许计算；任何页面筛选都不能越过该范围。</span></dd></div>
        </dl>
        <div class="button-row">
          <button class="btn primary" type="button" data-testid="new-slice" @click="createAnotherSlice">发起另一条切片</button>
          <button class="btn" type="button" data-testid="refresh-ticket" @click="selectTicket(selectedTicketNo)">刷新领用结果</button>
        </div>
      </div>

      <div v-if="context.tickets?.length" class="ticket-picker" data-testid="ticket-picker">
        <button
          v-for="ticket in context.tickets"
          :key="ticket.ticket_no"
          type="button"
          class="ticket-chip"
          :class="{ active: ticket.ticket_no === selectedTicketNo }"
          :data-testid="`pick-ticket-${ticket.ticket_no}`"
          @click="selectTicket(ticket.ticket_no)"
        >
          {{ ticket.ticket_no }} · {{ ticket.status }} · {{ ticket.read_count }}/{{ ticket.snapshot_total }}
        </button>
      </div>

      <article v-if="ticket" class="ticket-card" data-testid="ticket-receipt" :data-status="ticket.status">
        <div class="ticket-head">
          <h4>{{ ticket.ticket_no }}</h4>
          <span class="badge" :class="ticket.status === '已完成' ? 'ok' : ticket.status === '已终止' ? 'revoked' : 'running'">
            {{ ticket.status }}
          </span>
        </div>
        <div class="receipt-grid">
          <div><span>授权记录</span><strong>{{ ticket.grant_no }}（领取时 v{{ ticket.grant_version_at_claim }}，当前 {{ ticket.grant_status }} v{{ ticket.current_grant_version }}）</strong></div>
          <div><span>成员快照</span><strong data-testid="ticket-snapshot">{{ ticket.snapshot_no }} / {{ ticket.snapshot_hash }}</strong></div>
          <div><span>领用进度</span><strong data-testid="ticket-progress">{{ ticket.read_count }}/{{ ticket.snapshot_total }}，checkpoint={{ ticket.checkpoint_cursor }}，剩余 {{ ticket.remaining_count }}</strong></div>
          <div><span>本次计算截止位置</span><strong data-testid="compute-checkpoint">checkpoint={{ ticket.checkpoint_cursor }}；实际快照 {{ ticket.actual_member_count || 0 }} 人；hash={{ ticket.computed_hash || '未冻结' }}</strong></div>
          <div><span>实际计算成员数</span><strong data-testid="actual-member-count">{{ ticket.actual_member_count || 0 }}</strong></div>
        </div>

        <div class="button-row">
          <button
            class="btn primary"
            type="button"
            data-testid="continue-members"
            :disabled="busy || ['已完成', '已终止'].includes(ticket.status)"
            @click="continueRemaining"
          >
            继续领取 C10 的剩余成员
          </button>
          <button
            class="btn primary"
            type="button"
            data-testid="compute-ticket"
            :disabled="busy || ticket.status === '已终止'"
            @click="computeCurrent"
          >
            开始计算当前工单
          </button>
          <button
            class="btn"
            type="button"
            data-testid="terminate-ticket"
            :disabled="busy || ['已完成', '已终止'].includes(ticket.status)"
            @click="terminateCurrent"
          >
            终止工单
          </button>
        </div>

        <div v-if="ticket.conflict_basis && !ticket.completion_basis && !ticket.termination_basis" class="basis conflict-basis" data-testid="conflict-basis">
          <strong>撤回/计算冲突依据：</strong>{{ ticket.conflict_basis }}
        </div>
        <div v-if="ticket.completion_basis" class="basis ok-basis" data-testid="completion-basis">
          <strong>完成依据：</strong>{{ ticket.completion_basis }}
        </div>
        <div v-if="ticket.termination_basis" class="basis stop-basis" data-testid="termination-basis">
          <strong>终止依据：</strong>{{ ticket.termination_basis }}
        </div>

        <div v-if="ticket.stats || lastStats" class="stats-detail" data-testid="slice-stats">
          <h5>切片统计明细</h5>
          <p data-testid="stats-scope"><strong>授权范围：</strong>{{ ticket.授权范围 }}</p>
          <p><strong>实际成员数：</strong><span data-testid="stats-actual-count">{{ (ticket.stats || lastStats).实际成员数 }}</span></p>
          <div class="stat-pills">
            <span>对照组 {{ (ticket.stats || lastStats).对照组人数 }} 人 / 均值 {{ (ticket.stats || lastStats).对照组均值 }}</span>
            <span>实验组 {{ (ticket.stats || lastStats).实验组人数 }} 人 / 均值 {{ (ticket.stats || lastStats).实验组均值 }}</span>
            <span>均值差异 {{ (ticket.stats || lastStats).均值差异 }}</span>
            <span>组内方差 {{ (ticket.stats || lastStats).组内方差 }}</span>
          </div>
          <p class="mono">{{ (ticket.stats || lastStats).分组差异 }}</p>
          <details class="diff-details">
            <summary>查看组内成员差异明细</summary>
            <div class="diff-grid">
              <table v-for="groupName in ['对照组明细', '实验组明细']" :key="groupName" class="mini-table">
                <thead><tr><th colspan="4">{{ groupName }}</th></tr><tr><th>用户</th><th>指标值</th><th>均值差</th><th>差异平方</th></tr></thead>
                <tbody>
                  <tr v-for="item in (ticket.stats || lastStats)[groupName]" :key="`${groupName}-${item.实验编码}-${item.用户标识}`">
                    <td>{{ item.用户姓名 }}（{{ item.用户标识 }}）</td><td>{{ item.指标值 }}</td><td>{{ item.与组均值差 }}</td><td>{{ item.差异平方 }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </div>

        <h5>授权切片样本与领用成员</h5>
        <p class="hint">下表只展示授权快照内已领取/可复查的样本成员，服务端按稳定成员键和实验编码隔离同名用户。</p>
        <div class="member-toolbar">
          <label><span>页面内姓名/标识筛选（不会扩大服务端范围）</span>
            <input v-model="memberFilter" data-testid="member-filter" placeholder="例如：王敏" @keyup.enter="filterMembers" />
          </label>
          <button class="btn" type="button" data-testid="filter-members" @click="filterMembers">筛选授权成员</button>
          <button class="btn ghost" type="button" data-testid="clear-member-filter" @click="clearFilter">清空</button>
        </div>
        <table class="mini-table" data-testid="authorized-members-table">
          <thead><tr><th>稳定成员键</th><th>实验编码</th><th>用户标识</th><th>姓名</th><th>分组</th><th>指标值</th></tr></thead>
          <tbody>
            <tr v-for="member in members" :key="member.member_key" :data-testid="`authorized-member-${member.用户标识}`">
              <td>{{ member.member_key }}</td><td>{{ member.实验编码 }}</td><td>{{ member.用户标识 }}</td>
              <td>{{ member.用户姓名 }}</td><td>{{ member.分组名称 }}</td><td>{{ member.指标值 }}</td>
            </tr>
            <tr v-if="!members.length"><td colspan="6" class="empty-state">当前没有已领取且在授权快照内的成员</td></tr>
          </tbody>
        </table>
      </article>
    </template>

    <section v-if="context?.audit_events?.length" class="audit-panel" data-testid="slice-audit-list">
      <h4>授权 / 领用 / 计算审计</h4>
      <ul>
        <li v-for="event in context.audit_events" :key="event.id">
          <time>{{ event.at }}</time> <strong>{{ event.type }}</strong> {{ event.message }}
        </li>
      </ul>
    </section>

    <section class="credential-panel" data-testid="credential-panel">
      <h4>历史凭证复查</h4>
      <div class="credential-form">
        <label><span>历史凭证</span><input v-model="credentialNo" data-testid="credential-input" /></label>
        <button class="btn" type="button" data-testid="review-credential" @click="reviewCredential">历史凭证复查</button>
        <button class="btn primary" type="button" data-testid="recompute-credential" @click="recomputeCredential">按原成员数复算</button>
      </div>
      <div v-if="credential" class="credential-result" data-testid="credential-result" :data-consistent="credentialResult?.consistent ?? ''">
        <p><strong>{{ credential.slice_row?.切片批次 }}</strong> · {{ credential.slice_row?.status }}</p>
        <p data-testid="credential-scope"><strong>授权范围：</strong>{{ credential.scope_text }}</p>
        <p class="mono">{{ credential.slice_row?.分组差异 }}</p>
        <p>凭证指向快照 {{ credential.snapshot?.snapshot_no }} / {{ credential.snapshot?.member_hash }}；
          <strong>实际成员数：</strong><span data-testid="credential-actual-count">{{ credential.slice_row?.实际成员数 }}</span>；
          原始成员数 <span data-testid="original-member-count">{{ credential.original_member_count }}</span>
        </p>
        <template v-if="credentialResult">
          <p data-testid="recompute-message">{{ credentialResult.message }}</p>
          <p><strong>复算成员数：</strong><span data-testid="recomputed-member-count">{{ credentialResult.recomputed_member_count }}</span>；
            一致性：<span data-testid="credential-consistent">{{ credentialResult.consistent ? 'true' : 'false' }}</span></p>
          <div v-if="credentialResult.stats" class="stat-pills">
            <span>实际 {{ credentialResult.stats.实际成员数 }} 人</span>
            <span>均值差 {{ credentialResult.stats.均值差异 }}</span>
            <span>组内方差 {{ credentialResult.stats.组内方差 }}</span>
          </div>
        </template>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  claimTicket,
  computeTicket,
  continueTicket,
  getCredential,
  getGrantContext,
  getTicket,
  getTicketMembers,
  listGrants,
  recomputeCredential as recomputeCredentialApi,
  terminateTicket,
  type ControlledRecord,
  type ControlledResult,
} from '@/api/controlledSlice'

const emit = defineEmits<{ changed: [] }>()
const route = useRoute()
const queryGrant = Array.isArray(route.query.grant) ? route.query.grant[0] : route.query.grant
const queryRecipient = Array.isArray(route.query.recipient) ? route.query.recipient[0] : route.query.recipient
const queryCredential = Array.isArray(route.query.credential) ? route.query.credential[0] : route.query.credential

const grantNo = ref(String(queryGrant ?? 'GRANT-C10-JIA'))
const recipient = ref(String(queryRecipient ?? '甲'))
const credentialNo = ref(String(queryCredential ?? 'CRED-C10-HIST-001'))
const context = ref<ControlledResult | null>(null)
const grants = ref<ControlledRecord[]>([])
const ticket = ref<ControlledRecord | null>(null)
const members = ref<ControlledRecord[]>([])
const selectedTicketNo = ref('TKT-C10-JIA-001')
const memberFilter = ref('')
const credential = ref<ControlledResult | null>(null)
const credentialResult = ref<ControlledResult | null>(null)
const pageMessage = ref('')
const messageOk = ref(true)
const busy = ref(false)
const lastStats = ref<ControlledRecord | null>(null)
const deniedSlice = ref<ControlledRecord | null>(null)

function showMessage(result: ControlledResult) {
  pageMessage.value = result.message
  messageOk.value = result.ok
}

async function chooseGrant(grant: ControlledRecord) {
  grantNo.value = String(grant.grant_no ?? '')
  recipient.value = String(grant.接收者 ?? recipient.value)
  await openGrant()
}

async function openGrant() {
  busy.value = true
  try {
    const result = await getGrantContext(grantNo.value.trim(), recipient.value.trim())
    context.value = result
    showMessage(result)
    if (!result.ok) return
    const tickets = result.tickets ?? []
    const preferred = tickets.find((item: ControlledRecord) => item.ticket_no === selectedTicketNo.value) ?? tickets[0]
    if (preferred?.ticket_no) await selectTicket(String(preferred.ticket_no))
  } finally {
    busy.value = false
  }
}

async function refreshContext() {
  const result = await getGrantContext(grantNo.value.trim(), recipient.value.trim())
  if (result.ok) context.value = result
}

async function selectTicket(ticketNo: string) {
  if (!ticketNo) return
  selectedTicketNo.value = ticketNo
  const result = await getTicket(ticketNo)
  if (result.ok) {
    ticket.value = result.ticket
    lastStats.value = result.ticket?.stats ?? null
    await loadMembers()
  } else {
    showMessage(result)
  }
}

async function loadMembers() {
  const result = await getTicketMembers(selectedTicketNo.value, memberFilter.value.trim())
  if (result.ok) members.value = result.members ?? []
}

async function filterMembers() {
  await loadMembers()
}

async function clearFilter() {
  memberFilter.value = ''
  await loadMembers()
}

async function continueRemaining() {
  busy.value = true
  try {
    const result = await continueTicket(selectedTicketNo.value)
    showMessage(result)
    if (result.ok) {
      await selectTicket(selectedTicketNo.value)
      await refreshContext()
      emit('changed')
    }
  } finally {
    busy.value = false
  }
}

async function createAnotherSlice() {
  busy.value = true
  try {
    const result = await claimTicket(grantNo.value.trim(), { recipient: recipient.value.trim() })
    showMessage(result)
    deniedSlice.value = result.ok ? null : (result.slice_row ?? result)
    emit('changed')
    if (result.ok && result.ticket?.ticket_no) {
      context.value = await getGrantContext(grantNo.value.trim(), recipient.value.trim())
      await selectTicket(String(result.ticket.ticket_no))
    }
  } finally {
    busy.value = false
  }
}

async function computeCurrent() {
  busy.value = true
  try {
    const result = await computeTicket(selectedTicketNo.value)
    showMessage(result)
    if (result.ok) {
      lastStats.value = result.stats ?? null
      await selectTicket(selectedTicketNo.value)
      await refreshContext()
      emit('changed')
    }
  } finally {
    busy.value = false
  }
}

async function terminateCurrent() {
  busy.value = true
  try {
    const result = await terminateTicket(selectedTicketNo.value, '页面确认终止冲突工单')
    showMessage(result)
    if (result.ok) {
      await selectTicket(selectedTicketNo.value)
      await refreshContext()
      emit('changed')
    }
  } finally {
    busy.value = false
  }
}

async function reviewCredential() {
  credentialResult.value = null
  const result = await getCredential(credentialNo.value.trim())
  credential.value = result
  showMessage(result)
}

async function recomputeCredential() {
  const result = await recomputeCredentialApi(credentialNo.value.trim())
  credentialResult.value = result
  showMessage(result)
  if (result.ok) await reviewCredential()
}

onMounted(async () => {
  const grantList = await listGrants()
  if (grantList.ok) grants.value = grantList.items ?? []
  await openGrant()
  await reviewCredential()
})
</script>

<style scoped>
.controlled-panel { background: #fff; border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin: 12px 0 16px; }
.panel-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.panel-head h3, .credential-panel h4 { margin: 0 0 4px; }
.hint { color: var(--muted); font-size: 12px; margin: 0; }
.grant-records { margin: 12px 0; }
.grant-records h4 { margin: 0 0 6px; }
.grant-open-form, .credential-form { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.grant-open-form label, .credential-form label, .member-toolbar label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.grant-open-form input, .credential-form input, .member-toolbar input { border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; min-width: 220px; }
.form-message { padding: 8px 10px; border-radius: 6px; background: #ecfdf3; color: #027a48; font-size: 13px; margin: 10px 0; }
.form-message.error { background: #fef3f2; color: #b42318; }
.denied-card { border: 1px solid #fda29b; background: #fef3f2; color: #912018; border-radius: 8px; padding: 10px 12px; margin: 10px 0; font-size: 13px; }
.denied-card p { margin: 4px 0 0; }
.scope-card, .ticket-card, .credential-result { border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-top: 10px; background: #fcfcfd; }
.scope-card[data-status='已撤回'] { border-color: #fecdca; background: #fff7f7; }
.scope-title, .ticket-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.scope-title strong, .ticket-head h4 { margin: 0; }
.badge { border-radius: 999px; padding: 2px 8px; font-size: 12px; white-space: nowrap; }
.badge.ok { background: #dcfce7; color: #166534; }
.badge.revoked { background: #fee4e2; color: #b42318; }
.badge.running { background: #dbeafe; color: #1e40af; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; }
.detail-grid .wide { grid-column: 1 / -1; }
.detail-grid dt, .receipt-grid span { font-size: 12px; color: var(--muted); }
.detail-grid dd { margin: 2px 0 0; font-size: 13px; }
.button-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0; }
.ticket-picker { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.ticket-chip { border: 1px solid var(--border); background: #fff; border-radius: 999px; padding: 5px 10px; font-size: 12px; cursor: pointer; }
.ticket-chip.active { border-color: var(--brand); color: var(--brand); background: #eff6ff; }
.receipt-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; margin: 8px 0; }
.receipt-grid div { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.basis { border-radius: 6px; padding: 8px 10px; font-size: 12px; line-height: 1.6; margin: 8px 0; }
.ok-basis { background: #ecfdf3; color: #05603a; }
.conflict-basis { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }
.stop-basis { background: #fef3f2; color: #b42318; }
.stats-detail { border-top: 1px dashed var(--border); padding-top: 10px; margin-top: 10px; }
.stats-detail p { font-size: 13px; margin: 6px 0; }
.stat-pills { display: flex; gap: 8px; flex-wrap: wrap; }
.stat-pills span { background: #eff6ff; color: #1d4ed8; border-radius: 999px; padding: 4px 9px; font-size: 12px; }
.diff-details { margin-top: 10px; }
.diff-details summary { cursor: pointer; font-size: 13px; color: var(--brand); }
.diff-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }
.diff-grid .mini-table th[colspan='4'] { background: #f8fafc; }
.member-toolbar { display: flex; gap: 8px; align-items: flex-end; margin: 12px 0 8px; flex-wrap: wrap; }
.mini-table { width: 100%; border-collapse: collapse; background: #fff; }
.mini-table th, .mini-table td { border: 1px solid var(--border); padding: 6px 8px; font-size: 12px; text-align: left; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.credential-panel { border-top: 1px solid var(--border); margin-top: 14px; padding-top: 12px; }
.audit-panel { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 10px; }
.audit-panel h4 { margin: 0 0 6px; }
.audit-panel ul { margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.7; max-height: 180px; overflow: auto; }
@media (max-width: 820px) { .detail-grid, .receipt-grid, .diff-grid { grid-template-columns: 1fr; } .grant-open-form, .credential-form { width: 100%; } .grant-open-form label, .credential-form label { flex: 1; } }
</style>
