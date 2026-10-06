<script setup>
import { computed } from 'vue'
import { HUMAN_KINDS, KIND_LABELS } from '../api.js'

const props = defineProps({
  run: { type: Object, required: true },
  witnesses: { type: Array, required: true },
  columnIndex: { type: Number, default: null },
})
const emit = defineEmits(['judge', 'adjust', 'message'])

const col = computed(() =>
  props.columnIndex == null ? null : props.run.columns[props.columnIndex])

const judgment = computed(() =>
  props.run.judgments?.find(j => j.column_index === props.columnIndex) || null)

const draft = computed(() => ({
  kind: judgment.value?.kind || 'undecided',
  rationale: judgment.value?.rationale || '',
}))

function save() {
  if (!col.value) return
  emit('judge', {
    column_index: col.value.index,
    kind: draft.value.kind,
    rationale: draft.value.rationale,
  })
}

function split() {
  emit('adjust', { action: 'split_col', column_index: col.value.index })
}
</script>

<template>
  <aside class="panel">
    <h3 style="margin:0 0 8px">校勘判斷</h3>
    <p v-if="!col" class="muted">點選左側對齊表中的任一欄，查看各見本異同並下判斷。</p>

    <template v-else>
      <div class="muted">第 {{ col.index }} 欄</div>
      <table style="width:100%;font-size:13px;border-collapse:collapse;margin:6px 0">
        <tr v-for="w in witnesses" :key="w.id">
          <td style="padding:2px 6px;color:var(--muted);white-space:nowrap">{{ w.siglum }}</td>
          <td style="padding:2px 6px;font-size:17px">
            <template v-if="col.cells[w.id]">
              {{ col.cells[w.id].orig }}
              <span class="muted" v-if="col.cells[w.id].norm !== col.cells[w.id].orig">
                （比對形 {{ col.cells[w.id].norm }}）
              </span>
            </template>
            <span class="cell-empty">（無）</span>
          </td>
        </tr>
      </table>

      <div class="suggestion">
        <strong>系統建議（僅供參考，不構成結論）</strong><br />
        {{ KIND_LABELS[col.suggested_kind] || col.suggested_kind }}
        — {{ col.suggested_note }}
      </div>

      <div v-if="judgment" class="human">
        <strong>研究者判斷</strong>：{{ KIND_LABELS[judgment.kind] }}
        <div v-if="judgment.rationale" style="margin-top:4px">「{{ judgment.rationale }}」</div>
      </div>

      <label class="muted" style="display:block;margin-top:8px">人工判斷類別</label>
      <select v-model="draft.kind" style="width:100%;margin:4px 0">
        <option v-for="k in HUMAN_KINDS" :key="k" :value="k">{{ KIND_LABELS[k] }}</option>
      </select>

      <label class="muted" style="display:block;margin-top:6px">理由／校記</label>
      <textarea v-model="draft.rationale" placeholder="例如：乙本多一「其」字，甲丙二本俱無，疑為刻者所增……"></textarea>

      <div class="row" style="margin-top:8px">
        <button class="primary" @click="save">保存判斷</button>
        <button @click="split">拆分此欄</button>
      </div>
      <p class="muted" style="margin-bottom:0">
        調整只會生成新版本，不修改原轉錄；未知字「□」不可被移補為猜測字。
      </p>
    </template>
  </aside>
</template>
