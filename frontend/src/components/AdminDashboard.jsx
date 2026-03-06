import { useEffect, useState } from 'react';
import { getAdminData, postAdminAction } from '../api';
import { useToast } from './ToastProvider';

const AdminDashboard = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  const fetchData = async () => {
    try {
      const response = await getAdminData();
      setUsers(response.data);
    } catch (error) {
      toast.error('Failed to fetch admin data: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleAction = async (action, ip) => {
    try {
      await postAdminAction(action, ip);
      toast.success(`Action '${action}' successful for ${ip}`);
      fetchData();
    } catch (error) {
      toast.error(`Error: ${action} failed — ${error.message}`);
    }
  };

  const formatTime = (ts) => {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString();
  };

  return (
    <div className="card">
      <div className="card-header">
        <span>🛡️</span>
        <span>IP Reputation Monitor</span>
        <span style={{ marginLeft: 'auto', fontSize: '0.72rem', color: '#64748b', fontWeight: 500 }}>
          {loading ? 'Loading...' : `${users.length} IPs tracked`}
        </span>
      </div>

      {users.length === 0 && !loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#475569' }}>
          <div style={{ fontSize: '2rem', marginBottom: 8 }}>📡</div>
          <div style={{ fontSize: '0.85rem' }}>No IP data yet. Send some requests to populate.</div>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>IP Address</th>
              <th>Violations</th>
              <th>Last Seen</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.ip_address}>
                <td>
                  <code style={{ color: '#818cf8', fontSize: '0.82rem' }}>{user.ip_address}</code>
                </td>
                <td>
                  <span style={{
                    color: user.violation_count > 5 ? '#f87171' : user.violation_count > 0 ? '#facc15' : '#4ade80',
                    fontWeight: 700
                  }}>
                    {user.violation_count || 0}
                  </span>
                </td>
                <td style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
                  {formatTime(user.last_seen)}
                </td>
                <td>
                  {user.is_banned ? (
                    <span className="status-badge red">Banned</span>
                  ) : user.is_seamless ? (
                    <span className="status-badge green">Seamless</span>
                  ) : (
                    <span className="status-badge gray">Normal</span>
                  )}
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button className="btn btn-danger btn-sm" onClick={() => handleAction('ban', user.ip_address)}>
                      Ban
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => handleAction('unban', user.ip_address)}>
                      Unban
                    </button>
                    <button className="btn btn-success btn-sm" onClick={() => handleAction('seamless', user.ip_address)}>
                      Seamless
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => handleAction('unseamless', user.ip_address)}>
                      Remove
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default AdminDashboard;