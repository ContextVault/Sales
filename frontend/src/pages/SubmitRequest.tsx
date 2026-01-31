import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api_service } from '../services/api';
import { useNavigate } from 'react-router-dom';
import EnrichmentFlow from '../components/EnrichmentFlow';

export default function SubmitRequest() {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        customer_name: '',
        requested_discount: '',
        reason: '',
        requestor_email: 'john.sales@company.com' // Default
    });
    const [enrichedData, setEnrichedData] = useState<any>(null);

    const submitMutation = useMutation({
        mutationFn: (data: any) => api_service.submitRequest(data),
        onSuccess: (data) => {
            setEnrichedData(data);
        }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        submitMutation.mutate(formData);
    };

    if (enrichedData) {
        return (
            <EnrichmentFlow
                data={enrichedData}
                onContinue={() => navigate(`/request/${enrichedData.request_id}/email`)}
            />
        );
    }

    return (
        <div className="max-w-2xl mx-auto">
            <div className="bg-white shadow rounded-lg p-8">
                <h1 className="text-2xl font-bold mb-6 text-gray-900">Submit Discount Request</h1>

                <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Customer Name
                        </label>
                        <input
                            type="text"
                            required
                            value={formData.customer_name}
                            onChange={(e) => setFormData({ ...formData, customer_name: e.target.value })}
                            className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 outline-none"
                            placeholder="MedTech Corp"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Requested Discount (%)
                        </label>
                        <input
                            type="text"
                            required
                            value={formData.requested_discount}
                            onChange={(e) => setFormData({ ...formData, requested_discount: e.target.value })}
                            className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 outline-none"
                            placeholder="18%"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Reason for Request
                        </label>
                        <textarea
                            required
                            rows={4}
                            value={formData.reason}
                            onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                            className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 outline-none"
                            placeholder="Customer has 3 SEV-1 incidents and is threatening to churn..."
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={submitMutation.isPending}
                        className="w-full px-6 py-3 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-indigo-400 font-medium transition-colors"
                    >
                        {submitMutation.isPending ? 'Processing...' : 'Submit Request'}
                    </button>
                </form>
            </div>
        </div>
    );
}
