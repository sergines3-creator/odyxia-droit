import { useState, useEffect, useCallback, useRef } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { getTrainStatus, startTrain, stopTrain } from '../api.js'

export default function TabTraining() {
  const [status,   setStatus]   = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [error,    setError]    = useState(null)
  const [success,  setSuccess]  = useState(null)
  const logRef = useRef(null)

  // Paramètres de lancement
  const [phase,    setPhase]    = useState('finetune')
  const [epochs,   setEpochs]   = useState(3)
  const [lr,       setLr]       = useState(0.0001)
  const [batch,    setBatch]    = useState(8)

  const load = useCallback(async () => {
    try {
      const data = await getTrainStatus()
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 2000)
    return () => clearInterval(id)
  }, [load])

  // Auto-scroll du log vers le bas
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [status?.dernier_log])

  function notify(msg, isError = false) {
    if (isError) setError(msg); else setSuccess(msg)
    setTimeout(() => { setError(null); setSuccess(null) }, 5000)
  }

  async function handleStart() {
    setStarting(true)
    try {
      await startTrain({ phase, epochs, lr, batch_size: batch })
      notify(`Entraînement ${phase} démarré (${epochs} epochs, lr=${lr})`)
      load()
    } catch (e) {
      notify(e.message, true)
    } finally {
      setStarting(false)
    }
  }

  async function handleStop() {
    setStopping(true)
    try {
      await stopTrain()
      notify('Arrêt demandé — en attente de la fin de l\'étape courante')
      load()
    } catch (e) {
      notify(e.message, true)
    } finally {
      setStopping(false)
    }
  }

  // Préparer données courbes de loss
  const metrics = status?.metrics || {}
  const phase_data = metrics[phase === 'finetune' ? 'finetune' : 'pretrain'] || {}
  const lossData = (phase_data.steps || []).map((s, i) => ({
    step : s.step,
    loss : s.loss,
    lr   : s.lr,
  })).filter(d => d.loss != null)

  const actif    = status?.actif ?? false
  const dureeMin = status?.duree_s ? Math.floor(status.duree_s / 60) : 0
  const dureeSec = status?.duree_s ? status.duree_s % 60 : 0

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Entraînement</h2>

      {error   && <div className="card border-red-800 bg-red-900/20 text-red-400 text-sm">{error}</div>}
      {success && <div className="card border-green-800 bg-green-900/20 text-green-400 text-sm">{success}</div>}

      {/* État actuel */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${actif ? 'bg-orange-500 animate-pulse' : 'bg-gray-600'}`} />
            <span className="font-medium">{actif ? 'Entraînement en cours' : 'Inactif'}</span>
            {actif && (
              <span className="text-sm text-gray-500">
                {dureeMin}m {dureeSec}s
              </span>
            )}
          </div>
          {actif && (
            <button className="btn-danger" onClick={handleStop} disabled={stopping}>
              {stopping ? 'Arrêt...' : 'Arrêter'}
            </button>
          )}
        </div>
        {status?.dernier_log && (
          <p className="text-sm text-gray-400 mt-2 font-mono">{status.dernier_log}</p>
        )}
        {actif && status?.config && (
          <div className="flex gap-4 mt-3 text-xs text-gray-500">
            <span>Phase : {status.config.phase}</span>
            <span>Epochs : {status.config.epochs}</span>
            <span>LR : {status.config.lr}</span>
            <span>Batch : {status.config.batch_size}</span>
          </div>
        )}
      </div>

      {/* Lancer un entraînement */}
      {!actif && (
        <div className="card space-y-4">
          <h3 className="font-medium text-gray-200">Lancer un entraînement</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="label">Phase</label>
              <select className="input text-sm" value={phase} onChange={e => setPhase(e.target.value)}>
                <option value="pretrain">Pré-entraînement</option>
                <option value="finetune">Fine-tuning</option>
              </select>
            </div>
            <div>
              <label className="label">Epochs</label>
              <input
                type="number" min="1" max="100"
                className="input text-sm"
                value={epochs}
                onChange={e => setEpochs(Math.max(1, parseInt(e.target.value) || 1))}
              />
            </div>
            <div>
              <label className="label">Learning Rate</label>
              <input
                type="number" step="0.00001" min="0.000001" max="0.01"
                className="input text-sm"
                value={lr}
                onChange={e => setLr(parseFloat(e.target.value) || 1e-4)}
              />
            </div>
            <div>
              <label className="label">Batch Size</label>
              <input
                type="number" min="1" max="128"
                className="input text-sm"
                value={batch}
                onChange={e => setBatch(Math.max(1, parseInt(e.target.value) || 8))}
              />
            </div>
          </div>
          <button
            className="btn-primary"
            onClick={handleStart}
            disabled={starting}
          >
            {starting ? 'Démarrage...' : `Lancer le ${phase === 'finetune' ? 'fine-tuning' : 'pré-entraînement'}`}
          </button>
        </div>
      )}

      {/* Courbe de loss */}
      {lossData.length > 1 && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-4">Courbe de loss ({phase})</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={lossData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="#242424" strokeDasharray="3 3" />
              <XAxis dataKey="step" tick={{ fill: '#9ca3af', fontSize: 11 }} label={{ value: 'Step', position: 'insideBottom', fill: '#6b7280', offset: -2 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#1a1a1a', border: '1px solid #2e2e2e', borderRadius: 8 }}
                labelStyle={{ color: '#f3f4f6' }}
                formatter={(v) => [v?.toFixed(4), 'Loss']}
              />
              <Line
                type="monotone" dataKey="loss" stroke="#f55e29"
                strokeWidth={2} dot={false} activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Statistiques du corpus */}
      {metrics.config_entrainement && Object.keys(metrics.config_entrainement).length > 0 && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Statistiques corpus</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {Object.entries(metrics.config_entrainement).map(([k, v]) => (
              <div key={k} className="bg-dark-600 rounded-lg p-3">
                <div className="text-gray-500 text-xs mb-1">{k}</div>
                <div className="text-gray-200 font-medium">{String(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Log entraînement */}
      {(metrics.errors?.length > 0 || actif) && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-3">
            Logs {metrics.errors?.length > 0 && `(${metrics.errors.length} erreurs)`}
          </h3>
          <div
            ref={logRef}
            className="bg-dark-800 rounded-lg p-3 font-mono text-xs text-gray-400 h-40 overflow-y-auto space-y-1"
          >
            {(metrics.errors || []).map((e, i) => (
              <div key={i} className="text-red-400">[ERREUR] {e.message || JSON.stringify(e)}</div>
            ))}
            {actif && status?.dernier_log && (
              <div className="text-orange-400 animate-pulse">&gt; {status.dernier_log}</div>
            )}
            {!actif && (metrics.errors?.length === 0) && (
              <div className="text-gray-600">Aucune erreur enregistrée.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
