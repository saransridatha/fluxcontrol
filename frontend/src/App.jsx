import AdminDashboard from './components/AdminDashboard';
import ClientSimulator from './components/ClientSimulator';
import ConfigPanel from './components/ConfigPanel';
import './App.css';

function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="logo-group">
          <span className="logo-icon">⚡</span>
          <h1 className="logo-text">FluxControl</h1>
        </div>
        <span className="header-subtitle">Adaptive Rate Limiting &amp; Proof-of-Work Shield</span>
      </header>

      <main className="app-grid">
        <div className="sidebar">
          <ConfigPanel />
          <ClientSimulator />
        </div>
        <div className="main-content">
          <AdminDashboard />
        </div>
      </main>

      <footer className="app-footer">
        <span>FluxControl — DDoS-resistant API gateway with Proof-of-Work challenge</span>
      </footer>
    </div>
  );
}

export default App;
