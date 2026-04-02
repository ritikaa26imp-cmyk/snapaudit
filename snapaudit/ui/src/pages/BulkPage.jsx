import { useRef, useState } from 'react';
import { compareImages } from '../api.js';
import { theme } from '../theme.js';

const REQUIRED_CANONICAL = ['session_id', 'image_set_1_link_1', 'image_set_2_link_1'];

/** Lowercase, trim, collapse spaces and underscores — used for header matching */
function normalizeHeader(header) {
  return String(header).toLowerCase().trim().replace(/[\s_]+/g, '');
}

/** Normalised header → canonical field name (underscore form used in payloads/output) */
const NORMALIZED_TO_CANONICAL = {
  sessionid: 'session_id',
  imageset1link1: 'image_set_1_link_1',
  imageset1link2: 'image_set_1_link_2',
  imageset1link3: 'image_set_1_link_3',
  imageset2link1: 'image_set_2_link_1',
  imageset2link2: 'image_set_2_link_2',
  imageset2link3: 'image_set_2_link_3',
  category: 'category',
};

function headersHaveRequired(rawHeaders) {
  const present = new Set();
  rawHeaders.forEach((h) => {
    const canon = NORMALIZED_TO_CANONICAL[normalizeHeader(h)];
    if (canon) present.add(canon);
  });
  return REQUIRED_CANONICAL.every((req) => present.has(req));
}

/** Map a CSV row to canonical keys; duplicate columns for the same field → last wins */
function buildCanonicalRow(rawHeaders, cells) {
  const o = {
    session_id: '',
    image_set_1_link_1: '',
    image_set_1_link_2: '',
    image_set_1_link_3: '',
    image_set_2_link_1: '',
    image_set_2_link_2: '',
    image_set_2_link_3: '',
    category: '',
  };
  rawHeaders.forEach((h, i) => {
    const key = NORMALIZED_TO_CANONICAL[normalizeHeader(h)];
    if (!key) return;
    const val = cells[i] != null && cells[i] !== undefined ? String(cells[i]).trim() : '';
    o[key] = val;
  });
  return o;
}

const HEADER_SAMPLE =
  'session_id,image_set_1_link_1,image_set_1_link_2,image_set_1_link_3,image_set_2_link_1,image_set_2_link_2,image_set_2_link_3,category';

/** Parse one CSV line with optional double-quoted fields */
function parseCSVLine(line) {
  const out = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (c === '"') {
      if (inQ && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQ = !inQ;
      }
      continue;
    }
    if (c === ',' && !inQ) {
      out.push(cur.trim());
      cur = '';
      continue;
    }
    cur += c;
  }
  out.push(cur.trim());
  return out;
}

function parseCSV(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) return { headers: [], rows: [] };
  const headers = parseCSVLine(lines[0]).map((h) => h.trim());
  const rows = lines.slice(1).map((line) => parseCSVLine(line));
  return { headers, rows };
}

function collectLinks(obj, prefix) {
  const keys = [`${prefix}_link_1`, `${prefix}_link_2`, `${prefix}_link_3`];
  return keys.map((k) => obj[k]).filter((v) => v && String(v).trim().length > 0).slice(0, 3);
}

