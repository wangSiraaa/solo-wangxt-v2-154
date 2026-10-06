const BASE = ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch (e) {
      /* ignore */
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  if (res.headers.get('content-type')?.includes('application/json')) {
    return res.json()
  }
  return res.blob()
}

export const api = {
  health: () => request('/health'),
  listPassages: () => request('/passages'),
  getPassage: (id) => request(`/passages/${id}`),
  createPassage: (body) => request('/passages', { method: 'POST', body: JSON.stringify(body) }),
  addWitness: (pid, body) => request(`/passages/${pid}/witnesses`, { method: 'POST', body: JSON.stringify(body) }),
  parsePreview: (pid) => request(`/passages/${pid}/parse`),

  listRules: (pid) => request(`/rules/passage/${pid}`),
  createRule: (pid, body) => request(`/rules/passage/${pid}`, { method: 'POST', body: JSON.stringify(body) }),
  updateRule: (rid, body) => request(`/rules/${rid}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteRule: (rid) => request(`/rules/${rid}`, { method: 'DELETE' }),

  variantTypes: () => request('/variant-types'),
  runCollation: (body) => request('/collations/run', { method: 'POST', body: JSON.stringify(body) }),
  listRuns: (pid) => request(`/passages/${pid}/runs`),
  getRun: (rid) => request(`/runs/${rid}`),
  setJudgment: (cid, body) => request(`/columns/${cid}/judgment`, { method: 'PUT', body: JSON.stringify(body) }),
  addOverride: (rid, body) => request(`/runs/${rid}/overrides`, { method: 'POST', body: JSON.stringify(body) }),
  exportUrl: (rid, fmt) => `/runs/${rid}/export.${fmt}`,
}
