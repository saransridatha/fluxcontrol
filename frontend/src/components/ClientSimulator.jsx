import { useState, useRef, useCallback } from 'react';
import { makeProxyRequest } from '../api';
import { useToast } from './ToastProvider';
import ShieldModeVisualizer from './ShieldModeVisualizer';

const statusConfig = {
  200: { label: '200 OK', color: 'green' },
  401: { label: '401 Shield', color: 'purple' },
  403: { label: '403 Banned', color: 'red' },
  429: { label: '429 Limited', color: 'yellow' },
};

const ClientSimulator = () => {
  const [requests, setRequests] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [shieldChallenge, setShieldChallenge] = useState(null);
  const [powHistory, setPowHistory] = useState([]);
  const idCounter = useRef(0);
  const toast = useToast();

  const handleRequest = async (solution = null) => {
    setIsLoading(true);
    const requestId = ++idCounter.current;
    try {
      const response = await makeProxyRequest(solution);
      setRequests((prev) => [
        { id: requestId, status: response.status, data: response.data, ts: Date.now() },
        ...prev,
      ]);
      setShieldChallenge(null);
    } catch (error) {
      if (error.response) {
        const { status, data } = error.response;
        setRequests((prev) => [
          { id: requestId, status, data, ts: Date.now() },
          ...prev,
        ]);
        if (status === 401 && data.challenge) {
          setShieldChallenge(data);
        }
      } else {
        toast.error('Network error: ' + error.message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSolve = useCallback((solution) => {
    toast.success(`PoW solved! Retrying with nonce ${solution}`);
    setPowHistory((prev) => [
      {
        id: Date.now(),
        nonce: solution,
        challenge: shieldChallenge?.challenge,
        difficulty: shieldChallenge?.difficulty,
        solvedAt: new Date().toLocaleTimeString(),
      },
      ...prev,
    ]);
    handleRequest(String(solution));
  }, [shieldChallenge]);  // eslint-disable-line react-hooks/exhaustive-deps

  const handleBurst = async () => {
    for (let i = 0; i < 10; i++) {
      await handleRequest();
      if (shieldChallenge) break;
      await new Promise((r) => setTimeout(r, 100));
    }
  };

  const getStatusInfo = (status) => statusConfig[status] || { label: `${status}`, color: 'gray' };

  return (
    <div className="card">
      <div className="card-header">
        <span>🚀</span>
        <span>Request Simulator</span>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          className="btn btn-primary"
          onClick={() => handleRequest()}
          disabled={isLoading || !!shieldChallenge}
        >
          {isLoading ? '⏳' : '→'} Single Request
        </button>
        <button
          className="btn btn-secondary"
          onClick={handleBurst}
          disabled={isLoading || !!shieldChallenge}
        >
          ⚡ Burst (10)
        </button>
        {requests.length > 0 && (
          <button
            className="btn btn-secondary"
            onClick={() => { setRequests([]); idCounter.current = 0; }}
            style={{ marginLeft: 'auto' }}
          >
            Clear
          </button>
        )}
      </div>

      {shieldChallenge && (
        <ShieldModeVisualizer
          challenge={shieldChallenge.challenge}
          difficulty={shieldChallenge.difficulty}
          onSolve={handleSolve}
        />
      )}

      {powHistory.length > 0 && (
        <div className="pow-history-box">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#c084fc', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>🔐</span> PoW Solution History
              <span style={{ color: '#64748b' }}>({powHistory.length})</span>
            </div>
            <button
              className="btn btn-secondary"
              style={{ padding: '2px 8px', fontSize: '0.7rem' }}
              onClick={() => setPowHistory([])}
            >
              Clear
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
            {powHistory.map((entry) => (
              <div key={entry.id} className="pow-history-entry">
                <span style={{ color: '#4ade80', fontWeight: 700, fontSize: '0.8rem' }}>✅</span>
                <span style={{ color: '#94a3b8', fontSize: '0.75rem', minWidth: 64 }}>{entry.solvedAt}</span>
                <span style={{ fontSize: '0.78rem', color: '#cbd5e1' }}>
                  nonce <code style={{ color: '#818cf8' }}>{entry.nonce}</code>
                </span>
                <span style={{ fontSize: '0.72rem', color: '#64748b', marginLeft: 'auto' }}>
                  d={entry.difficulty}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Request Log {requests.length > 0 && <span style={{ color: '#475569' }}>({requests.length})</span>}
        </div>

        {requests.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '24px 0', color: '#475569', fontSize: '0.85rem' }}>
            No requests sent yet. Click a button above to start.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 360, overflowY: 'auto' }}>
            {requests.map((req) => {
              const info = getStatusInfo(req.status);
              return (
                <div key={req.id} className="log-entry">
                  <span className="log-id">#{req.id}</span>
                  <span className={`status-badge ${info.color}`}>{info.label}</span>
                  <span className="log-body">
                    {typeof req.data === 'object' ? JSON.stringify(req.data) : String(req.data)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ClientSimulator;