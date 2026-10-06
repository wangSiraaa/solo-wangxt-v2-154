<script setup>
import { ref } from 'vue'

const props = defineProps({
  run: { type: Object, required: true },
  witnesses: { type: Array, required: true },
  variantTypes: { type: Array, required: true },
  onJudgment: { type: Function, required: true },
  onOverride: { type: Function, required: true },
})
const emit = defineEmits(['error'])

const onlyDiff = ref(true)
const saved = ref(null)
const busy = ref(null)

const wmap = () => Object.fromEntries(props.witnesses.map((w) => [String(w.id), w]))

function visible() {
  return props.run.columns.filter((c) => !onlyDiff.value || (c.suggested_type && c.suggested_type !== 'identical'))
}
function presentReadings(c) {
  const m = wmap()
  return Object.entries(c.tokens)
    .filter(([, t]) => t)
    .map(([wid, t]) => ({ sig: m[wid]?.siglum || wid, t }))
}
function absentWitnesses(c) {
  const m = wmap()
  return Object.entries(c.tokens)
    .filter(([, t]) => !t)
    .map(([wid]) => m[wid]?.siglum || wid)
}

async function saveJudgment(c) {
  busy.value = c.id
  try {
    await props.onJudgment(c, {
      researcher_type: c.researcher_type || null,
      researcher_note: c.researcher_note || '',
      confirmed: c.confirmed,
    })
    saved.value = c.id
    setTimeout(() => (saved.value = null), 1500)
  } catch (e) {
    emit('error', e.message)
  } finally {
    busy.value = null
  }
}
async function act(c, action, payload) {
  try {
    await props.onOverride(action, payload)
  } catch (e) {
    emit('error', e.message)
  }
}
</script>

<template>
  <div class="panel">
    <h3>校勘条目 <label style="font-weight:400;font-size:13px;margin-left:10px">
      <input type="checkbox" v-model="onlyDiff" /> 只看有差异的列
    </label></h3>
    <p class="muted">
      灰字为系统自动建议，仅供参考；研究者结论写在下方下拉与按语中，二者各自保存、互不覆盖。
    </p>

    <div v-for="c in visible()" :key="c.id" class="entry">
      <div class="pos">#{{ c.position }}</div>
      <div>
        <div class="readings">
          <span v-for="r in presentReadings(c)" :key="r.sig" class="r">
            <span class="sig">{{ r.sig }}</span>
            <span :class="{ 'glyph unknown': r.t.kind === 'unknown', 'glyph variant': r.t.kind === 'char' && c.suggested_type === 'glyph_variant' }">
              {{ r.t.display }}
            </span>
            <span v-if="r.t.kind === 'lacuna'" class="coltype-badge t-lacuna">缺{{ r.t.gap_amount ? r.t.gap_amount + (r.t.gap_unit || '') : '' }}</span>
            <span v-if="r.t.kind === 'blank'" class="coltype-badge t-blank">空白</span>
            <span v-if="r.t.norm && r.t.norm !== r.t.display" class="norm-tag" style="display:inline">范：{{ r.t.norm }}</span>
          </span>
          <span v-if="absentWitnesses(c).length" class="r muted">
            {{ absentWitnesses(c).join('、') }} 无文
          </span>
        </div>
        <div class="auto">
          自动建议：<span class="coltype-badge" :class="`t-${c.suggested_type}`">{{ c.suggested_type }}</span>
          {{ c.suggested_reason }}
        </div>
        <div class="judge-row">
          <strong>研究者：</strong>
          <select v-model="c.researcher_type">
            <option :value="null">（未判定）</option>
            <option v-for="v in variantTypes" :key="v.value" :value="v.value">{{ v.label }} ({{ v.value }})</option>
          </select>
          <input type="text" v-model="c.researcher_note" placeholder="校记按语……" />
          <label><input type="checkbox" v-model="c.confirmed" /> 确认定稿</label>
          <button class="primary" :disabled="busy === c.id" @click="saveJudgment(c)">
            {{ saved === c.id ? '已保存 ✓' : '保存判断' }}
          </button>
        </div>
        <div class="judge-row">
          <span class="muted">调整对齐（不动原转录）：</span>
          <button @click="act(c, 'split', { column_id: c.id, witness_id: witnesses[0].id })"
                  title="把第一见本从此列拆出为新列">拆分此列</button>
          <button @click="act(c, 'mark_lacuna', { column_id: c.id, witness_id: witnesses[0].id, kind: 'lacuna' })"
                  title="仅允许在空缺处补结构标记，不能补实字">标为缺文</button>
          <button @click="act(c, 'mark_lacuna', { column_id: c.id, witness_id: witnesses[0].id, kind: 'blank' })">
            标为空白</button>
          <span v-if="c.confirmed" class="saved">已确认条目</span>
        </div>
      </div>
    </div>
  </div>
</template>
