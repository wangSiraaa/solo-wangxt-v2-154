<script setup>
import { reactive } from 'vue'

const emit = defineEmits(['close', 'submit'])
const form = reactive({ pattern: '', replacement: '', note: '', priority: 100, active: true })

function submit() {
  if (!form.pattern || !form.replacement) return
  emit('submit', { ...form })
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog">
      <h3>新增规范化规则</h3>
      <p class="muted">
        映射只影响匹配用的规范形，原字形在转录与界面中保持不变。
        不能对未知字 □、缺叶、空白建立规则。
      </p>
      <div class="row"><label>原字形（pattern）</label><input v-model="form.pattern" placeholder="如 峯" /></div>
      <div class="row"><label>规范形（replacement）</label><input v-model="form.replacement" placeholder="如 峰" /></div>
      <div class="row"><label>说明</label><input v-model="form.note" placeholder="如 峯為峰之異體" /></div>
      <div class="row"><label>优先级（大者先用）</label><input type="number" v-model.number="form.priority" /></div>
      <div class="actions">
        <button @click="emit('close')">取消</button>
        <button class="primary" @click="submit">保存规则</button>
      </div>
    </div>
  </div>
</template>
