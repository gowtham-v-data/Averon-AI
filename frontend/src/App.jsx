import { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import './index.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

function stripMarkdown(text) {
    if (!text) return '';
    let plain = text;
    // Remove code blocks
    plain = plain.replace(/```[\s\S]*?```/g, '');
    // Remove inline code
    plain = plain.replace(/`([^`]+)`/g, '$1');
    // Remove bold/italics
    plain = plain.replace(/\*\*?(.+?)\*\*?/g, '$1');
    // Remove headers
    plain = plain.replace(/^#+ (.+)$/gm, '$1');
    // Remove links
    plain = plain.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1');
    // Remove list markers
    plain = plain.replace(/^[*-] /gm, '');
    plain = plain.replace(/^\d+\. /gm, '');
    // Remove extra whitespace
    return plain.trim();
}

// ─── Simple Markdown Parser ──────────────────────────
function parseMarkdown(text) {
    if (!text) return '';
    let html = text;

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="lang-$1">$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br/>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>(<h[1-3]>)/g, '$1');
    html = html.replace(/(<\/h[1-3]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<pre>)/g, '$1');
    html = html.replace(/(<\/pre>)<\/p>/g, '$1');
    html = html.replace(/<p>(<ul>)/g, '$1');
    html = html.replace(/(<\/ul>)<\/p>/g, '$1');
    html = html.replace(/<p>(<blockquote>)/g, '$1');
    html = html.replace(/(<\/blockquote>)<\/p>/g, '$1');
    return html;
}

// ─── Suggestion Chips ────────────────────────────────
const SUGGESTIONS = [
    "Explain how AI works",
    "Help me write a poem",
    "Summarize my uploaded PDF",
    "Build me a portfolio website",
    "What can you do?",
    "Tell me a fun fact",
];

// ─── App Component ───────────────────────────────────
export default function App() {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [uploadStatus, setUploadStatus] = useState(null);
    const [voiceResponse, setVoiceResponse] = useState(false);
    const [autoSendVoice, setAutoSendVoice] = useState(true);
    const [isListening, setIsListening] = useState(false);
    const [speakingIndex, setSpeakingIndex] = useState(null);
    const [ttsLoading, setTtsLoading] = useState(null); // msg index
    const [builderStates, setBuilderStates] = useState({}); // { msgIndex: { mode: 'preview', fileIndex: 0 } }

    const chatEndRef = useRef(null);
    const textareaRef = useRef(null);
    const fileInputRef = useRef(null);
    const recognitionRef = useRef(null);
    const audioRef = useRef(null);

    // Scroll to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, loading]);

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
        }
    }, [input]);

    const fetchFiles = useCallback(async () => {
        try {
            const res = await axios.get(`${API_BASE}/files`);
            setUploadedFiles(res.data.files || []);
        } catch (err) {
            console.error('Failed to fetch files:', err);
        }
    }, []);

    // ─── TTS ───────────────────────────────────────────
    const handleTTS = useCallback(async (text, index) => {
        if (!text) return;

        // If clicking the same message that is already playing, stop it
        if (speakingIndex === index && audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
            setSpeakingIndex(null);
            return;
        }

        // Stop any currently playing audio
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }

        try {
            setTtsLoading(index);
            const cleanText = stripMarkdown(text);
            const res = await axios.post(`${API_BASE}/tts`, { text: cleanText }, { responseType: 'blob' });

            // Check if we got an error instead of audio (blob might contain JSON error)
            if (res.data.type === 'application/json') {
                const textError = await res.data.text();
                const errorObj = JSON.parse(textError);
                throw new Error(errorObj.error || 'TTS generation failed');
            }

            const audioBlob = new Blob([res.data], { type: 'audio/mpeg' });
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            audioRef.current = audio;

            // Handle browser play restrictions
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise.then(() => {
                    setSpeakingIndex(index);
                    setTtsLoading(null);
                }).catch(error => {
                    console.warn('TTS Playback blocked:', error);
                    // Chrome and some browsers block auto-play until a direct interaction
                    alert("Click anywhere on the page first to enable audio, then try again.");
                    setSpeakingIndex(null);
                    setTtsLoading(null);
                });
            }

            audio.onended = () => {
                URL.revokeObjectURL(audioUrl);
                setSpeakingIndex(null);
                audioRef.current = null;
            };
        } catch (err) {
            console.error('TTS error:', err);
            setTtsLoading(null);
            setSpeakingIndex(null);
        }
    }, [speakingIndex]);

    // ─── Send Message ──────────────────────────────────
    const sendMessage = useCallback(async (msgText) => {
        const text = (msgText || input).trim();
        if (!text || loading) return;

        const userMsg = { role: 'user', content: text };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            const res = await axios.post(`${API_BASE}/chat`, { message: text });

            if (res.data.builder) {
                const parsed = JSON.parse(res.data.builder);
                const assistantMsg = {
                    role: 'assistant',
                    content: `✅ Your website has been generated with **${parsed.files.length} files**! Preview it below.`,
                    builder: parsed,
                };
                setMessages(prev => [...prev, assistantMsg]);
            } else {
                const assistantMsg = { role: 'assistant', content: res.data.reply };
                setMessages(prev => [...prev, assistantMsg]);

                // Auto TTS if voice response enabled
                if (voiceResponse && res.data.reply) {
                    handleTTS(res.data.reply, messages.length + 1);
                }
            }
        } catch (err) {
            console.error('Chat error:', err);
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: '⚠️ Sorry, something went wrong. Please check that the backend is running and try again.',
            }]);
        } finally {
            setLoading(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [input, loading, voiceResponse, messages.length]);

    // Fetch files on mount
    useEffect(() => {
        fetchFiles();
    }, [fetchFiles]);

    const autoSendVoiceRef = useRef(autoSendVoice);
    useEffect(() => {
        autoSendVoiceRef.current = autoSendVoice;
    }, [autoSendVoice]);

    // ─── Voice Recognition Setup ─────────────────────
    useEffect(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return;

        if (!recognitionRef.current) {
            const recognition = new SpeechRecognition();
            recognition.lang = 'en-US';
            recognition.interimResults = false;
            recognition.continuous = false;

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                setInput(prev => {
                    const newText = prev ? prev + ' ' + transcript : transcript;
                    if (autoSendVoiceRef.current) {
                        setTimeout(() => sendMessage(newText), 100);
                    }
                    return newText;
                });
                setIsListening(false);
            };

            recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                setIsListening(false);
            };

            recognition.onend = () => {
                setIsListening(false);
            };

            recognitionRef.current = recognition;
        }
    }, [sendMessage]);

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    // ─── File Upload ───────────────────────────────────
    const handleFileUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploadStatus({ type: 'loading', message: `Uploading ${file.name}...` });

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await axios.post(`${API_BASE}/upload`, formData);
            if (res.data.error) {
                setUploadStatus({ type: 'error', message: res.data.error });
            } else {
                setUploadStatus({ type: 'success', message: `${file.name} uploaded.` });
                fetchFiles();
            }
        } catch {
            setUploadStatus({ type: 'error', message: 'Upload failed.' });
        }

        setTimeout(() => setUploadStatus(null), 4000);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleCopy = (text) => navigator.clipboard.writeText(text);

    // ─── New Chat ──────────────────────────────────────
    const handleNewChat = async () => {
        try { await axios.post(`${API_BASE}/clear-chat`); } catch { /* Ignore errors */ }
        setMessages([]);
        setSidebarOpen(false);
    };

    // ─── Clear Docs ────────────────────────────────────
    const handleClearDocs = async () => {
        try {
            await axios.post(`${API_BASE}/clear-docs`);
            setUploadedFiles([]);
        } catch { /* Ignore errors */ }
    };

    // ─── Builder Helpers ───────────────────────────────
    const setBuilderMode = (msgIndex, mode) => {
        setBuilderStates(prev => ({
            ...prev,
            [msgIndex]: { ...prev[msgIndex], mode }
        }));
    };

    const setBuilderFile = (msgIndex, fileIndex) => {
        setBuilderStates(prev => ({
            ...prev,
            [msgIndex]: { ...prev[msgIndex], fileIndex }
        }));
    };

    const downloadBuilderFiles = (files) => {
        files.forEach((f) => {
            const blob = new Blob([f.content], { type: 'text/plain' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = f.name;
            a.click();
        });
    };

    const getBuilderPreviewSrc = (builderFiles) => {
        const htmlFile = builderFiles.find(f => f.name === 'index.html');
        if (!htmlFile) return '';

        let htmlContent = htmlFile.content;

        // Find style and script files
        const styleFile = builderFiles.find(f => f.name.includes('.css') || f.name === 'style.css');
        const scriptFile = builderFiles.find(f => f.name.includes('.js') || f.name === 'script.js');

        // Inject CSS if found and doesn't already have it
        if (styleFile && !htmlContent.includes(`<style>${styleFile.content}`)) {
            if (htmlContent.includes('</head>')) {
                htmlContent = htmlContent.replace('</head>', `<style>\n${styleFile.content}\n</style>\n</head>`);
            } else {
                htmlContent = `<style>\n${styleFile.content}\n</style>\n` + htmlContent;
            }
        }

        // Inject JS if found
        if (scriptFile && !htmlContent.includes(`<script>${scriptFile.content}`)) {
            if (htmlContent.includes('</body>')) {
                htmlContent = htmlContent.replace('</body>', `<script>\n${scriptFile.content}\n</script>\n</body>`);
            } else {
                htmlContent = htmlContent + `\n<script>\n${scriptFile.content}\n</script>`;
            }
        }

        return 'data:text/html;charset=utf-8,' + encodeURIComponent(htmlContent);
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'numeric', year: 'numeric' });
    };

    // ─── RENDER ────────────────────────────────────────
    return (
        <div className="app-layout">
            {/* Mobile Overlay */}
            <div
                className={`sidebar-overlay ${sidebarOpen ? 'active' : ''}`}
                onClick={() => setSidebarOpen(false)}
            />

            {/* ═══ SIDEBAR ═══ */}
            <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
                {/* Logo */}
                <div className="sidebar-header">
                    <div className="sidebar-logo">
                        <div className="logo-icon">A</div>
                        <h2>Averon</h2>
                    </div>
                </div>

                {/* New Conversation */}
                <button className="new-chat-btn" onClick={handleNewChat} id="new-chat-btn">
                    <span className="btn-icon">+</span>
                    New conversation
                </button>

                {/* Knowledge Base */}
                <div className="sidebar-section">
                    <div className="sidebar-section-title">Knowledge Base</div>

                    {/* Upload controls */}
                    <div className="upload-controls">
                        <button className="attach-file-btn" onClick={() => fileInputRef.current?.click()}>
                            Attach file
                        </button>
                        <button className="upload-btn" onClick={() => fileInputRef.current?.click()}>
                            Upload
                        </button>
                    </div>

                    {/* Upload status */}
                    {uploadStatus && (
                        <div className={`upload-status-inline ${uploadStatus.type}`}>
                            {uploadStatus.type === 'loading' && <><span className="spinner" /> {uploadStatus.message}</>}
                            {uploadStatus.type === 'success' && <>✓ {uploadStatus.message}</>}
                            {uploadStatus.type === 'error' && <>✗ {uploadStatus.message}</>}
                        </div>
                    )}

                    {/* Uploaded files */}
                    {uploadedFiles.map((f, i) => (
                        <div key={i} className="uploaded-file-item">
                            <span className="file-icon">📄</span>
                            <span>{f.filename}</span>
                            <span className="file-date">{formatDate(f.uploaded_at)}</span>
                        </div>
                    ))}

                    {/* Clear knowledge base */}
                    {uploadedFiles.length > 0 && (
                        <button className="clear-kb-btn" onClick={handleClearDocs}>
                            <span className="clear-icon">🗑</span>
                            Clear knowledge base
                        </button>
                    )}
                </div>

                {/* Voice Toggles */}
                <div className="sidebar-footer">
                    <div className="toggle-row">
                        <span className="toggle-label">Voice response</span>
                        <label className="toggle-switch">
                            <input
                                type="checkbox"
                                checked={voiceResponse}
                                onChange={() => setVoiceResponse(!voiceResponse)}
                            />
                            <span className="toggle-slider" />
                        </label>
                    </div>
                    <div className="toggle-row">
                        <span className="toggle-label">Auto-send voice</span>
                        <label className="toggle-switch">
                            <input
                                type="checkbox"
                                checked={autoSendVoice}
                                onChange={() => setAutoSendVoice(!autoSendVoice)}
                            />
                            <span className="toggle-slider" />
                        </label>
                    </div>
                </div>
            </aside>

            {/* ═══ MAIN AREA ═══ */}
            <main className="main-area">
                {/* Header */}
                <header className="main-header">
                    <div className="main-header-left">
                        <button
                            className="mobile-menu-btn"
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            id="mobile-menu-btn"
                        >
                            ☰
                        </button>
                        <div className="header-info">
                            <span className="header-title">Averon</span>
                            <span className="header-subtitle">AI Assistant</span>
                        </div>
                    </div>
                    <div className="header-right">
                        <span className="online-dot" />
                        <span className="online-label">Online</span>
                    </div>
                </header>

                {/* Chat */}
                <div className="chat-container">
                    {messages.length === 0 && !loading ? (
                        <div className="welcome-screen">
                            <div className="welcome-icon">A</div>
                            <h1>Hello, I'm Averon</h1>
                            <p>Your intelligent AI assistant. Ask me anything, upload documents for analysis, or ask me to build you a website.</p>
                            <div className="welcome-chips">
                                {SUGGESTIONS.map((s, i) => (
                                    <button key={i} className="welcome-chip" onClick={() => sendMessage(s)}>
                                        {s}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="chat-messages">
                            {messages.map((msg, i) => (
                                msg.role === 'user' ? (
                                    /* ── User Message (right bubble) ── */
                                    <div key={i} className="message user">
                                        <div className="user-bubble">{msg.content}</div>
                                    </div>
                                ) : (
                                    /* ── Assistant Message (left with avatar) ── */
                                    <div key={i} className="message assistant">
                                        <div className="message-avatar">A</div>
                                        <div className="message-content">
                                            <div
                                                className="message-text"
                                                dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
                                            />

                                            {/* Builder Block */}
                                            {msg.builder && (
                                                <div className="builder-container">
                                                    <div className="builder-header">
                                                        <div className="builder-tabs">
                                                            <button
                                                                className={`builder-tab ${builderStates[i]?.mode !== 'code' ? 'active' : ''}`}
                                                                onClick={() => setBuilderMode(i, 'preview')}
                                                            >
                                                                🌐 Preview
                                                            </button>
                                                            <button
                                                                className={`builder-tab ${builderStates[i]?.mode === 'code' ? 'active' : ''}`}
                                                                onClick={() => setBuilderMode(i, 'code')}
                                                            >
                                                                📄 View Code
                                                            </button>
                                                        </div>
                                                        <div className="builder-actions">
                                                            <button
                                                                className="builder-action-btn"
                                                                onClick={() => downloadBuilderFiles(msg.builder.files)}
                                                                title="Download all files"
                                                            >
                                                                ⬇ Download
                                                            </button>
                                                        </div>
                                                    </div>

                                                    {builderStates[i]?.mode === 'code' ? (
                                                        <div className="builder-code-view">
                                                            <div className="builder-file-explorer">
                                                                {msg.builder.files.map((f, j) => (
                                                                    <button
                                                                        key={j}
                                                                        className={`file-tab ${(builderStates[i]?.fileIndex || 0) === j ? 'active' : ''}`}
                                                                        onClick={() => setBuilderFile(i, j)}
                                                                    >
                                                                        {f.name}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                            <div className="builder-code-content">
                                                                <pre>
                                                                    <code>{msg.builder.files[builderStates[i]?.fileIndex || 0]?.content}</code>
                                                                </pre>
                                                            </div>
                                                        </div>
                                                    ) : (
                                                        <div className="builder-preview-view">
                                                            <iframe
                                                                className="builder-iframe"
                                                                src={getBuilderPreviewSrc(msg.builder.files)}
                                                                title="Website Preview"
                                                                sandbox="allow-scripts"
                                                            />
                                                            <div className="builder-files-status">
                                                                {msg.builder.files.map((f, j) => (
                                                                    <span key={j} className="builder-file-tag">{f.name}</span>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Action buttons */}
                                            <div className="message-actions">
                                                <button className="msg-action-btn" onClick={() => handleCopy(msg.content)} title="Copy">
                                                    📋
                                                </button>
                                                <button
                                                    className={`msg-action-btn ${speakingIndex === i ? 'speaking' : ''} ${ttsLoading === i ? 'loading' : ''}`}
                                                    onClick={() => handleTTS(msg.content, i)}
                                                    title={speakingIndex === i ? "Stop speaking" : "Read aloud"}
                                                    disabled={ttsLoading === i}
                                                >
                                                    {ttsLoading === i ? <span className="spinner" /> : (speakingIndex === i ? '⏹' : '🔊')}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )
                            ))}

                            {/* Loading */}
                            {loading && (
                                <div className="message assistant">
                                    <div className="message-avatar">A</div>
                                    <div className="message-content">
                                        <div className="typing-indicator">
                                            <span /><span /><span />
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div ref={chatEndRef} />
                        </div>
                    )}
                </div>

                {/* Input */}
                <div className="input-area">
                    <div className="input-wrapper">
                        <div className="input-box">
                            <textarea
                                ref={textareaRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Reply to Averon..."
                                rows={1}
                                disabled={loading}
                                id="chat-input"
                            />
                            <div className="input-actions">
                                <button
                                    className="input-action-btn"
                                    onClick={() => fileInputRef.current?.click()}
                                    title="Attach file"
                                >
                                    ✏️
                                </button>
                                <button
                                    className={`input-action-btn mic-btn ${isListening ? 'listening' : ''}`}
                                    onClick={() => {
                                        if (!recognitionRef.current) {
                                            alert('Voice input is not supported in this browser.');
                                            return;
                                        }
                                        if (isListening) {
                                            recognitionRef.current.stop();
                                            setIsListening(false);
                                        } else {
                                            recognitionRef.current.start();
                                            setIsListening(true);
                                        }
                                    }}
                                    title={isListening ? 'Stop listening' : 'Voice input'}
                                    id="mic-btn"
                                >
                                    {isListening ? '⏹' : '🎤'}
                                </button>
                                <button
                                    className="input-action-btn send-btn"
                                    onClick={() => sendMessage()}
                                    disabled={!input.trim() || loading}
                                    title="Send"
                                    id="send-btn"
                                >
                                    ↑
                                </button>
                            </div>
                        </div>
                        <div className="input-footer">
                            <span>Averon can make mistakes. Please double-check responses.</span>
                        </div>
                    </div>
                </div>

                {/* Hidden file input */}
                <input
                    type="file"
                    className="file-upload-input"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".pdf,.csv,.xlsx,.xls,.docx,.doc,.txt,.json"
                />
            </main>
        </div>
    );
}
