import { useEffect, useMemo, useRef, useState } from 'react';
import { compareImages } from '../api.js';
import { COMPARISON_TYPE_OPTIONS, humanizeVerdictCopy } from '../comparisonLabels.js';
import { theme } from '../theme.js';

const zoneStyle = {
  flex: 1,
  minWidth: 280,
  border: '2px dashed #cbd5e1',
  borderRadius: 12,
  padding: 22,
  background: '#f8fafc',
  minHeight: 200,
  boxShadow: theme.cardShadowSubtle,
};

const thumbWrap = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 10,
  marginTop: 12,
};

const thumbBox = { position: 'relative', width: 88, height: 88 };

const thumbImg = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  borderRadius: 8,
  border: '1px solid #e2e8f0',
};

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

let idSeq = 0;
function nextId() {
  idSeq += 1;
  return `img-${idSeq}`;
}

const CATEGORY_HINTS = [
  { value: 'auto', label: 'Auto' },
  { value: 'saree', label: 'Saree' },
  { value: 'kurti', label: 'Kurti' },
  { value: 'bag', label: 'Bag' },
  { value: 'cloth', label: 'Cloth' },
  { value: 'jewellery', label: 'Jewellery' },
  { value: 'watch', label: 'Watch' },
];

function attributePillColors(raw) {
  const v = String(raw ?? '').toLowerCase();
  if (v === 'same') return { bg: '#dcfce7', fg: '#166534' };
  if (v === 'different') return { bg: '#fee2e2', fg: '#991b1b' };
  if (v === 'cant_say') return { bg: '#e2e8f0', fg: '#64748b' };
  return { bg: '#f1f5f9', fg: '#334155' };
}

function AttributePill({ label, value }) {
  const { bg, fg } = attributePillColors(value);
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '7px 12px',
        borderRadius: 999,
        background: bg,
        fontSize: 13,
        color: fg,
      }}
    >
      <span style={{ fontWeight: 600, opacity: 0.85 }}>{label}</span>
      <span>{value ?? '—'}</span>
    </span>
  );
}

function verdictBadgeColors(verdict) {
  const v = String(verdict ?? '').toLowerCase();
  if (v === 'match') return { bg: '#dcfce7', fg: '#166534' };
  if (v === 'mismatch') return { bg: '#fee2e2', fg: '#991b1b' };
  if (v === 'inconclusive') return { bg: '#fef9c3', fg: '#854d0e' };
  return { bg: '#e2e8f0', fg: '#334155' };
}

function VerdictBadge({ verdict }) {
  const { bg, fg } = verdictBadgeColors(verdict);
  return (
    <span
      style={{
        padding: '7px 14px',
        borderRadius: 8,
        fontWeight: 600,
        fontSize: 13,
        background: bg,
        color: fg,
      }}
    >
      Verdict: {verdict ?? '—'}
    </span>
  );
}

function confidenceBadgeColors(confidence) {
  const c = String(confidence ?? '').toLowerCase();
  if (c === 'high') return { bg: '#dcfce7', fg: '#166534' };
  if (c === 'medium') return { bg: '#fef9c3', fg: '#854d0e' };
  if (c === 'low') return { bg: '#fee2e2', fg: '#991b1b' };
  return { bg: '#e2e8f0', fg: '#334155' };
}

function ConfidenceBadge({ confidence }) {
  const { bg, fg } = confidenceBadgeColors(confidence);
  return (
    <span
      style={{
        padding: '7px 14px',
        borderRadius: 8,
        fontWeight: 600,
        fontSize: 13,
        background: bg,
        color: fg,
      }}
    >
      Confidence: {confidence ?? '—'}
    </span>
  );
}

function ShortCircuitBadge({ children }) {
  return (
    <span
      style={{
        padding: '7px 14px',
        borderRadius: 8,
        fontWeight: 600,
        fontSize: 13,
        background: '#fef9c3',
        color: '#854d0e',
      }}
    >
      {children}
    </span>
  );
}

