import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { startJob } from '../api';

export default function HomePage() {
  const navigate = useNavigate();
  const [repoUrl, setRepoUrl] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showToken, setShowToken] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const data = await startJob(repoUrl.trim(), githubToken.trim());
      navigate(`/job/${data.job_id}`);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div className="page page-enter">
      {/* Hero */}
      <section className="hero">
        <div className="hero-eyebrow">
          <span>⚡</span> Powered by LangGraph + Claude
        </div>
        <h1 className="hero-title">
          Document any codebase,
          <br />
          autonomously.
        </h1>
        <p className="hero-subtitle">
          Point DocBuild at a GitHub repository. Our AI agent clones it, explores
          every file, and writes comprehensive documentation — README, architecture docs,
          how-to guides, and more.
        </p>
      </section>

      {/* Form Card */}
      <div className="card card-lg" style={{ maxWidth: 620, margin: '0 auto' }}>
        <form onSubmit={handleSubmit} id="job-form">
          <div className="form-group">
            <label className="form-label" htmlFor="repo-url">
              GitHub Repository URL
            </label>
            <input
              id="repo-url"
              className="form-input"
              type="url"
              placeholder="https://github.com/owner/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              required
              autoFocus
            />
          </div>

          {/* Toggle for optional token */}
          <div style={{ marginBottom: 'var(--space-lg)' }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowToken((v) => !v)}
              id="toggle-token-btn"
            >
              {showToken ? '▾ Hide' : '▸ Add'} GitHub Token (optional)
            </button>
          </div>

          {showToken && (
            <div className="form-group" style={{ animation: 'fadeIn 0.25s ease' }}>
              <label className="form-label" htmlFor="github-token">
                GitHub Token
              </label>
              <input
                id="github-token"
                className="form-input"
                type="password"
                placeholder="ghp_xxxxxxxxxxxx"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
              />
              <p className="form-hint">
                Required for private repositories. Your token is never stored.
              </p>
            </div>
          )}

          {error && (
            <div className="error-banner mb-lg">
              <span className="error-banner-icon">⚠</span>
              <span className="error-banner-message">{error}</span>
            </div>
          )}

          <button
            type="submit"
            className={`btn btn-primary btn-block ${loading ? 'btn-loading' : ''}`}
            disabled={loading || !repoUrl.trim()}
            id="submit-btn"
          >
            <span className="btn-text">
              {loading ? 'Starting...' : '🚀 Generate Documentation'}
            </span>
          </button>
        </form>
      </div>

      {/* Features grid */}
      <section style={{ marginTop: 'var(--space-3xl)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 'var(--space-lg)',
          }}
        >
          <div className="card">
            <div style={{ fontSize: '1.8rem', marginBottom: 'var(--space-sm)' }}>🤖</div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: 'var(--space-sm)' }}>
              Agentic AI
            </h3>
            <p className="text-secondary" style={{ fontSize: '0.88rem' }}>
              LangGraph state machine autonomously explores your repo — reads files,
              understands architecture, and generates docs.
            </p>
          </div>
          <div className="card">
            <div style={{ fontSize: '1.8rem', marginBottom: 'var(--space-sm)' }}>📡</div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: 'var(--space-sm)' }}>
              Real-time Streaming
            </h3>
            <p className="text-secondary" style={{ fontSize: '0.88rem' }}>
              Watch the agent work in real-time with live logs and progress updates
              streamed via Server-Sent Events.
            </p>
          </div>
          <div className="card">
            <div style={{ fontSize: '1.8rem', marginBottom: 'var(--space-sm)' }}>📦</div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: 'var(--space-sm)' }}>
              Complete Output
            </h3>
            <p className="text-secondary" style={{ fontSize: '0.88rem' }}>
              Get README, architecture docs, how-to-run guides, API references,
              per-folder READMEs, and more — all in Markdown.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
