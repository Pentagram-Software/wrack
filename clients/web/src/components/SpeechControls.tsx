'use client';

import { useState } from 'react';
import { SpeakerWaveIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { robotController } from '@/lib/robot-api';

export default function SpeechControls() {
  const [text, setText] = useState('');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  const MAX_CHARACTERS = 500;

  const handleSpeak = async () => {
    if (!text.trim()) {
      toast.error('Please enter text to speak');
      return;
    }

    if (text.length > MAX_CHARACTERS) {
      toast.error(`Text too long. Maximum ${MAX_CHARACTERS} characters allowed.`);
      return;
    }

    setIsSpeaking(true);
    try {
      const response = await robotController.speak(text);

      if (response.success) {
        toast.success(`Speaking: "${text}"`);
        setText(''); // Clear input after successful speech
      } else {
        toast.error('Failed to send speech command');
      }
    } catch (error) {
      console.error('Speech error:', error);
      toast.error(error instanceof Error ? error.message : 'Error sending speech command');
    } finally {
      setIsSpeaking(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSpeak();
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newText = e.target.value;
    if (newText.length <= MAX_CHARACTERS) {
      setText(newText);
    }
  };

  // Quick preset messages
  const presetMessages = [
    'Hello',
    'Starting mission',
    'Obstacle detected',
    'Mission complete',
  ];

  const handlePreset = (message: string) => {
    setText(message);
  };

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between bg-gray-700 hover:bg-gray-600 transition-colors"
      >
        <div className="flex items-center gap-2">
          <SpeakerWaveIcon className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Speech Control</h2>
        </div>
        <span className="text-gray-400 text-sm">
          {isExpanded ? '▼' : '▶'}
        </span>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Text Input */}
          <div>
            <label htmlFor="speech-text" className="block text-sm font-medium text-gray-300 mb-2">
              Text to Speak
            </label>
            <textarea
              id="speech-text"
              value={text}
              onChange={handleTextChange}
              onKeyPress={handleKeyPress}
              placeholder="Enter text for EV3 to speak..."
              maxLength={MAX_CHARACTERS}
              rows={3}
              disabled={isSpeaking}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed resize-none"
            />
            <div className="flex justify-between items-center mt-1">
              <span className="text-xs text-gray-400">
                Press Enter to speak
              </span>
              <span className={`text-xs ${text.length > MAX_CHARACTERS * 0.9 ? 'text-yellow-400' : 'text-gray-400'}`}>
                {text.length}/{MAX_CHARACTERS}
              </span>
            </div>
          </div>

          {/* Preset Messages */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Quick Messages
            </label>
            <div className="grid grid-cols-2 gap-2">
              {presetMessages.map((message) => (
                <button
                  key={message}
                  onClick={() => handlePreset(message)}
                  disabled={isSpeaking}
                  className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {message}
                </button>
              ))}
            </div>
          </div>

          {/* Speak Button */}
          <button
            onClick={handleSpeak}
            disabled={!text.trim() || isSpeaking}
            className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            <SpeakerWaveIcon className="w-5 h-5" />
            {isSpeaking ? 'Speaking...' : 'Speak'}
          </button>
        </div>
      )}
    </div>
  );
}
