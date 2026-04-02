import { useEffect, useState } from 'react';
import { exportAudits, getAudit, getAudits } from '../api.js';
import { labelForComparisonType } from '../comparisonLabels.js';
import { theme } from '../theme.js';

const inputStyle = {
  padding: 8,
  borderRadius: 6,
  border: '1px solid #cbd5e1',
  fontSize: 13,
};

export default function AuditLogPage() {
  const [filters, setFilters] = useState({
    from_date: '',
    to_date: '',
    category: '',
    verdict: '',
    confidence: '',
  });
  const [page, setPage] = useState(1);
  const perPage = 50;
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [panelId, setPanelId] = useState(null);
  const [panelRow, setPanelRow] = useState(null);

  const load = async (p = page) => {
    setLoading(true);
    setErr(null);
    try {
      const { data: d } = await getAudits({
        ...filters,
        page: p,
        per_page: perPage,
      });
      setData(d);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(page);
  }, [page]);

  const applyFilters = () => {
    setPage(1);
    load(1);
  };

  const doExport = async () => {
    try {
      const res = await exportAudits(filters);
      const blob = res.data;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'snapaudit_export.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.message || 'Export failed');
    }
  };

  const openRow = async (row) => {
    setPanelId(row.audit_id);
    setPanelRow(row);
    try {
      const { data: full } = await getAudit(row.audit_id);
      setPanelRow(full);
    } catch {
      /* keep table row */
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
        <h1 style={{ ...theme.pageTitle, margin: 0 }}>Audit log</h1>
        <button
          type="button"
          onClick={doExport}
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            border: '1px solid #cbd5e1',
            background: '#fff',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Export CSV
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: 14,
          marginBottom: 18,
          alignItems: 'end',
        }}
      >
        <label style={{ fontSize: 12, color: '#64748b' }}>
          From date
          <input
            type="text"
            placeholder="ISO e.g. 2025-01-01"
            value={filters.from_date}
            onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))}
            style={{ ...inputStyle, width: '100%', marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: '#64748b' }}>
          To date
          <input
            type="text"
            placeholder="ISO e.g. 2025-12-31"
            value={filters.to_date}
            onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))}
            style={{ ...inputStyle, width: '100%', marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: '#64748b' }}>
          Category
          <input
            value={filters.category}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
            style={{ ...inputStyle, width: '100%', marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: '#64748b' }}>
          Verdict
          <input
            value={filters.verdict}
            onChange={(e) => setFilters((f) => ({ ...f, verdict: e.target.value }))}
            style={{ ...inputStyle, width: '100%', marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: '#64748b' }}>
          Confidence
          <input
            value={filters.confidence}
            onChange={(e) => setFilters((f) => ({ ...f, confidence: e.target.value }))}
            style={{ ...inputStyle, width: '100%', marginTop: 4 }}
          />
        </label>
        <button
          type="button"
          onClick={applyFilters}
          style={{
            padding: '10px 16px',
            borderRadius: 8,
            border: 'none',
            background: '#0f172a',
            color: '#fff',
            fontWeight: 600,
            cursor: 'pointer',
            height: 38,
          }}
        >
          Apply
        </button>
      </div>

      {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
      {loading ? (
        <p style={{ color: '#64748b' }}>Loading…</p>
      ) : (
        <>
          <div
            style={{
              overflowX: 'auto',
              border: '1px solid #e2e8f0',
              borderRadius: 12,
              background: '#fff',
              boxShadow: theme.cardShadowSubtle,
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f8fafc', textAlign: 'left' }}>
                  <th style={th}>Session</th>
                  <th style={th}>Comparison</th>
                  <th style={th}>Category</th>
                  <th style={th}>Verdict</th>
                  <th style={th}>Confidence</th>
                  <th style={th}>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr
                    key={row.audit_id}
                    onClick={() => openRow(row)}
                    style={{
                      borderTop: '1px solid #e2e8f0',
                      cursor: 'pointer',
                      background: panelId === row.audit_id ? '#f1f5f9' : '#fff',
                    }}
                  >
                    <td style={td}>{row.session_id}</td>
                    <td style={td}>{labelForComparisonType(row.comparison_type)}</td>
                    <td style={td}>{row.category_detected || row.category_hint || '—'}</td>
                    <td style={td}>{row.verdict}</td>
                    <td style={td}>{row.confidence}</td>
                    <td style={td}>{row.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 18, display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: '#64748b' }}>
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #cbd5e1' }}
            >
              Prev
            </button>
            <span>
              Page {page} of {Math.max(1, Math.ceil(data.total / perPage))} ({data.total} total)
            </span>
            <button
              type="button"
              disabled={page * perPage >= data.total}
              onClick={() => setPage((p) => p + 1)}
              style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #cbd5e1' }}
            >
              Next
            </button>
          </div>
        </>
      )}

      {panelRow && (
        <div
          role="presentation"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.25)',
            zIndex: 19,
          }}
          onClick={() => {
            setPanelId(null);
            setPanelRow(null);
          }}
        />
      )}
      {panelRow && (
        <aside
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            width: 'min(420px, 100vw)',
            height: '100vh',
            background: '#fff',
            boxShadow: '-4px 0 24px rgba(0,0,0,0.08)',
            padding: 20,
            overflowY: 'auto',
            zIndex: 20,
            borderLeft: '1px solid #e2e8f0',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <strong style={{ fontSize: 16 }}>Audit detail</strong>
            <button
              type="button"
              onClick={() => {
                setPanelId(null);
                setPanelRow(null);
              }}
              style={{ border: 'none', background: 'none', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}
            >
              ×
            </button>
          </div>
          <dl style={{ fontSize: 13, color: '#334155' }}>
            {Object.entries(panelRow).map(([k, v]) => (
              <div key={k} style={{ marginBottom: 10 }}>
                <dt style={{ fontWeight: 600, color: '#64748b', marginBottom: 2 }}>{k}</dt>
                <dd style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}
                </dd>
              </div>
            ))}
          </dl>
        </aside>
      )}
    </div>
  );
}

const th = { padding: '12px 14px', fontWeight: 600, color: '#475569' };
const td = { padding: '12px 14px', color: '#334155' };
