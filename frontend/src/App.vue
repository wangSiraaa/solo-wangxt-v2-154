<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, KIND_LABELS } from './api.js'
import WitnessPanel from './components/WitnessPanel.vue'
import CollationGrid from './components/CollationGrid.vue'
import JudgmentPanel from './components/JudgmentPanel.vue'

const health = ref(null)
const passages = ref([])
const currentPassage = ref(null)
const witnesses = ref([])
const rules = ref([])

const includePunct = ref(false)
const useCollatex = ref(true)
const run = ref(null)
const runHistory = ref([])
const selected = ref(null)
const previews = ref({})
const message = reactive({ kind: '', text: '' })

// 新增見本表單
const form = reactive({ siglum: '', source: '', era: '', raw: '' })
const formPreview = ref([])
// 規則表單
const ruleForm = reactive({ pattern: '', replacement: '', note: '' })

const markerLabel = {
  lacuna: '缺葉', blank: '空白正文', annotation: '批注', insertion: '插入',
}

onMounted(async () => {
  health.value = await api.health()
  passages.value = await api.passages()
  if (passages.value.length) await selectPassage(passages.value[0].id)
})

async function selectPassage(id) {
  const p = await api.passage(id)
  currentPassage.value = p
  witnesses.value = p.witnesses
  rules.value = await api.rules(id)
  runHistory.value = await api.runs(id)
  run.value = runHistory.value[0] || null
  selected.value = null
  await refreshPreviews()
}

async function refreshPreviews() {
  const out = {}
  for (const w of witnesses.value) {
    try {
      const r = await api.preview(w.raw_transcription, currentPassage.value.id)
      out[w.id] = r.tokens
    } catch (_) { /* 容錯：退回原文 */ }
  }
  previews.value = out
}

function flash(kind, text) {
  message.kind = kind
  message.text = text
  setTimeout(() => (message.text = ''), 4000)
}

async function previewForm() {
  if (!form.raw) { formPreview.value = []; return }
  const r = await api.preview(form.raw, currentPassage.value?.id)
  formPreview.value = r.tokens
}

async function addWitness() {
  if (!form.siglum || !form.raw) return flash('error', '請填寫簡稱與原轉錄')
  await api.addWitness(currentPassage.value.id, {
    siglum: form.siglum, source: form.source, era: form.era,
    raw_transcription: form.raw, sort_order: witnesses.value.length,
  })
  form.siglum = form.source = form.era = form.raw = ''
  formPreview.value = []
  await selectPassage(currentPassage.value.id)
  flash('ok', '見本已建立；原轉錄與比對形分欄保存')
}

async function addRule() {
  if (!ruleForm.pattern) return
  await api.addRule(currentPassage.value.id, {
    pattern: ruleForm.pattern, replacement: ruleForm.replacement,
    note: ruleForm.note,
  })
  ruleForm.pattern = ruleForm.replacement = ruleForm.note = ''
  await selectPassage(currentPassage.value.id)
  await refreshPreviews()
  flash('ok', '規則已套用；只改比對形，原字形不變')
}

async function collate() {
  run.value = await api.collate({
    passage_id: currentPassage.value.id,
    include_punctuation: includePunct.value,
    use_collatex: useCollatex.value,
  })
  runHistory.value = await api.runs(currentPassage.value.id)
  selected.value = null
  flash('ok', `對齊完成（引擎：${run.value.engine}）`)
}

async function judge(payload) {
  try {
    await api.judge(run.value.id, payload)
    run.value = await api.run(run.value.id)
    runHistory.value = await api.runs(currentPassage.value.id)
    flash('ok', '人工判斷已保存（與系統建議分開）')
  } catch (e) { flash('error', e.message) }
}

async function adjust(payload) {
  try {
    run.value = await api.adjust({
      run_id: run.value.id, revision_note: '前端人工調整', ...payload,
    })
    runHistory.value = await api.runs(currentPassage.value.id)
    selected.value = null
    flash('ok', '已生成新版本；舊 run 與原轉錄均保留')
  } catch (e) { flash('error', e.message) }
}

async function loadRun(id) {
  run.value = await api.run(id)
  selected.value = null
}

const witnessSiglum = computed(() => {
  const m = {}
  witnesses.value.forEach(w => (m[w.id] = w.siglum))
  return m
})
</script>

