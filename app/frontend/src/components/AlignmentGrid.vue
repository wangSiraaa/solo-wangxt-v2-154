<script setup>
import { computed } from 'vue'

const props = defineProps({
  run: { type: Object, required: true },
  witnesses: { type: Array, required: true },
})

const TYPE_LABEL = {
  identical: '一致', glyph_variant: '异体字', substitution: '异文',
  omission: '脱文', addition: '添入', punctuation: '断句',
  lacuna: '缺叶', blank: '空白', unknown_char: '未知字',
  mixed_struct: '结构混合', divergent: '待判',
}

const wmap = computed(() => Object.fromEntries(props.witnesses.map((w) => [String(w.id), w])))
const wids = computed(() => props.witnesses.map((w) => String(w.id)))

function cellClass(tok, col) {
  if (!tok) return 'cell-gap'
  if (tok.kind === 'lacuna') return 'cell-lacuna'
  if (tok.kind === 'blank') return 'cell-blank'
  if (tok.kind === 'unknown') return 'glyph unknown'
  if (tok.kind === 'punct') return 'cell-punct'
  if (col.suggested_type === 'glyph_variant' || (tok.norm && tok.norm !== tok.display)) return 'glyph variant'
  return 'glyph'
}
function cellText(tok) {
  if (!tok) return '∸'
  return tok.display
}
function isDiff(col) {
  return col.suggested_type && col.suggested_type !== 'identical'
}
</script>

<template>
  <div class="panel">
    <h3>并列见本对齐表</h3>
    <div class="legend">
      <span><i class="sw" style="background:#f6e5d6"></i>异体字（规范形相同）</span>
      <span><i class="sw" style="background:#f8dcd8"></i>异文/未知字</span>
      <span><i class="sw" style="background:#f3e2dc"></i>缺叶缺文</span>
      <span><i class="sw" style="background:#ecece6"></i>空白正文</span>
      <span><i class="sw" style="background:#e3ebf2"></i>断句标点</span>
      <span><i class="sw" style="box-shadow:inset 0 0 0 2px #4a6b3a"></i>已出人工判断</span>
      <span>∸ 该见本此处无文（脱/添的原始材料）</span>
    </div>
    <div class="alignment-scroll">
      <table class="alignment">
        <thead>
          <tr>
            <th class="row-head">见本 ＼ 列位</th>
            <th v-for="c in run.columns" :key="c.id" :title="`列 ${c.position}`">
              <span class="coltype-badge" :class="`t-${c.suggested_type}`">
                {{ TYPE_LABEL[c.suggested_type] || c.suggested_type }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="wid in wids" :key="wid">
            <th class="row-head">{{ wmap[wid]?.siglum || wid }}</th>
            <td v-for="c in run.columns" :key="c.id"
                :class="[isDiff(c) ? 'col-diff' : '', c.confirmed ? 'col-confirmed' : '']"
                :title="c.suggested_reason">
              <span :class="cellClass(c.tokens[wid], c)">{{ cellText(c.tokens[wid]) }}</span>
              <span v-if="c.tokens[wid] && c.tokens[wid].norm && c.tokens[wid].norm !== c.tokens[wid].display"
                    class="norm-tag">范：{{ c.tokens[wid].norm }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="run.annotations && run.annotations.length" class="annotation-rail">
      <span class="muted" style="width:100%">插入片段（批注/添补/按语，不参与正文对齐，锚定相邻字位）：</span>
      <span v-for="(a, i) in run.annotations" :key="i" class="annotation-chip">
        {{ wmap[String(a.witness_id)]?.siglum }} {{ a.display }}
        <span class="anchor">锚于字位 {{ a.anchor_after ?? 0 }} 之后{{ a.anchor_before ? `、${a.anchor_before} 之前` : '' }}</span>
      </span>
    </div>
  </div>
</template>
