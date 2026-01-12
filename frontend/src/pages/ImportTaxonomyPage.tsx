import { useState } from 'react'
import { importTaxonomy } from '../api/client'
import type { ImportTaxonomyResponse } from '../api/types'

export function ImportTaxonomyPage() {
  const [jsonText, setJsonText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<ImportTaxonomyResponse | null>(null)

  const handleImport = async () => {
    setError(null)
    setSuccess(null)
    setLoading(true)

    try {
      // Validate JSON
      let payload: any
      try {
        payload = JSON.parse(jsonText)
      } catch (e) {
        throw new Error(`Invalid JSON: ${e instanceof Error ? e.message : 'Unknown error'}`)
      }

      // Call API
      const response = await importTaxonomy(payload)
      setSuccess(response)
      setJsonText('')
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error'
      
      // Try to extract more detail from API errors
      if (errorMsg.includes('401') || errorMsg.includes('Unauthorized')) {
        setError('❌ Unauthorized. Admin access required.')
      } else if (errorMsg.includes('403') || errorMsg.includes('Forbidden')) {
        setError('❌ Access Denied. Admin access required.')
      } else if (errorMsg.includes('422')) {
        setError(`❌ Validation Error: ${errorMsg.split(':')[1]?.trim() || 'Invalid request format'}`)
      } else {
        setError(`❌ Import failed: ${errorMsg}`)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>📦 Import Taxonomy</h1>
      <p style={{ color: '#64748b', marginBottom: '1.5rem' }}>
        Paste a JSON taxonomy structure below and click Import. Upsert is idempotent by code field.
      </p>

      {/* JSON Input */}
      <div style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '0.5rem' }}>
          Taxonomy JSON:
        </label>
        <textarea
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          placeholder={`{
  "group": {"name": "Tech", "code": "TECH"},
  "subgroups": [
    {
      "name": "Large Cap",
      "code": "TECH-LC",
      "categories": [
        {
          "name": "Software",
          "code": "TECH-LC-SW",
          "asset_type": "equity",
          "assets": [
            {"symbol": "AAPL", "name": "Apple Inc"},
            {"symbol": "MSFT", "name": "Microsoft"}
          ]
        }
      ]
    }
  ]
}`}
          style={{
            width: '100%',
            minHeight: '300px',
            padding: '1rem',
            border: '1px solid #cbd5e1',
            borderRadius: '6px',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            fontColor: '#1e293b',
          }}
          disabled={loading}
        />
        <div style={{ fontSize: '0.875rem', color: '#64748b', marginTop: '0.5rem' }}>
          {jsonText.length} characters
        </div>
      </div>

      {/* Import Button */}
      <div style={{ marginBottom: '1.5rem' }}>
        <button
          onClick={handleImport}
          disabled={loading || !jsonText.trim()}
          style={{
            padding: '0.75rem 2rem',
            background: loading || !jsonText.trim() ? '#cbd5e1' : '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: loading || !jsonText.trim() ? 'not-allowed' : 'pointer',
            fontSize: '1rem',
            fontWeight: 'bold',
            transition: 'background 0.2s',
          }}
          onMouseEnter={(e) => {
            if (!loading && jsonText.trim()) {
              e.currentTarget.style.background = '#2563eb'
            }
          }}
          onMouseLeave={(e) => {
            if (!loading && jsonText.trim()) {
              e.currentTarget.style.background = '#3b82f6'
            }
          }}
        >
          {loading ? '⏳ Importing...' : '📤 Import'}
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div
          style={{
            padding: '1rem',
            background: '#fee2e2',
            border: '1px solid #fca5a5',
            borderRadius: '6px',
            marginBottom: '1.5rem',
            color: '#991b1b',
          }}
        >
          {error}
        </div>
      )}

      {/* Success Display */}
      {success && (
        <div
          style={{
            padding: '1rem',
            background: '#dcfce7',
            border: '1px solid #86efac',
            borderRadius: '6px',
            marginBottom: '1.5rem',
            color: '#166534',
          }}
        >
          <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>✅ Import Successful!</div>
          <div style={{ fontSize: '0.875rem', lineHeight: '1.6' }}>
            <div>📊 Groups: {success.groups_created} created, {success.groups_updated} updated</div>
            <div>📁 Subgroups: {success.subgroups_created} created, {success.subgroups_updated} updated</div>
            <div>🏷️ Categories: {success.categories_created} created, {success.categories_updated} updated</div>
            <div>💰 Assets: {success.assets_created} created, {success.assets_updated} updated</div>
            <div>🔗 Links: {success.links_created} created</div>
            {success.errors.length > 0 && (
              <div style={{ marginTop: '0.5rem', color: '#b91c1c' }}>
                ⚠️ Errors: {success.errors.join('; ')}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Example */}
      <div style={{ marginTop: '2rem', padding: '1rem', background: '#f1f5f9', borderRadius: '6px' }}>
        <h3 style={{ marginTop: 0 }}>📋 JSON Format Guide</h3>
        <p style={{ fontSize: '0.875rem', color: '#475569', marginBottom: '0.5rem' }}>
          Your JSON should have:
        </p>
        <ul style={{ fontSize: '0.875rem', color: '#475569', margin: 0 }}>
          <li><code>group</code>: Required, with name and code</li>
          <li><code>subgroups[]</code>: Optional array of subgroups</li>
          <li><code>categories[]</code>: Inside each subgroup</li>
          <li><code>assets[]</code>: Inside each category</li>
          <li>Each level must have <code>name</code> and <code>code</code> fields</li>
        </ul>
      </div>
    </div>
  )
}
