import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api_service } from '../services/api';
import { Mail, CheckCircle, Clock } from 'lucide-react';

export default function EmailThread() {
    const { requestId } = useParams();

    // Start email simulation on mount
    const emailQuery = useQuery({
        queryKey: ['email', requestId],
        queryFn: async () => {
            // Create a simulated delay before showing "sent" state
            await new Promise(resolve => setTimeout(resolve, 1000));
            return api_service.sendApprovalEmail(requestId!, 'jane.manager@company.com');
        },
        enabled: !!requestId
    });

    // Poll for status update
    const statusQuery = useQuery({
        queryKey: ['status', requestId],
        queryFn: () => api_service.checkRequestStatus(requestId!),
        enabled: !!requestId && emailQuery.isSuccess,
        refetchInterval: (query) => {
            // Stop polling if approved
            if (query.state.data?.status === 'approved') return false;
            return 2000; // Poll every 2s
        }
    });

    const isApproved = statusQuery.data?.status === 'approved';

    return (
        <div className="max-w-4xl mx-auto space-y-8">
            {/* Thread Header */}
            <div className="bg-white shadow rounded-lg p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                    <h1 className="text-xl font-bold flex items-center gap-2">
                        <Mail className="w-6 h-6 text-gray-500" />
                        Approval Thread
                    </h1>
                    <div className="px-3 py-1 bg-gray-100 rounded-full text-sm font-medium text-gray-600">
                        Request ID: {requestId}
                    </div>
                </div>
            </div>

            {/* Email 1: Request */}
            {emailQuery.isSuccess && (
                <div className="bg-white shadow rounded-lg overflow-hidden">
                    <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                        <div>
                            <h3 className="font-bold text-gray-900">John Sales</h3>
                            <p className="text-sm text-gray-500">To: Jane Manager</p>
                        </div>
                        <span className="text-xs text-gray-400">Just now</span>
                    </div>
                    <div className="p-6 whitespace-pre-wrap font-sans text-gray-800">
                        {emailQuery.data.email_body}
                    </div>
                </div>
            )}

            {/* Loading State or Approved Response */}
            {emailQuery.isSuccess && !isApproved && (
                <div className="flex items-center justify-center py-8 opacity-70 animate-pulse">
                    <Clock className="w-5 h-5 mr-2 text-gray-500" />
                    <span className="text-gray-500">Waiting for manager reply...</span>
                </div>
            )}

            {isApproved && (
                <div className="bg-white shadow rounded-lg overflow-hidden border-2 border-green-500">
                    <div className="bg-green-50 px-6 py-4 border-b border-green-100 flex justify-between items-center">
                        <div>
                            <h3 className="font-bold text-green-900 flex items-center gap-2">
                                Jane Manager
                                <span className="px-2 py-0.5 bg-green-200 text-green-800 text-xs rounded-full">APPROVED</span>
                            </h3>
                            <p className="text-sm text-green-700">To: John Sales</p>
                        </div>
                        <span className="text-xs text-green-600">Just now</span>
                    </div>
                    <div className="p-6">
                        <p className="mb-4">Approved at {statusQuery.data.final_discount}.</p>
                        <div className="bg-gray-50 p-4 rounded-md border border-gray-200 text-sm text-gray-600 italic">
                            {statusQuery.data.reasoning}
                        </div>
                        <div className="mt-6 flex items-center text-sm text-green-700 font-medium">
                            <CheckCircle className="w-4 h-4 mr-2" />
                            Decision recorded in Context Graph
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
