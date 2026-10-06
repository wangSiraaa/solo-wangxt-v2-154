<script setup>
defineProps({ witnesses: { type: Array, required: true } })
</script>

<template>
  <div class="panel">
    <h3>见本与原转录（逐字符保留，自动流程不改写）</h3>
    <div class="witness-grid">
      <div class="witness-card" v-for="w in witnesses" :key="w.id">
        <div class="siglum">{{ w.siglum }} <span class="label">{{ w.label }}</span></div>
        <div class="source">来源：{{ w.source_note || '（未标注）' }}</div>
        <pre>{{ w.raw_transcription }}</pre>
      </div>
    </div>
  </div>
</template>
