<template>
  <Teleport to="body">
    <div v-if="detail" class="modal-backdrop" data-testid="cohort-detail-modal" @click.self="$emit('close')">
      <section class="modal cohort-modal" role="dialog" aria-modal="true">
      <header class="detail-head">
        <div>
          <h3>人群详情：{{ cohort.人群编码 }} · {{ cohort.人群名称 }}</h3>
          <p class="page-desc">共享申请、切片领用资格授予、归属核对和授权记录均由服务端裁决。</p>
        </div>
        <button class="btn" type="button" data-testid="close-cohort-detail" @click="$emit('close')">关闭</button>
      </header>

      <p v-if="message" class="form-message" :class="{ error: !lastOk }" data-testid="cohort-detail-message">{{ message }}</p>

      <section class="detail-block" data-testid="ownership-panel">
        <div class="block-head">
          <h4>授权人核对：包归属与接收者</h4>
          <button class="btn" type="button" data-testid="verify-ownership" @click="verifyOwnership">核对包归属和接收者</button>
        </div>
        <dl class="detail-grid">
          <div><dt>人群编码</dt><dd data-testid="ownership-cohort">{{ ownership.人群编码 }}</dd></div>
          <div><dt>包归属项目</dt><dd>{{ ownership.包归属项目 }}</dd></div>
          <div><dt>归属人</dt><dd>{{ ownership.归属人 }}</dd></div>
          <div><dt>包归属凭证</dt><dd>{{ ownership.包归属凭证 }}</dd></div>
          <div><dt>来源实验</dt><dd data-testid="ownership-experiment">{{ ownership.来源实验 }}</dd></div>
          <div><dt>成员总数</dt><dd data-testid="ownership-total">{{ ownership.人群规模 }}</dd></div>
        </dl>
      </section>

      <section class="detail-block">
        <div class="block-head">
          <h4>共享申请</h4>
          <button
            class="btn primary"
            type="button"
            data-testid="open-share-form"
            @click="showShare = !showShare"
          >
            {{ showShare ? '收起共享表单' : '共享申请' }}
          </button>
        </div>
        <form v-if="showShare" class="inline-form" data-testid="share-form" @submit.prevent="submitShare">
          <label><span>接收者</span><input v-model="shareForm.接收者" data-testid="share-receiver" placeholder="例如：甲" /></label>
          <label><span>接收项目</span><input v-model="shareForm.接收项目" data-testid="share-project" placeholder="另一个项目名称" /></label>
          <label class="wide"><span>申请范围</span><input v-model="shareForm.申请范围" data-testid="share-scope" /></label>
          <label class="wide"><span>申请事由</span><input v-model="shareForm.申请事由" data-testid="share-reason" /></label>
          <button class="btn primary" type="submit" data-testid="submit-share">提交申请</button>
        </form>
        <table class="mini-table">
          <thead><tr><th>申请单号</th><th>接收者</th><th>接收项目</th><th>状态</th><th>范围/事由</th></tr></thead>
          <tbody>
            <tr v-for="item in detail.share_requests" :key="item.request_no">
              <td>{{ item.request_no }}</td><td>{{ item.接收者 }}</td><td>{{ item.接收项目 }}</td>
              <td>{{ item.status }}</td><td>{{ item.申请范围 }}<br />{{ item.申请事由 }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="detail-block">
        <div class="block-head">
          <h4>切片领用资格与授权记录</h4>
          <button
            class="btn primary"
            type="button"
            data-testid="open-grant-form"
            @click="showGrant = !showGrant"
          >
            {{ showGrant ? '收起授权表单' : '授予切片领用资格' }}
          </button>
        </div>
        <form v-if="showGrant" class="inline-form" data-testid="grant-form" @submit.prevent="submitGrant">
          <label><span>接收者</span><input v-model="grantForm.接收者" data-testid="grant-receiver" /></label>
          <label><span>接收项目</span><input v-model="grantForm.接收项目" data-testid="grant-project" /></label>
          <label class="wide"><span>授权范围</span><input v-model="grantForm.授权范围" data-testid="grant-scope" /></label>
          <button class="btn primary" type="submit" data-testid="submit-grant">确认授予</button>
        </form>

        <article
          v-for="grant in detail.grants"
          :key="grant.grant_no"
          class="grant-card"
          :data-testid="`grant-card-${grant.grant_no}`"
          :data-status="grant.status"
        >
          <div class="grant-head">
            <strong data-testid="grant-no">{{ grant.grant_no }}</strong>
            <span class="badge" :class="grant.status === '有效' ? 'ok' : 'revoked'">{{ grant.status }} · v{{ grant.version }}</span>
          </div>
          <dl class="detail-grid">
            <div><dt>包归属</dt><dd>{{ grant.归属项目 }} / {{ grant.归属人 }}</dd></div>
            <div><dt>接收者</dt><dd data-testid="grant-receiver-value">{{ grant.接收者 }}（{{ grant.接收项目 }}）</dd></div>
            <div class="wide"><dt>允许计算范围</dt><dd data-testid="grant-scope-text">{{ grant.授权范围 }}</dd></div>
            <div v-if="grant.revoked_at" class="wide"><dt>撤回时间/原因</dt><dd>{{ grant.revoked_at }} {{ grant.revoke_reason }}</dd></div>
          </dl>
          <div class="button-row">
            <button class="btn primary" type="button" :data-testid="`open-slice-${grant.grant_no}`" @click="openSlice(grant.grant_no, String(grant.接收者 || ''))">
              从授权记录打开切片
            </button>
            <button class="btn" type="button" :data-testid="`revoke-${grant.grant_no}`" @click="revoke(grant.grant_no)">
              撤回授权
            </button>
          </div>
        </article>
      </section>

      <section class="detail-block">
        <h4>授权范围内成员（{{ detail.members.length }}）</h4>
        <p class="hint">服务端只返回 C10/EXP-C10 成员；另一实验的同名用户不会出现在这里。</p>
        <table class="mini-table" data-testid="cohort-members-table">
          <thead><tr><th>稳定成员键</th><th>实验</th><th>用户标识</th><th>姓名</th><th>分组</th><th>指标值</th></tr></thead>
          <tbody>
            <tr v-for="m in detail.members" :key="m.member_key" :data-testid="`cohort-member-${m.用户标识}`">
              <td>{{ m.member_key }}</td><td>{{ m.实验编码 }}</td><td>{{ m.用户标识 }}</td>
              <td>{{ m.用户姓名 }}</td><td>{{ m.分组名称 }}</td><td>{{ m.指标值 }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="detail.audit_events?.length" class="detail-block">
        <h4>授权与领用审计</h4>
        <ul class="audit-list" data-testid="cohort-audit-list">
          <li v-for="event in detail.audit_events" :key="event.id">
            <time>{{ event.at }}</time> <strong>{{ event.type }}</strong> {{ event.message }}
          </li>
        </ul>
      </section>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { runAction as runResourceAction } from '@/api/backend-service'
import {
  createShareRequest,
  getCohortControlledDetail,
  grantSliceEligibility,
  revokeGrant,
  type ControlledRecord,
  type ControlledResult,
} from '@/api/controlledSlice'

const props = defineProps<{ cohortId: number; initialPanel?: 'share' | 'grant' | null }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const router = useRouter()

const detail = ref<ControlledResult | null>(null)
const message = ref('')
const lastOk = ref(true)
const showShare = ref(false)
const showGrant = ref(false)
const shareForm = reactive({ 接收者: '', 接收项目: '', 申请范围: '仅 C10 授权成员的受控切片组内差异计算', 申请事由: '' })
const grantForm = reactive({
  接收者: '甲',
  接收项目: '跨境增长分析项目',
  授权范围: '实验 EXP-C10；仅 C10 快照成员；允许组内差异计算；禁止跨实验、同姓名扩圈和筛选扩权',
})

const cohort = computed<ControlledRecord>(() => detail.value?.cohort ?? {})
const ownership = computed<ControlledRecord>(() => detail.value?.ownership_check ?? {})

async function reload() {
  const result = await getCohortControlledDetail(props.cohortId)
  if (!result.ok) {
    message.value = result.message
    lastOk.value = false
    return
  }
  detail.value = result
}

function notify(result: ControlledResult) {
  message.value = result.message
  lastOk.value = result.ok
}

async function verifyOwnership() {
  const result = await runResourceAction('cohort_builder', props.cohortId, '核对包归属')
  notify(result)
  if (result.ok) await reload()
}

async function submitShare() {
  const result = await createShareRequest(String(cohort.value.人群编码 ?? ''), { ...shareForm })
  notify(result)
  if (result.ok) {
    showShare.value = false
    emit('changed')
    await reload()
  }
}

async function submitGrant() {
  const result = await grantSliceEligibility(String(cohort.value.人群编码 ?? ''), { ...grantForm })
  notify(result)
  if (result.ok) {
    showGrant.value = false
    emit('changed')
    await reload()
  }
}

async function revoke(grantNo: string) {
  const result = await revokeGrant(grantNo, '授权人在人群详情中撤回')
  notify(result)
  emit('changed')
  await reload()
}

function openSlice(grantNo: string, recipientName = '') {
  void router.push({ path: '/segment_slice', query: { grant: grantNo, recipient: recipientName } })
}

onMounted(async () => {
  showShare.value = props.initialPanel === 'share'
  showGrant.value = props.initialPanel === 'grant'
  await reload()
})
</script>

<style scoped>
.cohort-modal { width: min(980px, 100%); }
.detail-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.detail-block { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }
.block-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; margin: 8px 0; }
.detail-grid > div { min-width: 0; }
.detail-grid .wide { grid-column: 1 / -1; }
.detail-grid dt { font-size: 12px; color: var(--muted); }
.detail-grid dd { margin: 2px 0 0; font-size: 13px; word-break: break-all; }
.inline-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin: 10px 0; }
.inline-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.inline-form .wide { grid-column: 1 / -1; }
.inline-form input { border: 1px solid var(--border); border-radius: 6px; padding: 8px; color: #1f2937; }
.inline-form button { align-self: end; }
.mini-table { width: 100%; border-collapse: collapse; margin-top: 8px; background: #fff; }
.mini-table th, .mini-table td { border: 1px solid var(--border); padding: 6px 8px; font-size: 12px; text-align: left; vertical-align: top; }
.grant-card { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-top: 10px; background: #fff; }
.grant-card[data-status='已撤回'] { background: #fff7f7; border-color: #fecdca; }
.grant-head { display: flex; justify-content: space-between; align-items: center; }
.badge { border-radius: 999px; padding: 2px 8px; font-size: 12px; }
.badge.ok { background: #dcfce7; color: #166534; }
.badge.revoked { background: #fee4e2; color: #b42318; }
.button-row { display: flex; gap: 8px; flex-wrap: wrap; }
.hint { font-size: 12px; color: var(--muted); }
.form-message { padding: 8px 10px; border-radius: 6px; background: #ecfdf3; color: #027a48; font-size: 13px; }
.form-message.error { background: #fef3f2; color: #b42318; }
.audit-list { margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.7; }
@media (max-width: 720px) { .detail-grid, .inline-form { grid-template-columns: 1fr; } }
</style>