function csvEscapeCell(val) {
  const s = val == null ? '' : String(val);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function buildOutputCsv(rows, resultsByIndex) {
  const cols = [
    'session_id',
    'image_set_1_link_1',
    'image_set_1_link_2',
    'image_set_1_link_3',
    'image_set_2_link_1',
    'image_set_2_link_2',
    'image_set_2_link_3',
    'category',
    'response_json',
  ];
  const header = cols.join(',');
  const lines = [header];
  rows.forEach((r, i) => {
    const res = resultsByIndex[i];
    let payload;
    if (!res) {
      payload = { error: 'not processed (batch cancelled or skipped)' };
    } else if (res.ok) {
      payload = res.data;
    } else {
      payload = { error: res.errorMessage || 'unknown' };
    }
    const json = JSON.stringify(payload);
    const cells = [
      r.session_id ?? '',
      r.image_set_1_link_1 ?? '',
      r.image_set_1_link_2 ?? '',
      r.image_set_1_link_3 ?? '',
      r.image_set_2_link_1 ?? '',
      r.image_set_2_link_2 ?? '',
      r.image_set_2_link_3 ?? '',
      r.category ?? '',
      json,
    ].map(csvEscapeCell);
    lines.push(cells.join(','));
  });
  return lines.join('\n');
}

function triggerDownload(csvText, filename) {
  const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  return blob;
}

export default function BulkPage() {
  const [fileName, setFileName] = useState('');
  const [parseError, setParseError] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [dataRows, setDataRows] = useState([]);
  const [previewRows, setPreviewRows] = useState([]);
  const [objects, setObjects] = useState([]);
  const [prompt, setPrompt] = useState('');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0, currentSession: '', completed: 0, errors: 0 });
  const [doneSummary, setDoneSummary] = useState(null);
  const [lastCsv, setLastCsv] = useState('');
  const cancelRef = useRef(false);
  const fileInputRef = useRef(null);

  const validCsv = parseError === null && objects.length > 0 && headersHaveRequired(headers);

  const clearUpload = () => {
    setFileName('');
    setParseError(null);
    setHeaders([]);
    setDataRows([]);
    setPreviewRows([]);
    setObjects([]);
    setDoneSummary(null);
    setLastCsv('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const onFile = (f) => {
    if (!f) return;
    setFileName(f.name);
    setParseError(null);
    setDoneSummary(null);
    setLastCsv('');
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = String(reader.result);
        const { headers: h, rows } = parseCSV(text);
        const present = new Set();
        h.forEach((col) => {
          const canon = NORMALIZED_TO_CANONICAL[normalizeHeader(col)];
          if (canon) present.add(canon);
        });
        const missing = REQUIRED_CANONICAL.filter((req) => !present.has(req));
        if (missing.length) {
          setParseError(`Missing required columns: ${missing.join(', ')}`);
          setHeaders([]);
          setDataRows([]);
          setPreviewRows([]);
          setObjects([]);
          return;
        }
        const objs = rows.map((cells) => buildCanonicalRow(h, cells));
        setHeaders(h);
        setDataRows(rows);
        setPreviewRows(rows.slice(0, 5));
        setObjects(objs);
      } catch (e) {
        setParseError(e.message || 'Failed to parse CSV');
        setObjects([]);
      }
    };
    reader.readAsText(f, 'utf-8');
  };

  const rowCount = objects.length;
  const warnMinutes = rowCount > 20 ? Math.ceil((rowCount * 45) / 60) : 0;

  const runBulk = async () => {
    if (!validCsv) return;
    cancelRef.current = false;
    setRunning(true);
    setDoneSummary(null);
    const total = objects.length;
    const resultsByIndex = {};
    let completed = 0;
    let errors = 0;

    for (let i = 0; i < total; i += 1) {
      const row = objects[i];
      setProgress({
        done: i,
        total,
        currentSession: row.session_id || '(no session)',
        completed,
        errors,
      });

      const image_set_1 = collectLinks(row, 'image_set_1');
      const image_set_2 = collectLinks(row, 'image_set_2');
      const category_hint = row.category && row.category.trim() ? row.category.trim() : 'auto';

      const payload = {
        session_id: row.session_id,
        comparison_type: 'catalog_vs_pickup',
        category_hint,
        image_set_1,
        image_set_2,
        user_prompt: prompt.slice(0, 500),
      };

      try {
        const { data } = await compareImages(payload);
        resultsByIndex[i] = { ok: true, data };
        completed += 1;
      } catch (e) {
        const msg =
          e.response?.data?.message ||
          e.response?.data?.detail ||
          (typeof e.response?.data === 'string' ? e.response.data : null) ||
          e.message ||
          'Request failed';
        const errStr = typeof msg === 'string' ? msg : JSON.stringify(msg);
        resultsByIndex[i] = { ok: false, errorMessage: errStr };
        errors += 1;
      }

      setProgress({
        done: i + 1,
        total,
        currentSession: row.session_id || '',
        completed,
        errors,
      });

      if (cancelRef.current) break;
    }

    const csvOut = buildOutputCsv(
      objects.map((o) => ({
        session_id: o.session_id,
        image_set_1_link_1: o.image_set_1_link_1,
        image_set_1_link_2: o.image_set_1_link_2,
        image_set_1_link_3: o.image_set_1_link_3,
        image_set_2_link_1: o.image_set_2_link_1,
        image_set_2_link_2: o.image_set_2_link_2,
        image_set_2_link_3: o.image_set_2_link_3,
        category: o.category,
      })),
      resultsByIndex,
    );
    setLastCsv(csvOut);
    triggerDownload(csvOut, 'snapaudit_bulk_results.csv');

    const processedRows = Object.keys(resultsByIndex).length;
    setDoneSummary({
      processed: processedRows,
      errors,
      completed,
    });
    setRunning(false);
  };

  const downloadAgain = () => {
    if (lastCsv) triggerDownload(lastCsv, 'snapaudit_bulk_results.csv');
  };

  return (
    <div style={{ paddingBottom: 48 }}>
      <h1 style={theme.pageTitle}>Bulk comparison</h1>
      <p style={theme.pageSubtitle}>
        Upload a CSV of image URLs and session IDs. Each row runs the same pipeline as the Compare page (~45s per row
        estimated).
      </p>

      {/* CSV upload */}
      <div
        style={{
          border: '2px dashed #94a3b8',
          borderRadius: 12,
          padding: 28,
          background: '#f8fafc',
          marginBottom: 20,
          boxShadow: theme.cardShadowSubtle,
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onFile(e.dataTransfer.files[0]);
        }}
      >
        <label style={{ cursor: 'pointer', fontWeight: 600, color: '#0f172a' }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            style={{ display: 'none' }}
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          Drop CSV here or click to upload
        </label>
        {fileName && (
          <div
            style={{
              marginTop: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
              color: '#475569',
              fontSize: 14,
            }}
          >
            <p style={{ margin: 0 }}>
              <strong>File:</strong> {fileName}
            </p>
            <button
              type="button"
              onClick={clearUpload}
              aria-label="Remove file"
              title="Remove file"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                padding: 0,
                border: '1px solid #cbd5e1',
                borderRadius: 6,
                background: '#fff',
                color: '#64748b',
                fontSize: 16,
                lineHeight: 1,
                cursor: 'pointer',
              }}
            >
              ×
            </button>
          </div>
        )}
        {parseError && (
          <p style={{ marginTop: 12, color: '#b91c1c', fontSize: 14 }}>{parseError}</p>
        )}
      </div>

      <details style={{ marginBottom: 24 }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#334155', marginBottom: 8 }}>
          Sample CSV format
        </summary>
        <pre
          style={{
            background: '#f1f5f9',
            padding: 16,
            borderRadius: 8,
            overflow: 'auto',
            fontSize: 12,
            border: '1px solid #e2e8f0',
            boxShadow: theme.cardShadowSubtle,
          }}
        >
          {HEADER_SAMPLE}
        </pre>
        <p style={{ fontSize: 13, color: '#64748b', marginTop: 8, lineHeight: 1.5 }}>
          <code>image_set_1_link_2</code>, <code>image_set_1_link_3</code>, <code>image_set_2_link_2</code>,{' '}
          <code>image_set_2_link_3</code> are optional. <strong>category</strong> accepts: auto, saree, kurti, bag, cloth,
          jewellery, watch
        </p>
      </details>

      {validCsv && previewRows.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: '#334155' }}>Preview (first 5 rows)</h2>
          <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: 10, boxShadow: theme.cardShadowSubtle }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f1f5f9' }}>
                  {headers.map((h) => (
                    <th key={h} style={{ padding: 10, textAlign: 'left', borderBottom: '1px solid #e2e8f0' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewRows.map((cells, ri) => (
                  <tr key={ri}>
                    {cells.map((c, ci) => (
                      <td
                        key={ci}
                        style={{
                          padding: 8,
                          borderBottom: '1px solid #f1f5f9',
                          maxWidth: 180,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={c}
                      >
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {rowCount > 20 && validCsv && (
        <div
          style={{
            background: '#fefce8',
            border: '1px solid #fde047',
            color: '#854d0e',
            padding: 16,
            borderRadius: 10,
            marginBottom: 24,
            fontSize: 14,
            lineHeight: 1.55,
            boxShadow: theme.cardShadowSubtle,
          }}
        >
          This batch has <strong>{rowCount}</strong> rows and may take approximately <strong>{warnMinutes}</strong>{' '}
          minute{warnMinutes !== 1 ? 's' : ''} to complete (est. 45 seconds per row). Keep this tab open and disable sleep
          mode on your Mac while it runs.
        </div>
      )}

      <label style={{ display: 'block', marginBottom: 20, maxWidth: 560 }}>
        <span style={{ fontWeight: 600, color: '#334155', fontSize: 14, display: 'block', marginBottom: 8 }}>
          Context prompt (optional) — applies to all rows ({prompt.length}/500)
        </span>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value.slice(0, 500))}
          rows={4}
          disabled={running}
          style={{
            width: '100%',
            padding: 14,
            borderRadius: 10,
            border: '1px solid #cbd5e1',
            fontFamily: 'inherit',
            fontSize: 14,
            boxShadow: theme.cardShadowSubtle,
          }}
        />
      </label>

      <button
        type="button"
        onClick={runBulk}
        disabled={!validCsv || running}
        style={{
          padding: '14px 28px',
          fontWeight: 600,
          fontSize: 15,
          border: 'none',
          borderRadius: 10,
          background: validCsv && !running ? '#0f172a' : '#94a3b8',
          color: '#fff',
          cursor: validCsv && !running ? 'pointer' : 'not-allowed',
          marginBottom: 24,
          boxShadow: validCsv && !running ? theme.cardShadowSubtle : 'none',
        }}
      >
        {running ? 'Running…' : `Run bulk comparison (${rowCount} rows)`}
      </button>

      {running && (
        <div
          style={{
            padding: 24,
            borderRadius: 12,
            border: '1px solid #e2e8f0',
            background: '#fff',
            marginBottom: 24,
            boxShadow: theme.cardShadow,
          }}
        >
          <div style={{ marginBottom: 12, fontWeight: 600, color: '#0f172a' }}>Progress</div>
          <div
            style={{
              height: 10,
              borderRadius: 8,
              background: '#e2e8f0',
              overflow: 'hidden',
              marginBottom: 12,
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%`,
                background: '#0f172a',
                transition: 'width 0.2s ease',
              }}
            />
          </div>
          <p style={{ fontSize: 14, color: '#475569', marginBottom: 8 }}>
            {progress.done} of {progress.total} rows complete
          </p>
          <p style={{ fontSize: 14, color: '#64748b', marginBottom: 8 }}>
            Current: <strong style={{ color: '#0f172a' }}>{progress.currentSession}</strong>
          </p>
          <p style={{ fontSize: 14, color: '#475569', marginBottom: 16 }}>
            {progress.completed} completed · {progress.errors} errors
          </p>
          <button
            type="button"
            onClick={() => {
              cancelRef.current = true;
            }}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: '1px solid #cbd5e1',
              background: '#fff',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel (after current row)
          </button>
        </div>
      )}

      {doneSummary && !running && (
        <div
          style={{
            padding: 24,
            borderRadius: 12,
            border: '1px solid #cbd5e1',
            background: '#f8fafc',
            boxShadow: theme.cardShadow,
          }}
        >
          <p style={{ fontSize: 16, fontWeight: 600, color: '#0f172a', marginBottom: 12 }}>
            Batch complete — {doneSummary.processed} rows processed, {doneSummary.errors} errors
          </p>
          <p style={{ fontSize: 13, color: '#64748b', marginBottom: 16 }}>
            Results were downloaded automatically. If your browser blocked it, use the button below.
          </p>
          <button
            type="button"
            onClick={downloadAgain}
            disabled={!lastCsv}
            style={{
              padding: '10px 20px',
              borderRadius: 8,
              border: '1px solid #cbd5e1',
              background: '#fff',
              fontWeight: 600,
              cursor: lastCsv ? 'pointer' : 'not-allowed',
            }}
          >
            Download again
          </button>
        </div>
      )}
    </div>
  );
}
