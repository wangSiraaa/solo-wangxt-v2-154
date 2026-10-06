// 组件渲染冒烟测试：用 vite 的 SSR 管线加载真实 .vue 文件，
// 以模拟 props 渲染，验证模板编译与关键内容（原转录、缺叶标记、人工判断区等）。
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

const vite = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
})

async function load(path) {
  return (await vite.ssrLoadModule(path)).default
}

const witnesses = [
  { id: 1, siglum: '甲本', label: '清抄本', source_note: '私家藏',
    raw_transcription: '夜分，誦聲［批注：朱筆］' },
  { id: 2, siglum: '乙本', label: '石印本', source_note: '民國石印',
    raw_transcription: '夜分誦聲〔缺二叶〕〔空白〕□' },
]
const run = {
  id: 1, engine: 'internal-fallback', note: '内置比对',
  columns: [
    { id: 1, position: 0, tokens: { 1: { kind: 'char', display: '夜', norm: '夜' }, 2: { kind: 'char', display: '夜', norm: '夜' } },
      suggested_type: 'identical', suggested_reason: '一致', researcher_type: null, researcher_note: '', confirmed: false },
    { id: 2, position: 1, tokens: { 1: { kind: 'char', display: '峯', norm: '峰' }, 2: { kind: 'char', display: '峰', norm: '峰' } },
      suggested_type: 'glyph_variant', suggested_reason: '异体字', researcher_type: null, researcher_note: '', confirmed: false },
    { id: 3, position: 2, tokens: { 1: null, 2: { kind: 'lacuna', display: '〔缺二叶〕', norm: '', gap_amount: 2, gap_unit: '叶' } },
      suggested_type: 'mixed_struct', suggested_reason: '需人工', researcher_type: null, researcher_note: '', confirmed: true },
  ],
  annotations: [
    { witness_id: 1, display: '［批注：朱筆］', anchor_after: 1, anchor_before: 2 },
  ],
  overrides: [{ id: 1, action: 'anchor_insert', payload: { after_position: 1 }, author: 'researcher' }],
}
const variantTypes = [{ value: 'glyph_variant', label: '异体字' }, { value: 'lacuna', label: '缺叶' }]

const checks = []
async function check(name, path, propsData, mustContain) {
  const Comp = await load(path)
  const app = createSSRApp({ render: () => h(Comp, propsData) })
  const html = await renderToString(app)
  const missing = mustContain.filter((s) => !html.includes(s))
  checks.push([name, missing.length === 0, missing, html.length])
}

await check('WitnessCards', '/src/components/WitnessCards.vue', { witnesses },
  ['甲本', '夜分，誦聲［批注：朱筆］', '〔缺二叶〕', '来源：私家藏'])
await check('AlignmentGrid', '/src/components/AlignmentGrid.vue', { run, witnesses },
  ['峯', '峰', '〔缺二叶〕', '范：峰', '异体字', '［批注：朱筆］', '锚于字位 1 之后'])
await check('ApparatusEntries', '/src/components/ApparatusEntries.vue',
  { run: JSON.parse(JSON.stringify(run)), witnesses, variantTypes,
    onJudgment: async () => {}, onOverride: async () => {} },
  ['自动建议', '研究者', '保存判断', '拆分此列', '异体字'])

await vite.close()
let ok = true
for (const [name, passed, missing, size] of checks) {
  console.log(`${passed ? 'PASS' : 'FAIL'} ${name} (html ${size}B)` +
    (missing.length ? ` 缺少: ${missing.join(' | ')}` : ''))
  if (!passed) ok = false
}
process.exit(ok ? 0 : 1)
