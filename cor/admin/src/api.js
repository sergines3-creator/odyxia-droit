// Client API centralisé — toutes les requêtes vers le serveur COR passent ici.
// Les requêtes utilisent le préfixe /api pour passer par le proxy Vite (évite CORS).

const BASE = '/api'
const KEY  = import.meta.env.VITE_COR_KEY  || ''

async function req(method, path, body = null, isFormData = false) {
  const headers = { 'X-Cor-Key': KEY }
  if (!isFormData && body) headers['Content-Type'] = 'application/json'

  const opts = {
    method,
    headers,
    body: isFormData ? body : (body ? JSON.stringify(body) : null),
  }

  const res = await fetch(`${BASE}${path}`, opts)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw Object.assign(new Error(data.erreur || `HTTP ${res.status}`), { status: res.status, data })
  return data
}

// ── Santé ──────────────────────────────────────────────────────────────────────
export const getHealth  = () => req('GET', '/health')
export const getInfo    = () => req('GET', '/info')

// ── Génération ─────────────────────────────────────────────────────────────────
export const generate = (question, pays, temperature, maxTokens) =>
  req('POST', '/generate', { question, pays_token: pays || null, temperature, max_tokens: maxTokens })

// ── RAG ────────────────────────────────────────────────────────────────────────
export const getRagDocuments  = ()           => req('GET',    '/rag/documents')
export const getRagStats      = ()           => req('GET',    '/rag/stats')
export const deleteRagDoc     = (id)         => req('DELETE', `/rag/document/${id}`)
export const addRagDocument   = (texte, meta) => req('POST',  '/rag/add_document', { texte, ...meta })

export function addRagPdf(file, meta) {
  const fd = new FormData()
  fd.append('fichier', file)
  Object.entries(meta).forEach(([k, v]) => v && fd.append(k, v))
  return req('POST', '/rag/add_pdf', fd, true)
}

// ── Entraînement ───────────────────────────────────────────────────────────────
export const getTrainStatus = () => req('GET',  '/train/status')
export const startTrain     = (cfg) => req('POST', '/train/start', cfg)
export const stopTrain      = ()   => req('POST', '/train/stop')

// ── Clients ────────────────────────────────────────────────────────────────────
export const getClients  = ()               => req('GET',  '/clients')
export const createClient = (nom, quota)   => req('POST', '/clients', { nom, quota_mensuel: quota })
