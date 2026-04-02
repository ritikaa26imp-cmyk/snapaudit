import { useState } from 'react';
import { checkVisibility } from '../api.js';
import { theme } from '../theme.js';

const VIS_HELP = {
  visible: 'Product occupies most of the frame and key attributes are clearly discernible.',
  partial: 'Product is present but key attributes are partially obscured.',
  not_visible:
    'Product cannot be assessed — only packaging, blank surface, or image too dark/blurred.',
};

export default function VisibilityPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const onFile = (f) => {
    if (!f || !f.type.startsWith('image/')) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError(null);
  };

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const dataUrl = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = reject;
        r.readAsDataURL(file);
      });
      const { data } = await checkVisibility(dataUrl);
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.message || e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={theme.pageTitle}>Visibility check</h1>
      <p style={theme.pageSubtitle}>
        Upload one product image. Pass 1 returns a visibility label for that frame (with internal placeholders for the second set).
      </p>

      <div
        style={{
          border: '2px dashed #cbd5e1',
          borderRadius: 12,
          padding: 28,
          maxWidth: 420,
          background: '#f8fafc',
          textAlign: 'center',
          boxShadow: theme.cardShadowSubtle,
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onFile(e.dataTransfer.files[0]);
        }}
      >
        {preview ? (
          <img src={preview} alt="" style={{ maxWidth: '100%', maxHeight: 220, borderRadius: 8 }} />
        ) : (
          <p style={{ color: '#64748b', fontSize: 14 }}>Drag one image here or choose a file</p>
        )}
        <label style={{ display: 'inline-block', marginTop: 12, cursor: 'pointer' }}>
          <span
            style={{
              padding: '8px 16px',
              background: '#0f172a',
              color: '#fff',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
            }}
          >
            Choose image
          </span>
          <input type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onFile(e.target.files?.[0])} />
        </label>
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={!file || loading}
        style={{
          marginTop: 20,
          padding: '12px 22px',
          borderRadius: 8,
          border: 'none',
          background: file && !loading ? '#0f172a' : '#94a3b8',
          color: '#fff',
          fontWeight: 600,
          cursor: file && !loading ? 'pointer' : 'not-allowed',
        }}
      >
        {loading ? 'Running…' : 'Submit'}
      </button>

      {error && (
        <p style={{ color: '#b91c1c', marginTop: 12 }}>{error}</p>
      )}

      {result && (
        <div
          style={{
            ...theme.verdictCard,
            maxWidth: 520,
          }}
        >
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>Result</div>
          <div
            style={{
              display: 'inline-block',
              padding: '8px 14px',
              borderRadius: 8,
              fontWeight: 700,
              fontSize: 16,
              background: '#e0e7ff',
              color: '#312e81',
              marginBottom: 12,
            }}
          >
            {result.visibility}
          </div>
          <p style={{ fontSize: 14, color: '#475569', lineHeight: 1.6, marginBottom: 12 }}>
            {VIS_HELP[result.visibility] || 'See policy for visibility definitions.'}
          </p>
          <div style={{ fontSize: 13, color: '#64748b' }}>
            Model: <strong style={{ color: '#334155' }}>{result.model_used}</strong>
            {' · '}
            Latency: <strong style={{ color: '#334155' }}>{result.latency_ms} ms</strong>
          </div>
        </div>
      )}
    </div>
  );
}
