<script setup>
defineProps({
  rules: { type: Array, required: true },
})
const emit = defineEmits(['toggle', 'remove', 'add'])
</script>

<template>
  <div class="panel">
    <h3>规范化规则（只用于匹配，不改原字形）</h3>
    <p class="muted">
      规则把原字形映射到规范形后再送 CollateX；停用规则后重跑校勘即可得到不同候选。
      另在转录中可就地写 <code>【原字形→规范形】</code>。残泐未知字 □、缺叶、空白不受任何规则影响。
    </p>
    <div v-for="r in rules" :key="r.id" class="rule-row" :class="{ off: !r.active }">
      <input :value="r.pattern" disabled title="原字形" />
      <span class="arrow">→</span>
      <input :value="r.replacement" disabled title="规范形" />
      <span class="note">{{ r.note }}</span>
      <button @click="emit('toggle', r)">{{ r.active ? '停用' : '启用' }}</button>
      <button class="danger" @click="emit('remove', r)">删除</button>
    </div>
    <div style="margin-top: 10px">
      <button @click="emit('add')">＋ 新增规范化规则</button>
    </div>
  </div>
</template>
