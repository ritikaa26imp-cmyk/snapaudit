import { useEffect, useState } from 'react';
import { getPolicyCategories } from '../api.js';
import { theme } from '../theme.js';

const ATTRS = ['colour', 'design', 'category', 'quantity'];

export default function PolicyPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data: d } = await getPolicyCategories();
        setData(d);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const categories = data?.categories || {};
  const vis = data?.visibility_definitions || {};

  return (
    <div>
      <div
        style={{
          background: '#eff6ff',
          border: '1px solid #bfdbfe',
          color: '#1e3a8a',
          padding: 16,
          borderRadius: 10,
          fontSize: 14,
          marginBottom: 24,
          boxShadow: theme.cardShadowSubtle,
        }}
      >
        Policies are edited via <code style={{ background: '#dbeafe', padding: '2px 6px', borderRadius: 4 }}>categories.yaml</code> and take effect on the next request.
      </div>

      <h1 style={{ ...theme.pageTitle, marginBottom: 18 }}>Category policies</h1>

      {loading && <p style={{ color: '#64748b' }}>Loading policies…</p>}
      {error && <p style={{ color: '#b91c1c' }}>{error}</p>}

      {data && (
        <>
          <section style={{ marginBottom: 28 }}>
            <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Visibility definitions</h2>
            <ul style={{ margin: 0, paddingLeft: 20, color: '#334155', fontSize: 14 }}>
              {Object.entries(vis).map(([k, v]) => (
                <li key={k} style={{ marginBottom: 6 }}>
                  <strong>{k}</strong>: {v}
                </li>
              ))}
            </ul>
          </section>

          {Object.entries(categories).map(([name, rules]) => (
            <details
              key={name}
              style={{
                marginBottom: 14,
                border: '1px solid #e2e8f0',
                borderRadius: 12,
                background: '#fff',
                boxShadow: theme.cardShadowSubtle,
              }}
            >
              <summary
                style={{
                  padding: '14px 18px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 15,
                  color: '#0f172a',
                }}
              >
                {name}
              </summary>
              <div style={{ padding: '0 18px 18px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th style={th}>Attribute</th>
                      <th style={th}>match</th>
                      <th style={th}>mismatch</th>
                      <th style={th}>cant_say</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ATTRS.map((attr) => {
                      const block = rules?.[attr];
                      return (
                        <tr key={attr} style={{ borderTop: '1px solid #e2e8f0' }}>
                          <td style={td}>{attr}</td>
                          <td style={td}>{block?.match ?? '—'}</td>
                          <td style={td}>{block?.mismatch ?? '—'}</td>
                          <td style={td}>{block?.cant_say ?? '—'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </details>
          ))}
        </>
      )}
    </div>
  );
}

const th = { padding: '8px 10px', textAlign: 'left', color: '#475569' };
const td = { padding: '8px 10px', color: '#334155', verticalAlign: 'top' };
