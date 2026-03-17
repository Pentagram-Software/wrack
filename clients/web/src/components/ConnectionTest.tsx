'use client';

import { useState } from 'react';
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/solid';
import { robotController } from '@/lib/robot-api';
import toast from 'react-hot-toast';

export default function ConnectionTest() {
  const [testing, setTesting] = useState(false);
  const [lastResult, setLastResult] = useState<any>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const testConnection = async () => {
    setTesting(true);
    try {
      console.log('🧪 Testing GCP connection...');
      const response = await robotController.getStatus();
      console.log('✅ Test successful:', response);
      setLastResult(response);
      toast.success('GCP connection successful!');
    } catch (error) {
      console.log('❌ Test failed:', error);
      setLastResult({ error: error instanceof Error ? error.message : 'Unknown error' });
      toast.error(`GCP connection failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-gray-700 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between">
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center space-x-2 text-white hover:text-blue-400 transition-colors"
        >
          {isExpanded ? (
            <ChevronDownIcon className="w-5 h-5" />
          ) : (
            <ChevronRightIcon className="w-5 h-5" />
          )}
          <h3 className="text-lg font-semibold">GCP Connection Test</h3>
        </button>
        
        <div className="flex items-center space-x-3">
          <div className={`w-2 h-2 rounded-full ${
            robotController.getConnectionStatus() === 'connected' ? 'bg-green-500' : 
            robotController.getConnectionStatus() === 'error' ? 'bg-red-500' : 'bg-gray-500'
          }`} />
          <button
            onClick={testConnection}
            disabled={testing}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              testing 
                ? 'bg-gray-600 text-gray-400 cursor-not-allowed' 
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {testing ? 'Testing...' : 'Test'}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-3">
          {lastResult && (
            <div className="bg-gray-800 rounded p-3">
              <h4 className="text-sm font-medium text-gray-300 mb-2">Last Test Result:</h4>
              <pre className="text-xs text-gray-400 whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(lastResult, null, 2)}
              </pre>
            </div>
          )}

          <div className="text-xs text-gray-400 space-y-1">
            <div>Status: <span className="font-mono">{robotController.getConnectionStatus()}</span></div>
            <div>URL: <span className="font-mono text-blue-300">{process.env.NEXT_PUBLIC_GCP_FUNCTION_URL}</span></div>
            <div>API Key: <span className="font-mono">{process.env.NEXT_PUBLIC_API_KEY?.substring(0, 8)}...</span></div>
            {robotController.getLastError() && (
              <div>Last Error: <span className="font-mono text-red-400">{robotController.getLastError()}</span></div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}