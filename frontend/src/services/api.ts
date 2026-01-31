import axios from 'axios';

// Configure base URL
const api = axios.create({
    baseURL: 'http://localhost:8000',
});

export const api_service = {
    submitRequest: async (data: {
        customer_name: string;
        requested_discount: string;
        reason: string;
        requestor_email: string;
    }) => {
        const res = await api.post('/request/submit', data);
        return res.data;
    },

    sendApprovalEmail: async (requestId: string, managerEmail: string) => {
        const res = await api.post(`/request/${requestId}/send-email`, null, {
            params: { manager_email: managerEmail }
        });
        return res.data;
    },

    checkRequestStatus: async (requestId: string) => {
        const res = await api.get(`/request/${requestId}/status`);
        return res.data;
    },

    chat: async (question: string) => {
        const res = await api.post('/chat', { question });
        return res.data;
    },
};
