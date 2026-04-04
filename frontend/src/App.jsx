import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import HomePage from './pages/HomePage';
import JobPage from './pages/JobPage';
import DocsPage from './pages/DocsPage';

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/job/:jobId" element={<JobPage />} />
        <Route path="/docs/:jobId" element={<DocsPage />} />
      </Routes>
    </>
  );
}
