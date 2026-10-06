<script setup>
// 並列見本：依 token 類型上色；原轉錄保持一字不改地呈現
defineProps({
  witnesses: { type: Array, required: true },
  // witnessId -> 預覽 token（可選，沒有就直接用 raw_transcription）
  previews: { type: Object, default: () => ({}) },
})
</script>

<template>
  <div class="witness-grid">
    <div class="legend">
      記號圖例：
      <code class="tok lacuna">〖缺葉〗</code>缺葉
      <code class="tok blank">【空白】</code>空白正文（與缺葉不同）
      <code class="tok unknown">□</code>未知字（不猜補）
      <code class="tok annotation">〔批：…〕</code>批注
      <code class="tok insertion">〔插：…〕</code>插入片段（錨定相鄰位置）
    </div>

    <div v-for="w in witnesses" :key="w.id" class="witness">
      <header>
        <span class="siglum">{{ w.siglum }}</span>
        <span class="muted">{{ w.source }} · {{ w.era }}</span>
      </header>
      <div class="transcript">
        <template v-if="previews[w.id]">
          <span
            v-for="t in previews[w.id]"
            :key="t.position"
            class="tok"
            :class="t.type"
            :title="`原字形：${t.orig}｜比對形：${t.norm}｜類型：${t.type}`"
          >{{ t.orig }}</span>
        </template>
        <template v-else>{{ w.raw_transcription }}</template>
      </div>
    </div>
  </div>
</template>
