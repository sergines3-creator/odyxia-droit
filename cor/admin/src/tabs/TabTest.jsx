import { useState, useRef } from 'react'
import { generate } from '../api.js'

const PAYS_OPTIONS = [
  { value: '',        label: 'Détection auto' },
  { value: '[CM]',    label: 'Cameroun' },
  { value: '[GA]',    label: 'Gabon' },
  { value: '[BJ]',    label: 'Bénin' },
  { value: '[CI]',    label: "Côte d'Ivoire" },
  { value: 'OHADA',   label: 'OHADA' },
  { value: 'CEMAC',   label: 'CEMAC' },
  { value: 'UEMOA',   label: 'UEMOA' },
]

export default function TabTest() {
  const [question,     setQuestion]    = useState('')
  const [pays,         setPays]        = useState('')
  const [temperature,  setTemperature] = useState(0.7)
  const [maxTokens,    setMaxTokens]   = useState(150)
  const [loading,      setLoading]     = useState(false)
  const [response,     setResponse]    = useState(null)
  const [history,      setHistory]     = useState([])
  const textareaRef = useRef(null)

  async function handleGenerate() {
    if (!question.trim() || loading) return

    setLoading(true)
    setResponse(null)

    const t0 = Date.now()
    try {
      const data = await generate(question.trim(), pays, temperature, maxTokens)
      const entry = {
        id         : Date.now(),
        question   : question.trim(),
        reponse    : data.reponse,
        fallback   : data.fallback,
        duree_ms   : data.duree_ms ?? (Date.now() - t0),
        ts         : new Date().toLocaleTimeString('fr-FR'),
      }
      setResponse(entry)
      setHistory(h => [entry, ...h.slice(0, 9)])
    } catch (e) {
      const entry = {
        id       : Date.now(),
        question : question.trim(),
        reponse  : null,
        fallback : true,
        erreur   : e.message,
        ts       : new Date().toLocaleTimeString('fr-FR'),
      }
      setResponse(entry)
      setHistory(h => [entry, ...h.slice(0, 9)])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleGenerate()
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-lg font-semibold">Tester COR</h2>

      {/* Formulaire */}
      <div className="card space-y-4">
        <div>
          <label className="label">Question juridique</label>
          <textarea
            ref={textareaRef}
            className="input resize-none h-28"
            placeholder="Ex : Quelles sont les conditions de licenciement au Cameroun ?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <p className="text-xs text-gray-600 mt-1">Ctrl+Entrée pour envoyer</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="label">Pays / Juridiction</label>
            <select
              className="input"
              value={pays}
              onChange={e => setPays(e.target.value)}
            >
              {PAYS_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Température — {temperature.toFixed(1)}</label>
            <input
              type="range" min="0.1" max="2.0" step="0.1"
              value={temperature}
              onChange={e => setTemperature(parseFloat(e.target.value))}
              className="w-full accent-orange-500 mt-2"
            />
          </div>
          <div>
            <label className="label">Tokens max — {maxTokens}</label>
            <input
              type="range" min="30" max="300" step="10"
              value={maxTokens}
              onChange={e => setMaxTokens(parseInt(e.target.value))}
              className="w-full accent-orange-500 mt-2"
            />
          </div>
        </div>

        <button
          className="btn-primary w-full"
          onClick={handleGenerate}
          disabled={loading || !question.trim()}
        >
          {loading ? 'Génération en cours...' : 'Générer une réponse'}
        </button>
      </div>

      {/* Réponse courante */}
      {response && (
        <div className={`card ${response.fallback ? 'border-yellow-800' : 'border-dark-500'}`}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-gray-300">Réponse</span>
            <div className="flex gap-2 items-center">
              {response.fallback
                ? <span className="text-xs text-yellow-500 bg-yellow-900/30 px-2 py-0.5 rounded-full">Fallback</span>
                : <span className="text-xs text-green-400 bg-green-900/30 px-2 py-0.5 rounded-full">COR</span>
              }
              {response.duree_ms && (
                <span className="text-xs text-gray-500">{response.duree_ms} ms</span>
              )}
            </div>
          </div>

          {response.erreur && (
            <p className="text-red-400 text-sm">{response.erreur}</p>
          )}
          {response.reponse ? (
            <p className="text-gray-200 leading-relaxed whitespace-pre-wrap text-sm">{response.reponse}</p>
          ) : !response.erreur && (
            <p className="text-gray-500 text-sm italic">Aucune réponse générée — le modèle n'est peut-être pas encore entraîné.</p>
          )}
        </div>
      )}

      {/* Historique */}
      {history.length > 1 && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Historique récent ({history.length})</h3>
          <div className="space-y-2">
            {history.slice(1).map(h => (
              <div
                key={h.id}
                className="bg-dark-600 rounded-lg p-3 cursor-pointer hover:bg-dark-500 transition-colors"
                onClick={() => { setQuestion(h.question); setResponse(h) }}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs text-gray-500">{h.ts}</span>
                  <span className={`text-xs ${h.fallback ? 'text-yellow-500' : 'text-green-400'}`}>
                    {h.fallback ? 'fallback' : `${h.duree_ms}ms`}
                  </span>
                </div>
                <p className="text-sm text-gray-300 truncate">{h.question}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
