import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import SubmitRequest from './pages/SubmitRequest';
import ChatAssistant from './pages/ChatAssistant';
import EmailThread from './pages/EmailThread';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    }
  }
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<SubmitRequest />} />
            <Route path="chat" element={<ChatAssistant />} />
            <Route path="request/:requestId/email" element={<EmailThread />} />
            <Route path="graph" element={
              <div className="text-center py-20 text-gray-500">
                Graph Explorer Placeholder
              </div>
            } />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
