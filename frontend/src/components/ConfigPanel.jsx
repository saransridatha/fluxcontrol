import { useState } from 'react';
import { postConfig } from '../api';
import { useToast } from './ToastProvider';

const ConfigPanel = () => {
  const [config, setConfig] = useState({
    mode: 'normal',
    rate_limit: 5,
    cpu_threshold: 80,
    difficulty: 3,
  });
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const handleChange = (name, value) => {
    setConfig((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await postConfig(config);
      toast.success('Configuration updated successfully');
    } catch (error) {
      toast.error('Config update failed: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <span>⚙️</span>
        <span>System Configuration</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label className="label">System Mode</label>
          <select
            className="input-field"
            value={config.mode}
            onChange={(e) => handleChange('mode', e.target.value)}
          >
            <option value="normal">Normal — standard rate limiting</option>
            <option value="shield">Shield — PoW challenge active</option>
          </select>
        </div>

        <div>
          <label className="label">Rate Limit (per 10s window)</label>
          <input
            className="input-field"
            type="number"
            min={1}
            max={100}
            value={config.rate_limit}
            onChange={(e) => handleChange('rate_limit', parseInt(e.target.value || '0', 10))}
          />
        </div>

        <div>
          <label className="label">CPU Threshold (%)</label>
          <input
            className="input-field"
            type="number"
            min={1}
            max={100}
            value={config.cpu_threshold}
            onChange={(e) => handleChange('cpu_threshold', parseInt(e.target.value || '0', 10))}
          />
        </div>

        <div>
          <label className="label">Shield Difficulty (leading zeroes)</label>
          <input
            className="input-field"
            type="number"
            min={1}
            max={8}
            value={config.difficulty}
            onChange={(e) => handleChange('difficulty', parseInt(e.target.value || '0', 10))}
          />
          <div style={{ marginTop: 6 }}>
            <div className="zeroes-display">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className={`zero-block ${i < config.difficulty ? 'required' : 'remaining'}`}>
                  0
                </div>
              ))}
              <span style={{ fontSize: '0.72rem', color: '#64748b', marginLeft: 6 }}>
                {config.difficulty} zeroes required
              </span>
            </div>
          </div>
        </div>

        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={saving}
          style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
        >
          {saving ? '⏳ Saving...' : '✓ Apply Configuration'}
        </button>
      </div>
    </div>
  );
};

export default ConfigPanel;