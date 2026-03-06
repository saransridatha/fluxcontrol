import { useEffect, useState, useRef, useCallback } from 'react';

const toHex = (buffer) =>
  Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');

const sha256 = async (value) => {
  const encoded = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest('SHA-256', encoded);
  return toHex(digest);
};

const ShieldModeVisualizer = ({ challenge, difficulty, onSolve }) => {
  const [nonce, setNonce] = useState(0);
  const [hash, setHash] = useState('');
  const [isMining, setIsMining] = useState(false);
  const [startTime, setStartTime] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const cancelledRef = useRef(false);
  const timerRef = useRef(null);

  const prefix = '0'.repeat(difficulty);

  // Elapsed time ticker
  useEffect(() => {
    if (isMining && startTime) {
      timerRef.current = setInterval(() => {
        setElapsed(((Date.now() - startTime) / 1000).toFixed(1));
      }, 100);
    }
    return () => clearInterval(timerRef.current);
  }, [isMining, startTime]);

  useEffect(() => {
    cancelledRef.current = false;

    const mine = () => {
      setIsMining(true);
      setStartTime(Date.now());
      let currentNonce = 0;

      const step = async () => {
        if (cancelledRef.current) return;

        const batchSize = 500;
        for (let i = 0; i < batchSize; i++) {
          if (cancelledRef.current) return;

          const attempt = challenge + String(currentNonce);
          const currentHash = await sha256(attempt);

          if (currentHash.startsWith(prefix)) {
            setNonce(currentNonce);
            setHash(currentHash);
            setIsMining(false);
            onSolve(String(currentNonce));
            return;
          }
          currentNonce++;
        }

        // Update UI once per batch instead of every nonce
        setNonce(currentNonce);
        const displayHash = await sha256(challenge + String(currentNonce - 1));
        setHash(displayHash);

        requestAnimationFrame(step);
      };
      step();
    };

    if (challenge && difficulty) mine();

    return () => {
      cancelledRef.current = true;
      setIsMining(false);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [challenge, difficulty]);

  // Render the hash with color-coded leading chars
  const renderHash = (h) => {
    if (!h) return null;
    const matchLen = Math.min(difficulty, h.length);
    const matched = h.substring(0, matchLen);
    const rest = h.substring(matchLen);
    const allMatch = matched === '0'.repeat(matchLen);
    return (
      <span>
        <span className={allMatch ? 'match' : 'no-match'}>{matched}</span>
        <span className="no-match">{rest}</span>
      </span>
    );
  };

  return (
    <div className="mining-card">
      {/* PoW Explainer — pitch-deck friendly */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#c084fc', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>🔐</span> Proof-of-Work Challenge Active
        </div>
        <p style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: 1.6, margin: '0 0 16px' }}>
          When the system detects suspicious traffic, it activates <strong style={{ color: '#e2e8f0' }}>Shield Mode</strong>.
          Instead of blocking users, it issues a <strong style={{ color: '#e2e8f0' }}>computational puzzle</strong> —
          the client must find a number (nonce) that, combined with the challenge, produces a hash starting with
          <strong style={{ color: '#4ade80' }}> {difficulty} zeroes</strong>.
          This makes automated attacks expensive while letting real users through.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="explainer-step">
            <div className="step-number">1</div>
            <div className="step-text">
              <strong>Server sends a challenge</strong> — in this case, the client's IP address: <code style={{ color: '#818cf8' }}>{challenge}</code>
            </div>
          </div>
          <div className="explainer-step">
            <div className="step-number">2</div>
            <div className="step-text">
              <strong>Client tries random nonces:</strong> compute <code style={{ color: '#818cf8' }}>SHA-256(challenge + nonce)</code> until
              the result starts with <strong style={{ color: '#4ade80' }}>{difficulty} zeroes</strong>
            </div>
          </div>
          <div className="explainer-step">
            <div className="step-number">3</div>
            <div className="step-text">
              <strong>Found it?</strong> Send the nonce back. The server verifies in one hash — cheap to verify, expensive to solve.
              This is the same principle behind Bitcoin mining.
            </div>
          </div>
        </div>
      </div>

      {/* Difficulty visualizer */}
      <div style={{ marginBottom: 16 }}>
        <div className="label">Required Hash Prefix</div>
        <div className="zeroes-display">
          {Array.from({ length: Math.min(difficulty, 8) }).map((_, i) => (
            <div key={i} className="zero-block required">0</div>
          ))}
          {Array.from({ length: Math.max(0, 8 - difficulty) }).map((_, i) => (
            <div key={`r${i}`} className="zero-block remaining">?</div>
          ))}
          <span style={{ fontSize: '0.78rem', color: '#94a3b8', marginLeft: 8 }}>
            …remaining 56 hex characters can be anything
          </span>
        </div>
      </div>

      {/* Live mining stats */}
      {isMining ? (
        <>
          <div className="mining-progress">
            <div className="mining-progress-bar" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, margin: '16px 0' }}>
            <div className="stat-box">
              <div className="stat-value">{elapsed}s</div>
              <div className="stat-label">Elapsed</div>
            </div>
            <div className="stat-box">
              <div className="stat-value">{nonce.toLocaleString()}</div>
              <div className="stat-label">Nonces Tried</div>
            </div>
            <div className="stat-box">
              <div className="stat-value" style={{ color: '#c084fc' }}>⛏️</div>
              <div className="stat-label">Mining…</div>
            </div>
          </div>

          <div style={{ marginTop: 8 }}>
            <div className="label">Current Attempt</div>
            <div style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: 4 }}>
              Input: <code style={{ color: '#818cf8' }}>{challenge}{nonce}</code>
            </div>
            <div className="hash-display">
              SHA-256 → {renderHash(hash)}
            </div>
          </div>
        </>
      ) : hash ? (
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <div style={{ fontSize: '1.8rem', marginBottom: 8 }}>✅</div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#4ade80', marginBottom: 4 }}>
            Solution Found!
          </div>
          <div style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: 12 }}>
            Nonce <strong style={{ color: '#e2e8f0' }}>{nonce.toLocaleString()}</strong> produces a valid hash
          </div>
          <div className="hash-display" style={{ textAlign: 'left' }}>
            {renderHash(hash)}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default ShieldModeVisualizer;