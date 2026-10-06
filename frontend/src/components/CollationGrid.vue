<script setup>
// 並列對齊表：列＝見本（含來源簡稱），欄＝對齊位；自動建議只著色不替代結論
const props = defineProps({
  run: { type: Object, required: true },
  witnesses: { type: Array, required: true },
  selected: { type: Number, default: null },
})
const emit = defineEmits(['select'])

const kindText = {
  variant_form: '異體/異文', omission: '脫文/增入', same: '一致',
  punctuation: '斷句', lacuna: '缺葉', blank: '空白',
  undecided: '未判定',
}

function cellClass(cell) {
  return {
    lacuna: cell?.type === 'lacuna',
    blank: cell?.type === 'blank',
  }
}
</script>

<template>
  <div class="collation-scroll">
    <table class="alignment">
      <thead>
        <tr>
          <th>欄</th>
          <th v-for="w in witnesses" :key="w.id">{{ w.siglum }}</th>
          <th>自動建議</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="col in run.columns" :key="col.index">
          <td class="colhead">{{ col.index }}</td>
          <td
            v-for="w in witnesses"
            :key="w.id"
            :class="['', `k-${col.suggested_kind}`, { selected: selected === col.index }, cellClass(col.cells[w.id])]"
            @click="emit('select', col.index)"
            :title="col.cells[w.id] ? `原：${col.cells[w.id].orig}｜比對：${col.cells[w.id].norm}` : '此本無字'"
          >
            <template v-if="col.cells[w.id]">
              <span class="glyph">{{ col.cells[w.id].orig }}</span>
              <span
                v-if="col.cells[w.id].norm && col.cells[w.id].norm !== col.cells[w.id].orig"
                class="norm"
              >→{{ col.cells[w.id].norm }}</span>
            </template>
            <span v-else class="cell-empty">·</span>
          </td>
          <td class="colhead">
            {{ kindText[col.suggested_kind] || col.suggested_kind }}
            <span v-if="run.judgments?.some(j => j.column_index === col.index)" class="judged-mark" title="已有研究者判斷">●</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