function SnapAuditAboutBanner() {
  const [open, setOpen] = useState(false);
  return (
    <div
      style={{
        marginBottom: 24,
        background: '#f0f4f8',
        border: '1px solid #e2e8f0',
        borderRadius: 10,
        padding: '14px 16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <p style={{ margin: 0, fontSize: 14, color: '#334155', lineHeight: 1.55, flex: '1 1 240px' }}>
          Open-source AI that compares reference catalog images with delivery or return photos to detect product swaps.
          Runs entirely on your machine.
        </p>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          style={{
            flexShrink: 0,
            padding: '8px 14px',
            fontSize: 14,
            fontWeight: 600,
            color: '#0f172a',
            background: '#fff',
            border: '1px solid #cbd5e1',
            borderRadius: 8,
            cursor: 'pointer',
          }}
        >
          {open ? 'Show less ↑' : 'Learn more ↓'}
        </button>
      </div>
      <div
        style={{
          maxHeight: open ? 3200 : 0,
          overflow: 'hidden',
          transition: 'max-height 0.45s ease',
        }}
      >
        <div
          style={{
            paddingTop: open ? 16 : 0,
            marginTop: open ? 16 : 0,
            borderTop: open ? '1px solid #e2e8f0' : 'none',
          }}
        >
          <h2 style={{ fontSize: 17, fontWeight: 700, color: '#0f172a', margin: '0 0 12px' }}>What is SnapAudit?</h2>
          <div style={{ fontSize: 14, color: '#334155', lineHeight: 1.65 }}>
            <p style={{ margin: '0 0 14px' }}>
              SnapAudit is an open-source AI tool that detects product swaps in e-commerce supply chains. It compares two
              sets of product images — a reference image from the catalog and an image of the product received by the user
              or returned by the user — and returns a structured verdict on whether the items match.
            </p>
            <p style={{ margin: '0 0 8px', fontWeight: 600, color: '#0f172a' }}>Built for two common fraud scenarios:</p>
            <p style={{ margin: '0 0 12px', paddingLeft: 4 }}>
              <span style={{ color: '#475569' }}>→</span> <strong>Return fraud:</strong> A buyer receives a genuine
              product, initiates a return, and sends back a different or damaged item. SnapAudit compares the catalog
              image against the image of the product returned by the user to flag mismatches before the refund is
              processed.
            </p>
            <p style={{ margin: '0 0 14px', paddingLeft: 4 }}>
              <span style={{ color: '#475569' }}>→</span> <strong>Delivery fraud:</strong> A seller ships the wrong
              product — either deliberately or by error. SnapAudit compares the catalog listing against the image of the
              product received by the user to catch substitutions at the doorstep.
            </p>
            <p style={{ margin: '0 0 14px' }}>
              The model evaluates four attributes independently: colour, design, category, and quantity — and returns a
              match, mismatch, or inconclusive verdict with a confidence score.
            </p>
            <p style={{ margin: 0 }}>
              Powered by open-source vision models (Qwen2.5-VL, Gemma3, LLaVA) running entirely on your local machine. No
              data leaves your device.
            </p>
          </div>
          <p
            style={{
              margin: '16px 0 0',
              paddingTop: 14,
              borderTop: '1px solid #e2e8f0',
              fontSize: 12,
              color: '#64748b',
            }}
          >
            Built with FastAPI · React · Ollama · SQLite · Open source on GitHub
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ComparisonPage() {
  const [set1, setSet1] = useState([]);
  const [set2, setSet2] = useState([]);
  const [sessionId, setSessionId] = useState('');
  const [comparisonType, setComparisonType] = useState('catalog_vs_icud');
  const [categoryHint, setCategoryHint] = useState('auto');
  const [userPrompt, setUserPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadStage, setLoadStage] = useState(1);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const set1Ref = useRef(set1);
  const set2Ref = useRef(set2);
  useEffect(() => {
    set1Ref.current = set1;
  }, [set1]);
  useEffect(() => {
    set2Ref.current = set2;
  }, [set2]);

  useEffect(() => {
    if (!loading) {
      setLoadStage(1);
      return undefined;
    }
    const t = setTimeout(() => setLoadStage(2), 1400);
    return () => clearTimeout(t);
  }, [loading]);

  const canSubmit = useMemo(
    () => sessionId.trim().length > 0 && set1.length >= 2 && set2.length >= 2 && set1.length <= 3 && set2.length <= 3,
    [sessionId, set1.length, set2.length],
  );

  /**
   * Add images to set 1 or 2 (never replace). Uses refs so `room` always reflects
   * the latest length (avoids stale closure from `set1`/`set2` in async handlers).
   * After decode, merge uses a functional update capped at 3 in case of races.
   */
  const addFiles = async (fileList, which) => {
    const list = Array.from(fileList).filter((f) => f.type.startsWith('image/'));
    if (list.length === 0) return;

    const setter = which === 1 ? setSet1 : setSet2;
    const prev = which === 1 ? set1Ref.current : set2Ref.current;
    const room = Math.max(0, 3 - prev.length);
    const take = list.slice(0, room);
    if (take.length === 0) return;

    const newItems = await Promise.all(
      take.map(async (file) => ({
        id: nextId(),
        preview: URL.createObjectURL(file),
        dataUrl: await fileToDataUrl(file),
      })),
    );

    setter((p) => {
      const cap = Math.max(0, 3 - p.length);
      return [...p, ...newItems.slice(0, cap)];
    });
  };

  /** File input: add then clear value so the same path can be chosen again. */
  const handleFileInputChange = (which) => async (e) => {
    const { files } = e.target;
    if (!files?.length) return;
    await addFiles(files, which);
    e.target.value = '';
  };

  const remove = (which, id) => {
    const setter = which === 1 ? setSet1 : setSet2;
    setter((prev) => {
      const row = prev.find((x) => x.id === id);
      if (row?.preview?.startsWith('blob:')) URL.revokeObjectURL(row.preview);
      return prev.filter((x) => x.id !== id);
    });
  };

  const run = async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const { data } = await compareImages({
        session_id: sessionId.trim(),
        comparison_type: comparisonType,
        category_hint: categoryHint,
        image_set_1: set1.map((x) => x.dataUrl),
        image_set_2: set2.map((x) => x.dataUrl),
        user_prompt: userPrompt.slice(0, 500),
      });
      setResult(data);
    } catch (e) {
      const msg =
        e.response?.data?.message ||
        e.response?.data?.detail ||
        e.message ||
        'Request failed';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={theme.pageTitle}>Compare product images</h1>
      <p style={theme.pageSubtitle}>
        Upload 2–3 images per side, then run the pipeline (visibility → comparison).
      </p>

      <SnapAuditAboutBanner />

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 28 }}>
        <DropZone
          title="Image Set 1 — Reference"
          style={zoneStyle}
          disabled={loading}
          onPick={handleFileInputChange(1)}
          onDropFiles={(files) => addFiles(files, 1)}
          count={set1.length}
        >
          <Thumbs items={set1} which={1} onRemove={remove} />
        </DropZone>
        <DropZone
          title="Image Set 2 — Product Received by User / Product Returned by User"
          style={zoneStyle}
          disabled={loading}
          onPick={handleFileInputChange(2)}
          onDropFiles={(files) => addFiles(files, 2)}
          count={set2.length}
        >
          <Thumbs items={set2} which={2} onRemove={remove} />
        </DropZone>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 20,
          marginBottom: 20,
          maxWidth: 720,
        }}
      >
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
          <span style={{ fontWeight: 600, color: '#334155' }}>Session ID *</span>
          <input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder="e.g. sess-2024-001"
            disabled={loading}
            style={{ padding: 10, borderRadius: 8, border: '1px solid #cbd5e1' }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
          <span style={{ fontWeight: 600, color: '#334155' }}>Comparison type</span>
          <select
            value={comparisonType}
            onChange={(e) => setComparisonType(e.target.value)}
            disabled={loading}
            style={{ padding: 10, borderRadius: 8, border: '1px solid #cbd5e1' }}
          >
            {COMPARISON_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
          <span style={{ fontWeight: 600, color: '#334155' }}>Category hint</span>
          <select
            value={categoryHint}
            onChange={(e) => setCategoryHint(e.target.value)}
            disabled={loading}
            style={{ padding: 10, borderRadius: 8, border: '1px solid #cbd5e1' }}
          >
            {CATEGORY_HINTS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <div />
      </div>

      <label style={{ display: 'block', marginBottom: 20, maxWidth: 720 }}>
        <span style={{ fontWeight: 600, color: '#334155', fontSize: 13, display: 'block', marginBottom: 6 }}>
          Context prompt ({userPrompt.length}/500)
        </span>
        <textarea
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value.slice(0, 500))}
          rows={4}
          disabled={loading}
          placeholder="Optional notes for the model (does not override policy)"
          style={{
            width: '100%',
            padding: 12,
            borderRadius: 8,
            border: '1px solid #cbd5e1',
            fontFamily: 'inherit',
            fontSize: 14,
          }}
        />
      </label>

      <button
        type="button"
        onClick={run}
        disabled={!canSubmit || loading}
        style={{
          padding: '12px 24px',
          fontWeight: 600,
          fontSize: 15,
          border: 'none',
          borderRadius: 8,
          background: canSubmit && !loading ? '#0f172a' : '#94a3b8',
          color: '#fff',
          cursor: canSubmit && !loading ? 'pointer' : 'not-allowed',
        }}
      >
        {loading ? 'Running…' : 'Run comparison'}
      </button>

      {loading && (
        <p style={{ marginTop: 16, color: '#475569', fontSize: 14 }}>
          {loadStage === 1 ? 'Checking visibility…' : 'Running comparison…'}
        </p>
      )}

      {error && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: '#fef2f2',
            color: '#991b1b',
            borderRadius: 8,
            fontSize: 14,
          }}
        >
          {error}
        </div>
      )}

      {result && (
        <div style={theme.verdictCard}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', marginBottom: 18 }}>
            <VerdictBadge verdict={result.verdict} />
            <ConfidenceBadge confidence={result.confidence} />
            {result.short_circuited && (
              <ShortCircuitBadge>Short-circuited (Pass 2 skipped)</ShortCircuitBadge>
            )}
          </div>
          {result.short_circuit_reason && (
            <p style={{ fontSize: 13, color: '#64748b', marginBottom: 18 }}>
              {humanizeVerdictCopy(result.short_circuit_reason)}
            </p>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 18 }}>
            <AttributePill label="Colour" value={result.colour} />
            <AttributePill label="Design" value={result.design} />
            <AttributePill label="Category" value={result.category_match} />
            <AttributePill label="Quantity" value={result.quantity} />
          </div>
          <p style={{ fontSize: 14, color: '#334155', lineHeight: 1.6, marginBottom: 12 }}>
            {humanizeVerdictCopy(result.description) || '—'}
          </p>
          <div style={{ fontSize: 13, color: '#64748b' }}>
            <div>
              Model: <strong style={{ color: '#334155' }}>{result.model_used}</strong>
            </div>
            <div>
              Latency: <strong style={{ color: '#334155' }}>{result.total_latency_ms} ms</strong>
              {result.overwritten && ' · overwritten'}
            </div>
            <div style={{ marginTop: 4 }}>
              Audit ID: <code style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>{result.audit_id}</code>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DropZone({ title, children, style, disabled, onPick, onDropFiles, count }) {
  const [drag, setDrag] = useState(false);
  return (
    <div
      style={{
        ...style,
        borderColor: drag ? '#64748b' : '#cbd5e1',
        opacity: disabled ? 0.6 : 1,
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (!disabled) onDropFiles(e.dataTransfer.files);
      }}
    >
      <div style={{ fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 13, color: '#64748b', marginBottom: 8 }}>
        {count}/3 images · drag & drop or click
      </div>
      <label
        style={{
          display: 'inline-block',
          padding: '8px 14px',
          background: '#fff',
          border: '1px solid #cbd5e1',
          borderRadius: 6,
          fontSize: 13,
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
        Choose files
        <input
          type="file"
          accept="image/*"
          multiple
          disabled={disabled || count >= 3}
          style={{ display: 'none' }}
          onChange={onPick}
        />
      </label>
      {children}
    </div>
  );
}

function Thumbs({ items, which, onRemove }) {
  if (!items.length) return null;
  return (
    <div style={thumbWrap}>
      {items.map((item) => (
        <div key={item.id} style={thumbBox}>
          <img src={item.preview} alt="" style={thumbImg} />
          <button
            type="button"
            onClick={() => onRemove(which, item.id)}
            style={{
              position: 'absolute',
              top: -6,
              right: -6,
              width: 22,
              height: 22,
              borderRadius: '50%',
              border: 'none',
              background: '#0f172a',
              color: '#fff',
              fontSize: 14,
              lineHeight: '20px',
              cursor: 'pointer',
            }}
            aria-label="Remove"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
