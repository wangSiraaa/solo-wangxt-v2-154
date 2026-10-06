// 與 FastAPI 互動的薄封裝
const BASE = '/api'

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.headers.get('content-type')?.includes('application/json')) {
    return res.json()
  }
  return res.text()
}

export const api = {
  health: () => req('/health'),
  passages: () => req('/passages'),
  passage: (id) => req(`/passages/${id}`),
  createPassage: (data) => req('/passages', {
    method: 'POST', body: JSON.stringify(data),
  }),
  addWitness: (pid, data) => req(`/passages/${pid}/witnesses`, {
    method: 'POST', body: JSON.stringify(data),
  }),
  rules: (pid) => req(`/passages/${pid}/rules`),
  addRule: (pid, data) => req(`/passages/${pid}/rules`, {
    method: 'POST', body: JSON.stringify(data),
  }),
  preview: (raw, pid) => req('/preview', {
    method: 'POST',
    body: JSON.stringify({ raw_transcription: raw, passage_id: pid }),
  }),
  collate: (data) => req('/collate', {
    method: 'POST', body: JSON.stringify(data),
  }),
  runs: (pid) => req(`/passages/${pid}/runs`),
  run: (id) => req(`/runs/${id}`),
  judge: (runId, data) => req(`/runs/${runId}/judgments`, {
    method: 'PUT', body: JSON.stringify(data),
  }),
  adjust: (data) => req('/adjust', {
    method: 'POST', body: JSON.stringify(data),
  }),
  exportUrl: (runId, fmt) => `${BASE}/runs/${runId}/export?fmt=${fmt}`,
}

export const KIND_LABELS = {
  variant_form: '異體/異文',
  omission: '脫文',
  added: '增衍',
  same: '一致',
  punctuation: '斷句',
  annotation: '批注',
  insertion: '插入',
  lacuna: '缺葉',
  blank: '空白',
  unknown: '存疑',
  doubtful: '待考',
  moved: '移位',
  undecided: '未判定',
}

export const HUMAN_KINDS = [
  'variant_form', 'omission', 'added', 'same', 'punctuation',
  'annotation', 'insertion', 'lacuna', 'blank', 'unknown',
  'doubtful', 'moved', 'undecided',
]
