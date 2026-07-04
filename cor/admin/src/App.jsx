import { useState } from 'react'
import TabDashboard  from './tabs/TabDashboard.jsx'
import TabTest       from './tabs/TabTest.jsx'
import TabDocuments  from './tabs/TabDocuments.jsx'
import TabTraining   from './tabs/TabTraining.jsx'

const TABS = [
  { id: 'dashboard',  label: 'Dashboard' },
  { id: 'test',       label: 'Tester COR' },
  { id: 'documents',  label: 'Documents' },
  { id: 'training',   label: 'Entraînement' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  return (
    <div className="min-h-screen bg-dark-900 text-gray-100 font-sans flex flex-col">
      {/* Header */}
      <header className="border-b border-dark-500 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-orange-500 flex items-center justify-center font-bold text-sm text-white">
            C
          </div>
          <span className="font-semibold text-lg tracking-tight">COR Admin</span>
          <span className="text-xs text-gray-500 ml-1">Droit africain francophone</span>
        </div>
        <div className="text-xs text-gray-500">
          {import.meta.env.VITE_COR_URL || 'http://localhost:5000'}
        </div>
      </header>

      {/* Tabs */}
      <nav className="border-b border-dark-500 px-6 flex gap-6">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`py-3 text-sm ${activeTab === t.id ? 'tab-active' : 'tab-inactive'}`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 p-6 overflow-auto">
        {activeTab === 'dashboard' && <TabDashboard />}
        {activeTab === 'test'      && <TabTest />}
        {activeTab === 'documents' && <TabDocuments />}
        {activeTab === 'training'  && <TabTraining />}
      </main>
    </div>
  )
}
