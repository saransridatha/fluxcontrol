import axios from 'axios';

const API_URL = import.meta.env.DEV
    ? '/api'
    : 'https://41osqgw03d.execute-api.ap-northeast-1.amazonaws.com/prod';

export const getAdminData = () => axios.get(`${API_URL}/admin`);

export const postAdminAction = (action, ip) => {
  return axios.post(`${API_URL}/admin`, { action, ip });
};

export const postConfig = (config) => {
    return axios.post(`${API_URL}/admin`, { action: 'config', ...config });
};

export const makeProxyRequest = (solution) => {
    const headers = {};
    if (solution) {
        headers['X-Puzzle-Solution'] = solution;
    }
    return axios.get(`${API_URL}/proxy`, { headers });
};
