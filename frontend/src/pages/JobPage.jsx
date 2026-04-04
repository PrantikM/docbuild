import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { createJobStream } from '../api';

function formatTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-US', { hour12: false });
}

function StatusBadge({ status }) {
  const labels = {
    queued: 'Queued',
    running: 'Running',
    done: 'Complete',
    error: 'Error',
  };
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span className="status-dot" />
      {labels[status] || status}
    </span>
  );
}

export default function JobPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('queued');
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [repoUrl, setRepoUrl] = useState('');
  const logEndRef = useRef(null);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    const es = createJobStream(jobId);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setStatus(data.status);
        setProgress(data.progress || 0);
        setLogs(data.logs || []);
        setError(data.error || null);
        if (data.repo_url) setRepoUrl(data.repo_url);

        if (data.status === 'done' || data.status === 'error' || data.status === 'not_found') {
          es.close();
        }
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [jobId]);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="page page-enter">
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-xl)', flexWrap: 'wrap', gap: 'var(--space-md)' }}>
        <div>
          <h1 style={{ fontSize: '1.6rem', fontWeight: 700, marginBottom: 'var(--space-xs)', letterSpacing: '-0.02em' }}>
            Processing Repository
          </h1>
          {repoUrl && (
            <p className="text-secondary" style={{ fontSize: '0.88rem', fontFamily: 'var(--font-mono)' }}>
              {repoUrl}
            </p>
          )}
        </div>
        <StatusBadge status={status} />
      </div>

      {/* Progress */}
      <div className="card" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="progress-container">
          <div className="progress-header">
            <span className="progress-label">
              {status === 'done' ? 'Documentation complete' :
               status === 'error' ? 'Job failed' :
               'Agent is exploring the codebase...'}
            </span>
            <span className="progress-value">{progress}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="error-banner" style={{ marginBottom: 'var(--space-lg)' }}>
          <span className="error-banner-icon">✕</span>
          <div>
            <div className="error-banner-message">{error}</div>
          </div>
        </div>
      )}

      {/* Live Logs */}
      <div className="card" style={{ marginBottom: 'var(--space-xl)' }}>
        <div className="flex items-center justify-between mb-md">
          <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>Live Logs</h2>
          <span className="text-muted" style={{ fontSize: '0.78rem' }}>
            {logs.length} entries
          </span>
        </div>
        <div className="log-viewer" id="log-viewer">
          {logs.length === 0 && (
            <div className="text-muted" style={{ padding: 'var(--space-lg)', textAlign: 'center' }}>
              Waiting for agent to start...
            </div>
          )}
          {logs.map((log, i) => (
            <div className="log-entry" key={i}>
              <span className="log-timestamp">
                {log.ts ? formatTime(log.ts) : '--:--:--'}
              </span>
              <span className={`log-message log-message--${log.type || 'info'}`}>
                {log.message}
              </span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-md" style={{ flexWrap: 'wrap' }}>
        {status === 'done' && (
          <button
            className="btn btn-primary"
            onClick={() => navigate(`/docs/${jobId}`)}
            id="view-docs-btn"
          >
            📄 View Documentation
          </button>
        )}
        {status === 'error' && (
          <Link to="/" className="btn btn-primary" id="retry-btn">
            ↩ Try Again
          </Link>
        )}
        <Link to="/" className="btn btn-ghost" id="new-job-btn">
          + New Job
        </Link>
      </div>
    </div>
  );
}
