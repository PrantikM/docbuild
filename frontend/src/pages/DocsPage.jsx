import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { getJobDocs } from '../api';

const TAB_KEYS = [
  { key: 'main_readme', label: 'README' },
  { key: 'architecture_doc', label: 'Architecture' },
  { key: 'how_to_run', label: 'How to Run' },
  { key: 'api_reference', label: 'API Reference' },
  { key: 'contributing_guide', label: 'Contributing' },
  { key: 'changelog', label: 'Changelog' },
  { key: 'folder_readmes', label: 'Folder Docs' },
];

function Accordion({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`accordion ${open ? 'accordion--open' : ''}`}>
      <button className="accordion-trigger" onClick={() => setOpen((v) => !v)}>
        <span>{title}</span>
        <span className="accordion-icon">▾</span>
      </button>
      {open && <div className="accordion-content">{children}</div>}
    </div>
  );
}

export default function DocsPage() {
  const { jobId } = useParams();
  const [docs, setDocs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('main_readme');

  useEffect(() => {
    getJobDocs(jobId)
      .then((data) => {
        setDocs(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [jobId]);

  if (loading) {
    return (
      <div className="page page-enter flex flex-col items-center justify-center" style={{ minHeight: '50vh' }}>
        <div className="btn-loading" style={{ position: 'relative', width: 40, height: 40 }}>
          <span style={{ position: 'absolute', width: 28, height: 28, border: '3px solid var(--border-subtle)', borderTopColor: 'var(--accent-primary)', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
        </div>
        <p className="text-secondary mt-lg">Loading documentation...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page page-enter">
        <div className="error-banner">
          <span className="error-banner-icon">✕</span>
          <span className="error-banner-message">{error}</span>
        </div>
        <div className="mt-lg">
          <Link to="/" className="btn btn-primary">← Back to Home</Link>
        </div>
      </div>
    );
  }

  // Filter tabs that have content
  const availableTabs = TAB_KEYS.filter(({ key }) => {
    if (key === 'folder_readmes') {
      return docs.folder_readmes && docs.folder_readmes.length > 0;
    }
    return docs[key] && docs[key].trim().length > 0;
  });

  const renderTabContent = () => {
    if (activeTab === 'folder_readmes') {
      const folders = docs.folder_readmes || [];
      if (folders.length === 0) return <p className="text-muted">No folder documentation available.</p>;
      return (
        <div>
          {folders.map((f, i) => (
            <Accordion key={i} title={`📁 ${f.folder}`}>
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                  {f.content}
                </ReactMarkdown>
              </div>
            </Accordion>
          ))}
        </div>
      );
    }
    const content = docs[activeTab];
    if (!content) return <p className="text-muted">No content available for this section.</p>;
    return (
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {content}
        </ReactMarkdown>
      </div>
    );
  };

  return (
    <div className="page page-enter">
      {/* Header */}
      <div style={{ marginBottom: 'var(--space-xl)' }}>
        <h1 style={{ fontSize: '1.6rem', fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 'var(--space-xs)' }}>
          Generated Documentation
        </h1>
        <p className="text-secondary" style={{ fontSize: '0.88rem' }}>
          Job <span className="text-muted" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{jobId}</span>
        </p>
      </div>

      {/* Tabs */}
      <div className="tabs" id="doc-tabs">
        {availableTabs.map(({ key, label }) => (
          <button
            key={key}
            className={`tab ${activeTab === key ? 'tab--active' : ''}`}
            onClick={() => setActiveTab(key)}
            id={`tab-${key}`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="card card-lg tab-content" key={activeTab}>
        {renderTabContent()}
      </div>

      {/* Actions */}
      <div className="flex gap-md mt-xl" style={{ flexWrap: 'wrap' }}>
        <Link to="/" className="btn btn-primary" id="new-job-btn-docs">
          + Start New Job
        </Link>
        <button
          className="btn btn-ghost"
          onClick={() => {
            const blob = new Blob([JSON.stringify(docs, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `docbuild-${jobId.slice(0, 8)}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          id="download-json-btn"
        >
          ⬇ Download JSON
        </button>
      </div>
    </div>
  );
}
