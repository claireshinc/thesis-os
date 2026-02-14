import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import BriefPage from './pages/BriefPage';
import ThesisPage from './pages/ThesisPage';
import FeedPage from './pages/FeedPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<BriefPage />} />
          <Route path="/thesis" element={<ThesisPage />} />
          <Route path="/feed" element={<FeedPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
