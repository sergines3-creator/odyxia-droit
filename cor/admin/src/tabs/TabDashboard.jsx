import { useState, useEffect, useCallback } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { getHealth, getInfo, getRagStats } from '../api.js'

function StatCard({ label, value, sub }) {
  return (
    <div className="card flex flex-col gap-1">
      <span className="text-xs text-gray-500 uppercase tracking-wide">{label}</span>
      <span className="text-2xl font-semibold text-white">{value}</span>
      {sub && <span className="text-xs text-gray-500">{sub}</span>}
    </div>
  )
}

export default function TabDashboard() {
  const [health, setHealth]   = useState(null)
  const [info,   setInfo]     = useState(null)
  const [stats,  setStats]    = useState(null)
  const [error,  setError]    = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([
        getHealth().catch(() => null),
        getRagStats().catch(() => null),
      ])
      setHealth(h)
      setStats(s)
      if (h?.modele_charge) {
        const i = await getInfo().catch(() => null)
        setInfo(i)
      }
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [load])

  // Préparer les données pour le graphique répartition par pays
  const paysDonnees = stats?.par_pays
    ? Object.entries(stats.par_pays).map(([k, v]) => ({ pays: k.replace(/[\[\]]/g, ''), docs: v }))
    : []

  const domaineDonnees = stats?.par_domaine
    ? Object.entries(stats.par_domaine).map(([k, v]) => ({ domaine: k.replace(/_/g, ' '), docs: v }))
    : []

  if (loading) return <div className="text-gray-500 text-sm">Chargement...</div>

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Vue d'ensemble</h2>

      {error && (
        <div className="card border-red-800 bg-red-900/20 text-red-400 text-sm">
          Impossible de joindre le serveur COR : {error}
        </div>
      )}

      {/* Statut serveur */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Statut serveur"
          value={health ? (health.status === 'ok' ? 'En ligne' : 'Erreur') : 'Hors ligne'}
          sub={health?.modele_charge ? 'Modèle chargé' : 'Mode fallback'}
        />
        <StatCard
          label="Documents RAG"
          value={stats?.nb_documents ?? '—'}
          sub={`${stats?.nb_chunks_total ?? 0} chunks indexés`}
        />
        <StatCard
          label="Paramètres"
          value={info?.nb_parametres ? `${(info.nb_parametres / 1e6).toFixed(1)}M` : '—'}
          sub={info ? `${info.config?.vocab_size ?? '—'} tokens vocab` : 'Modèle absent'}
        />
        <StatCard
          label="Embedding"
          value="MiniLM"
          sub={stats?.modele_embedding?.split('/').pop() ?? 'paraphrase-multilingual'}
        />
      </div>

      {/* Graphiques répartition */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {paysDonnees.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-medium text-gray-300 mb-4">Documents par pays</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={paysDonnees} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="pays" tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1a1a', border: '1px solid #2e2e2e', borderRadius: 8 }}
                  labelStyle={{ color: '#f3f4f6' }}
                />
                <Bar dataKey="docs" radius={[4, 4, 0, 0]}>
                  {paysDonnees.map((_, i) => (
                    <Cell key={i} fill="#f55e29" fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {domaineDonnees.length > 0 && (
          <div className="card">
            <h3 className="text-sm font-medium text-gray-300 mb-4">Documents par domaine</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={domaineDonnees} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="domaine" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#1a1a1a', border: '1px solid #2e2e2e', borderRadius: 8 }}
                  labelStyle={{ color: '#f3f4f6' }}
                />
                <Bar dataKey="docs" radius={[4, 4, 0, 0]}>
                  {domaineDonnees.map((_, i) => (
                    <Cell key={i} fill="#6366f1" fillOpacity={0.8} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Infos modèle */}
      {info && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Informations modèle</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {Object.entries(info.config || {}).map(([k, v]) => (
              <div key={k} className="bg-dark-600 rounded-lg p-3">
                <div className="text-gray-500 text-xs mb-1">{k}</div>
                <div className="text-gray-200 font-medium">{String(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
