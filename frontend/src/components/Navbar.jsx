import { Link } from 'react-router-dom';

export default function Navbar() {
  return (
    <nav className="navbar" id="navbar">
      <Link to="/" className="navbar-brand">
        <span className="navbar-logo">◈</span>
        DocBuild
        <span className="navbar-badge">AI</span>
      </Link>
      <div className="navbar-links">
        <a
          href="https://github.com/PrantikM/docbuild"
          target="_blank"
          rel="noopener noreferrer"
          className="navbar-link"
        >
          GitHub ↗
        </a>
      </div>
    </nav>
  );
}
