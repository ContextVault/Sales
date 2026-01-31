import { motion } from 'framer-motion';
import { CheckCircle, AlertTriangle } from 'lucide-react';

export default function EnrichmentFlow({ data, onContinue }: any) {
    return (
        <div className="max-w-4xl mx-auto">
            <div className="bg-white shadow rounded-lg p-8">
                <h2 className="text-2xl font-bold mb-6">Analyzing Request...</h2>

                <div className="space-y-4">
                    {/* CRM Data */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.2 }}
                        className="bg-blue-50 border-l-4 border-blue-500 p-4"
                    >
                        <div className="flex items-start">
                            <CheckCircle className="w-6 h-6 text-blue-500 mr-3 flex-shrink-0" />
                            <div className="flex-1">
                                <p className="font-medium text-blue-900">Customer Data (Salesforce)</p>
                                <div className="mt-2 text-sm text-blue-800 space-y-1">
                                    <p>-  ARR: ${data.enrichment.crm.arr?.toLocaleString() ?? 0}</p>
                                    <p>-  Industry: {data.enrichment.crm.industry}</p>
                                    <p>-  Tier: {data.enrichment.crm.tier}</p>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Support Data */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.4 }}
                        className="bg-green-50 border-l-4 border-green-500 p-4"
                    >
                        <div className="flex items-start">
                            <CheckCircle className="w-6 h-6 text-green-500 mr-3 flex-shrink-0" />
                            <div className="flex-1">
                                <p className="font-medium text-green-900">Support Tickets (Zendesk)</p>
                                <div className="mt-2 text-sm text-green-800 space-y-1">
                                    <p>-  SEV-1 Tickets: {data.enrichment.support.sev1_tickets}</p>
                                    <p>-  SEV-2 Tickets: {data.enrichment.support.sev2_tickets}</p>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Finance Data */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.6 }}
                        className="bg-purple-50 border-l-4 border-purple-500 p-4"
                    >
                        <div className="flex items-start">
                            <CheckCircle className="w-6 h-6 text-purple-500 mr-3 flex-shrink-0" />
                            <div className="flex-1">
                                <p className="font-medium text-purple-900">Financial Data (Stripe)</p>
                                <div className="mt-2 text-sm text-purple-800 space-y-1">
                                    <p>-  Margin: {data.enrichment.finance.margin_percent}%</p>
                                    <p>-  Payment History: {data.enrichment.finance.payment_history}</p>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Policy Evaluation */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.8 }}
                        className={`border-l-4 p-4 ${data.policy_evaluation.exceeds_limit
                                ? 'bg-yellow-50 border-yellow-500'
                                : 'bg-green-50 border-green-500'
                            }`}
                    >
                        <div className="flex items-start">
                            {data.policy_evaluation.exceeds_limit ? (
                                <AlertTriangle className="w-6 h-6 text-yellow-500 mr-3 flex-shrink-0" />
                            ) : (
                                <CheckCircle className="w-6 h-6 text-green-500 mr-3 flex-shrink-0" />
                            )}
                            <div className="flex-1">
                                <p className={`font-medium ${data.policy_evaluation.exceeds_limit ? 'text-yellow-900' : 'text-green-900'
                                    }`}>
                                    Policy Evaluation (v{data.policy_evaluation.version})
                                </p>
                                <div className={`mt-2 text-sm space-y-1 ${data.policy_evaluation.exceeds_limit ? 'text-yellow-800' : 'text-green-800'
                                    }`}>
                                    <p>-  Standard Limit: {data.policy_evaluation.standard_limit}</p>
                                    {data.policy_evaluation.exceeds_limit ? (
                                        <>
                                            <p className="font-medium">⚠️ Exceeds limit by {data.policy_evaluation.deviation}</p>
                                            <p>-  Requires: {data.approval_level.toUpperCase()} approval</p>
                                        </>
                                    ) : (
                                        <p className="font-medium">✓ Within policy limits</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Precedents */}
                    {data.precedents && data.precedents.length > 0 && (
                        <motion.div
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 1.0 }}
                            className="bg-indigo-50 border-l-4 border-indigo-500 p-4"
                        >
                            <div className="flex items-start">
                                <CheckCircle className="w-6 h-6 text-indigo-500 mr-3 flex-shrink-0" />
                                <div className="flex-1">
                                    <p className="font-medium text-indigo-900">Similar Precedents</p>
                                    <div className="mt-2 text-sm text-indigo-800 space-y-1">
                                        {data.precedents.slice(0, 3).map((p: any, i: number) => (
                                            <p key={i}>
                                                -  {p.customer}: {p.outcome} ({(p.similarity * 100).toFixed(0)}% similar)
                                            </p>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </div>

                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 1.2 }}
                    className="mt-8"
                >
                    <button
                        onClick={onContinue}
                        className="w-full px-6 py-3 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 font-medium transition-colors"
                    >
                        {data.requires_approval
                            ? 'Send Approval Request to Manager'
                            : 'Auto-Approve Request'}
                    </button>
                </motion.div>
            </div>
        </div>
    );
}