<template>
  <header>
    <h1>古籍並列見本校勘</h1>
    <p class="muted" v-if="health">
      資料庫：{{ health.database }} ｜ CollateX：{{ health.collatex_url || '未配置（自動用內建比對器）' }}
      ｜ 原字形與比對形分存，自動建議不替代研究者結論
    </p>
  </header>

  <section class="card">
    <div class="row">
      <label>段落：
        <select
          :value="currentPassage?.id"
          @change="selectPassage($event.target.value)"
        >
          <option v-for="p in passages" :key="p.id" :value="p.id">
            {{ p.title }}
          </option>
        </select>
      </label>
      <span class="spacer"></span>
      <a :href="api.exportUrl(run.id, 'json')" target="_blank" v-if="run"><button>匯出 JSON</button></a>
      <a :href="api.exportUrl(run.id, 'csv')" target="_blank" v-if="run"><button>匯出 CSV</button></a>
      <a :href="api.exportUrl(run.id, 'md')" target="_blank" v-if="run"><button>匯出校勘記 MD</button></a>
    </div>
    <p class="muted" v-if="currentPassage" style="margin:6px 0 0">
      {{ currentPassage.reference }}
    </p>
  </section>

  <p v-if="message.text" :class="message.kind">{{ message.text }}</p>

  <h2>一、並列見本（原轉錄）</h2>
  <WitnessPanel :witnesses="witnesses" :previews="previews" />

  <section class="card">
    <h3 style="margin:4px 0 8px">新增見本</h3>
    <div class="row">
      <input v-model="form.siglum" type="text" placeholder="簡稱，如 丁本" />
      <input v-model="form.source" type="text" placeholder="來源，如 某氏重刻本" />
      <input v-model="form.era" type="text" placeholder="年代" />
    </div>
    <textarea
      v-model="form.raw"
      @blur="previewForm"
      placeholder="貼入原轉錄；可用記號 〖缺葉〗 【空白】 □ 〔批：…〕 〔插：…〕"
      style="margin-top:8px"
    ></textarea>
    <div class="row" style="margin-top:6px">
      <button @click="previewForm">預覽分詞</button>
      <button class="primary" @click="addWitness">建立見本</button>
      <span class="muted" v-if="formPreview.length">
        {{ formPreview.length }} 個 token：
        <span v-for="t in formPreview" :key="t.position" class="tok" :class="t.type">
          {{ t.orig }}<span v-if="t.norm && t.norm !== t.orig" class="norm">→{{ t.norm }}</span>
        </span>
      </span>
    </div>
  </section>

  <h2>二、規範化規則（只影響比對形）</h2>
  <section class="card">
    <table style="font-size:13px;border-collapse:collapse;width:100%">
      <tr v-for="r in rules" :key="r.id">
        <td style="padding:2px 8px;font-size:16px">{{ r.pattern }}</td>
        <td>→</td>
        <td style="font-size:16px">{{ r.replacement }}</td>
        <td class="muted">{{ r.note }}</td>
      </tr>
    </table>
    <div class="row" style="margin-top:8px">
      <input v-model="ruleForm.pattern" type="text" placeholder="原形，如 峯" />
      <span>→</span>
      <input v-model="ruleForm.replacement" type="text" placeholder="規範形，如 峰" />
      <input v-model="ruleForm.note" type="text" placeholder="備註" style="flex:1" />
      <button class="primary" @click="addRule">加規則</button>
    </div>
  </section>

  <h2>三、生成對齊候選</h2>
  <section class="card">
    <div class="row">
      <label><input type="checkbox" v-model="includePunct" /> 標點參與對齊</label>
      <label><input type="checkbox" v-model="useCollatex" /> 優先使用 CollateX（不可達時自動退回內建）</label>
      <button class="primary" @click="collate">開始對齊</button>
    </div>
    <p class="muted" style="margin-bottom:0">
      關閉標點時，不同斷句不會在正文行列產生差異；勾選後標點自成欄並標為「斷句」。
    </p>
  </section>

  <template v-if="run">
    <h2>
      四、對齊結果與人工判斷
      <span class="pill">run {{ run.id.slice(0, 8) }} · {{ run.engine }} · 標點{{ run.include_punctuation ? '計入' : '不計' }}</span>
    </h2>

    <ul class="markers">
      <li v-for="m in run.markers" :key="m.token_id" :class="`m-${m.type}`">
        [{{ markerLabel[m.type] }}] <strong>{{ witnessSiglum[m.witness_id] }}</strong>
        {{ m.orig }}
        <span v-if="m.note">（{{ m.note }}）</span>
        <span class="muted">—— 錨定於第 {{ m.anchor_column_index ?? '?' }} 欄</span>
      </li>
    </ul>

    <div class="layout" style="margin-top:10px">
      <CollationGrid
        :run="run"
        :witnesses="witnesses"
        :selected="selected"
        @select="selected = $event"
      />
      <JudgmentPanel
        :run="run"
        :witnesses="witnesses"
        :column-index="selected"
        @judge="judge"
        @adjust="adjust"
      />
    </div>

    <h2>五、對齊版本（調整不覆舊）</h2>
    <section class="card">
      <table style="width:100%;font-size:13px;border-collapse:collapse">
        <tr v-for="r in runHistory" :key="r.id"
            :style="r.id === run.id ? 'background:#f3e9dc' : ''">
          <td style="padding:3px 8px">{{ r.created_at?.replace('T', ' ').slice(0, 19) }}</td>
          <td>{{ r.engine }}</td>
          <td>{{ r.revision_note || '（自動對齊）' }}</td>
          <td>{{ r.judgments?.length || 0 }} 條判斷</td>
          <td><button @click="loadRun(r.id)" :disabled="r.id === run.id">查看</button></td>
        </tr>
      </table>
    </section>
  </template>
</template>
