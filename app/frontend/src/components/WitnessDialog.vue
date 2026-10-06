<script setup>
import { reactive } from 'vue'

const emit = defineEmits(['close', 'submit'])
const form = reactive({
  siglum: '', label: '', source_note: '', raw_transcription: '', sort_order: 0,
})

function submit() {
  if (!form.siglum || !form.raw_transcription) return
  emit('submit', { ...form })
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" style="width: 560px">
      <h3>新增见本</h3>
      <p class="muted">
        标记语法：〔缺二叶〕缺叶 · 〔空白〕版面留白 · □三 残泐未知三字（不猜补） ·
        ［批注：…］/［添：…］/［按：…］插入片段（自动锚定相邻字位） ·
        【原字形→规范形】就地规范提示。
      </p>
      <div class="row"><label>简称 siglum</label><input v-model="form.siglum" placeholder="如 丁本" /></div>
      <div class="row"><label>名称</label><input v-model="form.label" placeholder="如 明初刻本" /></div>
      <div class="row"><label>来源说明</label><input v-model="form.source_note" placeholder="藏地、形制、批校者等" /></div>
      <div class="row"><label>原转录（逐字符照录）</label>
        <textarea v-model="form.raw_transcription" rows="6" placeholder="直接粘贴转录文本……"></textarea>
      </div>
      <div class="row"><label>排序</label><input type="number" v-model.number="form.sort_order" /></div>
      <div class="actions">
        <button @click="emit('close')">取消</button>
        <button class="primary" @click="submit">保存见本</button>
      </div>
    </div>
  </div>
</template>
