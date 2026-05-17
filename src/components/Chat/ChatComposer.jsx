import React, { useState, useRef, useEffect } from 'react';
import { sendChatMessage } from '../../services/chatService';
import './ChatComposer.css';

const ChatComposer = ({ onMessageSend }) => {
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleSubmit();
      }
    };

    const textarea = textareaRef.current;
    if (textarea) {
      textarea.addEventListener('keydown', handleKeyDown);
      return () => textarea.removeEventListener('keydown', handleKeyDown);
    }
  }, [message]);

  useEffect(() => {
    autoResizeTextarea();
  }, [message]);

  const autoResizeTextarea = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  };

  const handleSubmit = async () => {
    if (!message.trim() || isLoading) return;

    setIsLoading(true);
    const userMessage = message.trim();
    setMessage('');

    try {
      const response = await sendChatMessage(userMessage);
      onMessageSend(response);
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (e) => {
    setMessage(e.target.value);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-composer">
      <textarea
        ref={textareaRef}
        className="chat-input"
        placeholder="Type your message..."
        value={message}
        onChange={handleInputChange}
        onKeyPress={handleKeyPress}
        disabled={isLoading}
        rows={1}
      />
      <button
        className="send-button"
        onClick={handleSubmit}
        disabled={isLoading || !message.trim()}
      >
        {isLoading ? 'Sending...' : 'Send'}
      </button>
    </div>
  );
};

export default ChatComposer;