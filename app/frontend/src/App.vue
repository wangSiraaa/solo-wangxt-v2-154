<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api/client.js'
import WitnessCards from './components/WitnessCards.vue'
import RulesPanel from './components/RulesPanel.vue'
import AlignmentGrid from './components/AlignmentGrid.vue'
import ApparatusEntries from './components/ApparatusEntries.vue'
import RuleDialog from './components/RuleDialog.vue'
import WitnessDialog from './components/WitnessDialog.vue'

const passages = ref([])
const currentId = ref(null)
const passage = ref(null)
const rules = ref([])
const run = ref(null)
const runs = ref([])
const variantTypes = ref([])
const includePunctuation = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const showRuleDialog = ref(false)
const showWitnessDialog = ref(false)

const currentPassage = computed(() => passage.value)

function flash(msg, isError = false) {
  (isError ? error : notice).value = msg
  setTimeout(() => {
    if (isError) error.value = ''; else notice.value = ''
  }, 5000)
}

async function loadPassages() {
  passages.value = await api.listPassages()
  if (!currentId.value && passages.value.length) {
    await selectPassage(passages.value[0].id)
  }
}

async function selectPassage(id) {
  currentId.value = id
  error.value = notice.value = ''
  passage.value = await api.getPassage(id)
  rules.value = await api.listRules(id)
  runs.value = await api.listRuns(id)
  run.value = null
  if (runs.value.length) {
    run.value = await api.getRun(runs.value[0].id)
  }
}

async function doCollate() {
  loading.value = true
  error.value = ''
  try {
    run.value = await api.runCollation({
      passage_id: currentId.value,
      include_punctuation: includePunctuation.value,
    })
    runs.value = await api.listRuns(currentId.value)
    if (run.value.note) flash(run.value.note)
  } catch (e) {
    flash(e.message, true)
  } finally {
    loading.value = false
  }
}

async function saveJudgment(c, body) {
  await api.setJudgment(c.id, body)
  Object.assign(c, body)
}

async function doOverride(action, payload) {
  const res = await api.addOverride(run.value.id, { action, payload })
  run.value = res.run
  flash(`已记录调整：${action}（原转录未改动）`)
}

async function toggleRule(r) {
  await api.updateRule(r.id, {
    pattern: r.pattern, replacement: r.replacement, note: r.note,
    witness_id: r.witness_id, priority: r.priority, active: !r.active,
  })
  rules.value = await api.listRules(currentId.value)
}
async function removeRule(r) {
  if (!confirm(`删除规则 ${r.pattern} → ${r.replacement}？原转录不受影响。`)) return
  await api.deleteRule(r.id)
  rules.value = await api.listRules(currentId.value)
}
async function addRule(body) {
  await api.createRule(currentId.value, body)
  rules.value = await api.listRules(currentId.value)
  showRuleDialog.value = false
}
async function addWitness(body) {
  await api.addWitness(currentId.value, body)
  passage.value = await api.getPassage(currentId.value)
  showWitnessDialog.value = false
}

async function switchRun(ev) {
  const id = Number(ev.target.value)
  if (id) run.value = await api.getRun(id)
}

function exportLink(fmt) {
  return api.exportUrl(run.value.id, fmt)
}

onMounted(async () => {
  variantTypes.value = await api.variantTypes()
  await loadPassages()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div>
        <h1>并列见本校勘台</h1>
        <div class="sub">Vue 3 · FastAPI · CollateX · PostgreSQL</div>
      </div>
      <div>
        <div class="muted" style="margin-bottom:6px">文字段落</div>
        <div v-for="p in passages" :key="p.id"
             class="passage-item" :class="{ active: p.id === currentId }"
             @click="selectPassage(p.id)">
          <div class="t">{{ p.title }}</div>
          <div class="m">{{ p.witnesses.length }} 个见本</div>
        </div>
      </div>
      <button v-if="currentPassage" @click="showWitnessDialog = true">＋ 新增见本</button>
      <div class="sub" style="margin-top:auto">
        自动建议只作候选；原转录与人工判断分别保存。
      </div>
    </aside>

    <main class="main" v-if="currentPassage">
      <h2>{{ currentPassage.title }}</h2>
      <p class="description">{{ currentPassage.description }}</p>
      <p v-if="error" class="error" style="font-size:14px">⚠ {{ error }}</p>
      <p v-if="notice" class="engine-note">{{ notice }}</p>

      <WitnessCards :witnesses="currentPassage.witnesses" />

      <RulesPanel :rules="rules" @toggle="toggleRule" @remove="removeRule"
                  @add="showRuleDialog = true" />

      <div class="panel">
        <h3>生成对齐候选</h3>
        <div class="toolbar">
          <label>
            <input type="checkbox" v-model="includePunctuation" />
            标点参与对齐（不勾选则只比对文字，断句差异另行展示）
          </label>
          <button class="primary" :disabled="loading" @click="doCollate">
            {{ loading ? '比对中…' : (run ? '重新运行 CollateX' : '运行 CollateX 校勘') }}
          </button>
          <select v-if="runs.length" :value="run?.id" @change="switchRun">
            <option v-for="r in runs" :key="r.id" :value="r.id">
              #{{ r.id }} {{ r.engine }} · 标点{{ r.include_punctuation ? '入' : '不入' }}
            </option>
          </select>
        </div>
        <div v-if="run" class="toolbar" style="margin-top:0">
          <span class="engine-note">引擎：{{ run.engine }} — {{ run.note || 'CollateX 原生结果' }}</span>
          <a :href="exportLink('json')"><button>导出 JSON</button></a>
          <a :href="exportLink('csv')"><button>导出 CSV 校勘表</button></a>
          <a :href="exportLink('xml')"><button>导出 TEI XML</button></a>
          <span class="muted">导出含见本来源、规则快照、自动建议、人工判断与调整记录</span>
        </div>
      </div>

      <template v-if="run">
        <AlignmentGrid :run="run" :witnesses="currentPassage.witnesses" />
        <ApparatusEntries :run="run" :witnesses="currentPassage.witnesses"
                          :variant-types="variantTypes"
                          :on-judgment="saveJudgment" :on-override="doOverride"
                          @error="(m) => flash(m, true)" />
        <div class="panel">
          <h3>人工调整记录（审计）</h3>
          <p v-if="!run.overrides.length" class="muted">尚无调整。</p>
          <div v-for="o in run.overrides" :key="o.id" class="hist-item">
            #{{ o.id }} {{ o.author }} 执行 <code>{{ o.action }}</code>
            — {{ JSON.stringify(o.payload) }}
          </div>
        </div>
      </template>
      <div v-else class="panel muted">
        选择是否让标点参与对齐，点击「运行 CollateX 校勘」生成候选；候选不会替代研究者结论。
      </div>
    </main>

    <RuleDialog v-if="showRuleDialog" @close="showRuleDialog = false" @submit="addRule" />
    <WitnessDialog v-if="showWitnessDialog" @close="showWitnessDialog = false" @submit="addWitness" />
  </div>
</template>
