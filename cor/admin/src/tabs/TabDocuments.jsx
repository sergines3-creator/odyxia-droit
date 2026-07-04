import { useState, useEffect, useCallback, useRef } from 'react'
import { getRagDocuments, deleteRagDoc, addRagDocument, addRagPdf } from '../api.js'

const PAYS_OPTIONS = ['[CM]', '[GA]', '[BJ]', '[CI]', 'OHADA', 'CEMAC', 'UEMOA', 'inconnu']
const DOMAINE_OPTIONS = [
  'general', 'droit_travail', 'droit_commercial', 'droit_penal',
  'droit_ohada', 'procedure_civile', 'droit_fiscal', 'droit_administratif',
]

export default function TabDocuments() {
  const [documents,   setDocuments]  = useState([])
  const [loading,     setLoading]    = useState(true)
  const [uploading,   setUploading]  = useState(false)
  const [uploadProg,  setUploadProg] = useState('')
  const [error,       setError]      = useState(null)
  const [success,     setSuccess]    = useState(null)

  // Formulaire texte brut
  const [texte,   setTexte]   = useState('')
  const [pays,    setPays]    = useState('[CM]')
  const [domaine, setDomaine] = useState('general')
  const [source,  setSource]  = useState('')
  const [titre,   setTitre]   = useState('')

  // Upload PDF
  const [pdfFile,    setPdfFile]    = useState(null)
  const [pdfPays,    setPdfPays]    = useState('[CM]')
  const [pdfDomaine, setPdfDomaine] = useState('general')
  const [pdfSource,  setPdfSource]  = useState('')
  const [dragOver,   setDragOver]   = useState(false)
  const fileInputRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getRagDocuments()
      setDocuments(data.documents || [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function notify(msg, isError = false) {
    if (isError) setError(msg); else setSuccess(msg)
    setTimeout(() => { setError(null); setSuccess(null) }, 4000)
  }

  async function handleAddTexte(e) {
    e.preventDefault()
    if (!texte.trim() || uploading) return
    setUploading(true)
    setUploadProg('Indexation en cours...')
    try {
      const r = await addRagDocument(texte, { pays, domaine, source, titre })
      notify(`Document indexé : ${r.doc_id} (${r.nb_chunks} chunks)`)
      setTexte(''); setSource(''); setTitre('')
      load()
    } catch (e) {
      notify(e.message, true)
    } finally {
      setUploading(false); setUploadProg('')
    }
  }

  async function handleAddPdf(e) {
    e.preventDefault()
    if (!pdfFile || uploading) return
    setUploading(true)
    setUploadProg(`Extraction du PDF "${pdfFile.name}"...`)
    try {
      const r = await addRagPdf(pdfFile, { pays: pdfPays, domaine: pdfDomaine, source: pdfSource || pdfFile.name })
      notify(`PDF indexé : ${r.nb_pages} pages, ${r.nb_chunks} chunks`)
      setPdfFile(null); setPdfSource('')
      load()
    } catch (e) {
      notify(e.message, true)
    } finally {
      setUploading(false); setUploadProg('')
    }
  }

  async function handleDelete(docId) {
    if (!confirm('Supprimer ce document de la base vectorielle ?')) return
    try {
      await deleteRagDoc(docId)
      notify('Document supprimé')
      setDocuments(d => d.filter(x => x.doc_id !== docId))
    } catch (e) {
      notify(e.message, true)
    }
  }

  function handleDrop(e) {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file?.name.toLowerCase().endsWith('.pdf')) setPdfFile(file)
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Gestion des documents</h2>

      {error   && <div className="card border-red-800 bg-red-900/20 text-red-400 text-sm">{error}</div>}
      {success && <div className="card border-green-800 bg-green-900/20 text-green-400 text-sm">{success}</div>}
      {uploadProg && (
        <div className="card border-orange-800 bg-orange-900/10 text-orange-400 text-sm flex items-center gap-2">
          <span className="animate-spin">⟳</span> {uploadProg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Ajouter un texte brut */}
        <div className="card space-y-4">
          <h3 className="font-medium text-gray-200">Indexer un texte juridique</h3>
          <form onSubmit={handleAddTexte} className="space-y-3">
            <div>
              <label className="label">Texte juridique *</label>
              <textarea
                className="input resize-none h-32 text-sm"
                placeholder="Coller le texte de l'article, loi, jurisprudence..."
                value={texte}
                onChange={e => setTexte(e.target.value)}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Pays *</label>
                <select className="input text-sm" value={pays} onChange={e => setPays(e.target.value)}>
                  {PAYS_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Domaine</label>
                <select className="input text-sm" value={domaine} onChange={e => setDomaine(e.target.value)}>
                  {DOMAINE_OPTIONS.map(d => <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Source</label>
                <input className="input text-sm" placeholder="OHADA.com, JO 2023..." value={source} onChange={e => setSource(e.target.value)} />
              </div>
              <div>
                <label className="label">Titre</label>
                <input className="input text-sm" placeholder="Acte Uniforme OHADA..." value={titre} onChange={e => setTitre(e.target.value)} />
              </div>
            </div>
            <button className="btn-primary w-full" type="submit" disabled={uploading || !texte.trim()}>
              Indexer le texte
            </button>
          </form>
        </div>

        {/* Upload PDF */}
        <div className="card space-y-4">
          <h3 className="font-medium text-gray-200">Uploader un PDF</h3>
          <form onSubmit={handleAddPdf} className="space-y-3">
            {/* Zone drag & drop */}
            <div
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                dragOver ? 'border-orange-500 bg-orange-500/10' : 'border-dark-500 hover:border-dark-400'
              }`}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              {pdfFile ? (
                <div className="text-sm text-green-400">{pdfFile.name} ({(pdfFile.size / 1024).toFixed(0)} Ko)</div>
              ) : (
                <>
                  <div className="text-2xl mb-2 text-gray-600">📄</div>
                  <div className="text-sm text-gray-500">Glisser-déposer un PDF ici</div>
                  <div className="text-xs text-gray-600 mt-1">ou cliquer pour sélectionner</div>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file" accept=".pdf" className="hidden"
                onChange={e => setPdfFile(e.target.files[0] || null)}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Pays *</label>
                <select className="input text-sm" value={pdfPays} onChange={e => setPdfPays(e.target.value)}>
                  {PAYS_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Domaine</label>
                <select className="input text-sm" value={pdfDomaine} onChange={e => setPdfDomaine(e.target.value)}>
                  {DOMAINE_OPTIONS.map(d => <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="label">Source</label>
              <input className="input text-sm" placeholder="OHADA.com, JO Cameroun..." value={pdfSource} onChange={e => setPdfSource(e.target.value)} />
            </div>
            <button className="btn-primary w-full" type="submit" disabled={uploading || !pdfFile}>
              Indexer le PDF
            </button>
          </form>
        </div>
      </div>

      {/* Liste des documents */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-medium text-gray-200">Documents indexés ({documents.length})</h3>
          <button className="btn-secondary text-sm" onClick={load} disabled={loading}>
            {loading ? 'Chargement...' : 'Actualiser'}
          </button>
        </div>

        {documents.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-8">Aucun document indexé — commencer par ajouter un texte ou un PDF.</p>
        ) : (
          <div className="space-y-2">
            {documents.map(doc => (
              <div key={doc.doc_id} className="bg-dark-600 rounded-lg p-3 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="badge-pays">{doc.pays}</span>
                    <span className="text-xs text-gray-500">{doc.domaine?.replace(/_/g, ' ')}</span>
                    <span className="text-xs text-gray-600">{doc.nb_chunks} chunks</span>
                  </div>
                  <p className="text-sm text-gray-200 truncate">{doc.titre || doc.source || doc.doc_id}</p>
                  <p className="text-xs text-gray-600 mt-0.5">{doc.date_ajout?.slice(0, 10)}</p>
                </div>
                <button className="btn-danger flex-shrink-0" onClick={() => handleDelete(doc.doc_id)}>
                  Supprimer
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
