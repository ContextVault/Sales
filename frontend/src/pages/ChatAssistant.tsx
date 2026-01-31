import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api_service } from '../services/api';
import { Send, Bot, User } from 'lucide-react';

interface Message {
    role: 'user' | 'assistant';
    content: string;
    data?: any;
}

export default function ChatAssistant() {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: '👋 Hi! I can help you analyze past decisions. Try asking:\n\n-  "Who approved the most discounts last month?"\n-  "What\'s the approval rate for healthcare customers?"\n-  "Show me decisions that exceeded policy limits"'
        }
    ]);
    const [input, setInput] = useState('');

    const chatMutation = useMutation({
        mutationFn: (question: string) => api_service.chat(question),
        onSuccess: (data) => {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: data.answer,
                data: data.data
            }]);
        }
    });

    const handleSend = () => {
        if (!input.trim()) return;

        setMessages(prev => [...prev, { role: 'user', content: input }]);
        chatMutation.mutate(input);
        setInput('');
    };

    return (
        <div className="max-w-4xl mx-auto">
            <div className="bg-white shadow rounded-lg h-[700px] flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-200">
                    <h1 className="text-xl font-bold flex items-center gap-2">
                        <Bot className="w-6 h-6 text-indigo-600" />
                        Knowledge Graph Assistant
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Ask questions about past decisions, policies, and patterns
                    </p>
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {messages.map((msg, i) => (
                        <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`flex gap-3 max-w-[80%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === 'user' ? 'bg-indigo-600' : 'bg-gray-200'
                                    }`}>
                                    {msg.role === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-gray-600" />}
                                </div>

                                <div className={`rounded-lg px-4 py-3 ${msg.role === 'user'
                                        ? 'bg-indigo-600 text-white'
                                        : 'bg-gray-100 text-gray-900'
                                    }`}>
                                    <p className="whitespace-pre-wrap">{msg.content}</p>

                                    {msg.data && msg.data.length > 0 && (
                                        <div className="mt-3 pt-3 border-t border-gray-300/50">
                                            <p className="text-xs font-medium mb-2 opacity-70">Data from knowledge graph:</p>
                                            <div className="text-xs space-y-1 overflow-x-auto">
                                                {msg.data.slice(0, 3).map((item: any, j: number) => (
                                                    <div key={j} className="bg-white/50 rounded p-2 border border-gray-200/50">
                                                        <pre className="font-mono text-[10px]">{JSON.stringify(item, null, 2)}</pre>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}

                    {chatMutation.isPending && (
                        <div className="flex justify-start">
                            <div className="flex gap-3 max-w-[80%]">
                                <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                                    <Bot className="w-5 h-5 text-gray-600" />
                                </div>
                                <div className="bg-gray-100 rounded-lg px-4 py-3">
                                    <p className="text-gray-600">Thinking...</p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Input */}
                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
                    <div className="flex gap-2">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                            placeholder="Ask about past decisions..."
                            className="flex-1 rounded-md border border-gray-300 px-4 py-2 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
                        />
                        <button
                            onClick={handleSend}
                            disabled={chatMutation.isPending || !input.trim()}
                            className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-gray-400 transition-colors flex items-center justify-center"
                        >
                            <Send className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Suggested Questions */}
                    <div className="mt-3 flex flex-wrap gap-2">
                        {[
                            "Who approved the highest discount?",
                            "Show healthcare customer patterns",
                            "What's the average approval time?"
                        ].map((q, i) => (
                            <button
                                key={i}
                                onClick={() => { setInput(q); }}
                                className="text-xs px-3 py-1 bg-white border border-gray-200 text-gray-700 rounded-full hover:bg-gray-50 transition-colors"
                            >
                                {q}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
