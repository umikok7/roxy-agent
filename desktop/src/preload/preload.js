const { contextBridge, ipcRenderer } = require('electron');

const API_BASE_URL = 'http://localhost:8000';

async function parseStreamResponse(response) {
    const rawText = await response.text();
    const events = [];
    const blocks = rawText.split(/\n\n+/);

    for (const block of blocks) {
        const dataLines = block
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trim())
            .filter(Boolean);

        if (dataLines.length === 0) continue;

        try {
            events.push(JSON.parse(dataLines.join('\n')));
        } catch (error) {
            console.warn('Failed to parse SSE payload in preload:', error);
        }
    }

    return events;
}

// Secure IPC bridge - only expose necessary APIs
contextBridge.exposeInMainWorld('electronAPI', {
    // Window controls
    dragLock: (locked) => ipcRenderer.send('drag-lock', locked),
    dragMove: () => ipcRenderer.send('drag-move'),
    dragEnd: () => ipcRenderer.send('drag-end'),
    startDragReaction: () => ipcRenderer.send('start-drag-reaction'),
    endDragReaction: () => ipcRenderer.send('end-drag-reaction'),
    openChatDialog: () => ipcRenderer.send('open-chat-dialog'),
    closeDialog: () => ipcRenderer.send('close-dialog'),
    minimizeDialog: () => ipcRenderer.send('minimize-dialog'),
    setDialogChatBusy: (active) => ipcRenderer.send('dialog-chat-busy', active),
    notifyDialogInputFocus: () => ipcRenderer.send('dialog-input-focus'),
    notifyDialogInputBlur: () => ipcRenderer.send('dialog-input-blur'),
    onStateChange: (callback) => ipcRenderer.on('state-change', (_event, state, svgPath) => callback(state, svgPath)),
    onPlayVoiceAsset: (callback) => {
        const listener = (_event, payload) => callback(payload);
        ipcRenderer.on('play-voice-asset', listener);
        return () => ipcRenderer.removeListener('play-voice-asset', listener);
    },
    playVoiceKey: (voiceKey) => ipcRenderer.send('play-voice-key', voiceKey),
    playRandomAction: (actionKey, assetUrl) => {
        console.log('[preload] playRandomAction called:', actionKey, assetUrl);
        ipcRenderer.send('play-random-action', actionKey, assetUrl);
    },
    getRandomAction: () => {
        console.log('[preload] getRandomAction called');
        return ipcRenderer.invoke('get-random-action');
    },
    onPlayRandomAction: (callback) => {
        console.log('[preload] onPlayRandomAction registered');
        const listener = (_event, actionKey, assetUrl) => {
            console.log('[preload] onPlayRandomAction received:', actionKey, assetUrl);
            callback(actionKey, assetUrl);
        };
        ipcRenderer.on('play-random-action', listener);
        return () => ipcRenderer.removeListener('play-random-action', listener);
    },
    openChatDialog: () => ipcRenderer.send('open-chat-dialog'),

    // Chat streaming - parsed in preload so the renderer never receives a raw Response object
    sendChatStream: async (message, threadId, messages) => {
        const response = await fetch(`${API_BASE_URL}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                thread_id: threadId || null,
                messages: messages || []
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return parseStreamResponse(response);
    },

    // Non-streaming chat
    sendChat: async (message, threadId, messages) => {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                thread_id: threadId || null,
                messages: messages || []
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return response.json();
    },

    // List available models
    listModels: async () => {
        const response = await fetch(`${API_BASE_URL}/models`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    },

    fetchConversations: async () => {
        const response = await fetch(`${API_BASE_URL}/conversations`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    },

    fetchConversation: async (threadId) => {
        const response = await fetch(`${API_BASE_URL}/conversations/${encodeURIComponent(threadId)}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    },

    createConversation: async () => {
        const response = await fetch(`${API_BASE_URL}/conversations/create`, {
            method: 'POST',
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    },

    // Health check
    healthCheck: async () => {
        const response = await fetch(`${API_BASE_URL}/health`);
        return response.ok;
    },
});
