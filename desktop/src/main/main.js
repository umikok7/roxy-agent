const { app, BrowserWindow, ipcMain, Notification, screen } = require('electron');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { pathToFileURL } = require('url');
const log = require('electron-log');
const { applyStationaryCollectionBehavior } = require('./mac-window');

log.transports.file.level = 'info';
log.transports.console.level = 'debug';

const isMac = process.platform === 'darwin';
const SERVER_PORT = 23333;
const PET_SIZE = 340;
const HIT_PADDING = 10;
const SESSION_TTL_MS = 10 * 60 * 1000;
const TASK_SEQUENCE_MS = 3200;
const DRAG_SLEEP_MS = 5 * 60 * 1000;
const PET_EDGE_MARGIN = 0;

const PET_LAYOUT = {
    visibleArea: {
        left: 0.18,
        top: 0.02,
        width: 0.64,
        height: 0.96,
    },
    hitArea: {
        left: 0.27,
        top: 0.08,
        width: 0.46,
        height: 0.84,
    },
};

const STATE_TO_SVG = {
    thinking: 'roxy-thinking.svg',
    lookAround: 'roxy-idle.svg',
};

const VRMA_ACTION_URLS = [
    'Relax',
    'Angry',
    'Blush',
    'Clapping',
    'Sleepy',
    'Sad',
    'Jump',
    'Surprised',
    'Goodbye',
].map(name => {
    const relativePath = path.join('..', '..', 'assets', 'roxy_3D', 'vrma', `${name}.vrma`);
    return {
        key: name.toLowerCase(),
        relativePath,
        absolutePath: path.join(__dirname, relativePath),
        label: name,
    };
});

let lastRandomActionKey = null;

function getRandomVrmaAction() {
    const available = VRMA_ACTION_URLS.filter(a => a.key !== lastRandomActionKey);
    if (available.length === 0) return VRMA_ACTION_URLS[0];
    const selected = available[Math.floor(Math.random() * available.length)];
    lastRandomActionKey = selected.key;
    return {
        key: selected.key,
        label: selected.label,
        url: pathToFileURL(selected.absolutePath).href,
    };
}

const CLAUDE_HOOK_EVENTS = [
    'SessionStart',
    'SessionEnd',
    'UserPromptSubmit',
    'PreToolUse',
    'PostToolUse',
    'PostToolUseFailure',
    'Stop',
    'SubagentStart',
    'SubagentStop',
];

const RENDERER_DIST_DIR = path.join(__dirname, '..', 'renderer-dist');

const PET_CONFIG = {
    width: PET_SIZE + HIT_PADDING * 2,
    height: PET_SIZE + HIT_PADDING * 2,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
        preload: path.join(__dirname, '..', 'preload', 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
    },
};

const DIALOG_CONFIG = {
    width: 326,
    height: 352,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    maximizable: false,
    minimizable: false,
    hasShadow: false,
    skipTaskbar: true,
    backgroundColor: '#00000000',
    webPreferences: {
        preload: path.join(__dirname, '..', 'preload', 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
    },
};

const CODEX_AGENT_CONFIG = {
    logEventMap: {
        'session_meta': 'lookAround',
        'event_msg:task_started': 'thinking',
        'event_msg:user_message': 'thinking',
        'event_msg:agent_message': null,
        'event_msg:exec_command_end': 'thinking',
        'event_msg:patch_apply_end': 'thinking',
        'event_msg:custom_tool_call_output': 'thinking',
        'response_item:function_call': 'thinking',
        'response_item:custom_tool_call': 'thinking',
        'response_item:web_search_call': 'thinking',
        'event_msg:task_complete': 'task-success',
        'event_msg:context_compacted': 'lookAround',
        'event_msg:turn_aborted': 'task-failure',
    },
    logConfig: {
        sessionDir: '~/.codex/sessions',
        pollIntervalMs: 1500,
    },
};

const VOICE_CLIP_FILES = {
    intro_first_open: 'intro_first_open.wav',
    dialog_open_a: 'dialog_open_a.wav',
    single_click_bother_a: 'single_click_bother_a.wav',
    single_click_lazy_a: 'single_click_lazy_a.wav',
    single_click_focus_a: 'single_click_focus_a.wav',
    single_click_hydrate_a: 'single_click_hydrate_a.wav',
    single_click_help_a: 'single_click_help_a.wav',
    single_click_command_a: 'single_click_command_a.wav',
    single_click_spell_joke_a: 'single_click_spell_joke_a.wav',
    single_click_no_chant_a: 'single_click_no_chant_a.wav',
    success_light_a: 'success_light_a.wav',
    success_light_b: 'success_light_b.wav',
    success_normal_a: 'success_normal_a.wav',
    success_normal_b: 'success_normal_b.wav',
    success_heavy_a: 'success_heavy_a.wav',
    success_heavy_b: 'success_heavy_b.wav',
    partial_issue_a: 'partial_issue_a.wav',
    hard_failure_a: 'hard_failure_a.wav',
    reminder_due_a: 'reminder_due_a.wav',
    reminder_start_simple_a: 'reminder_start_simple_a.wav',
};

const EXTERNAL_COMPLETION_EVENTS = {
    success: new Set(['Stop', 'event_msg:task_complete']),
    failure: new Set(['Stop', 'turn_aborted', 'event_msg:turn_aborted']),
};

const SINGLE_CLICK_VOICE_KEYS = [
    'single_click_bother_a',
    'single_click_lazy_a',
    'single_click_focus_a',
    'single_click_hydrate_a',
    'single_click_help_a',
    'single_click_command_a',
    'single_click_spell_joke_a',
    'single_click_no_chant_a',
];

let petWindow = null;
let hitWindow = null;
let dialogWindow = null;
let stateServer = null;
let stateCleanupTimer = null;
let codexMonitor = null;
let dragLocked = false;
let dragSnapshot = null;
let dragReactionActive = false;
let chatModeActive = false;
let currentPetState = 'lookAround';
let sleepModeActive = false;
let lastDragAt = Date.now();
let transientStateTimer = null;
let sleepCheckTimer = null;
let dialogChatBusy = false;
let hasPlayedIntroVoice = false;
const externalSessions = new Map();
const voiceRotationState = new Map();
const externalCompletionCooldown = new Map();
const pendingReminderCards = [];

function getSvgAssetPath(fileName) {
    return path.join(__dirname, '..', '..', 'assets', 'roxy', fileName);
}

function getVoiceAssetPath(voiceKey) {
    const fileName = VOICE_CLIP_FILES[voiceKey];
    if (!fileName) {
        return null;
    }
    return path.join(__dirname, '..', '..', 'assets', 'voice', 'ja', fileName);
}

function resolveRendererEntry(distFileName) {
    const distPath = path.join(RENDERER_DIST_DIR, distFileName);
    if (fs.existsSync(distPath)) {
        return distPath;
    }

    throw new Error(`Renderer bundle not found: ${distFileName}. Run "npm run build:renderer" in the desktop package first.`);
}

function getCurrentSvgPath() {
    return getSvgAssetPath(STATE_TO_SVG[currentPetState] || STATE_TO_SVG.lookAround);
}

function sendToRenderer(channel, ...args) {
    if (petWindow && !petWindow.isDestroyed()) {
        petWindow.webContents.send(channel, ...args);
    }
}

function selectRotatingVoiceKey(voiceKeys) {
    if (!Array.isArray(voiceKeys) || voiceKeys.length === 0) {
        return null;
    }
    if (voiceKeys.length === 1) {
        return voiceKeys[0];
    }
    const groupKey = voiceKeys.join('|');
    const currentIndex = voiceRotationState.get(groupKey) || 0;
    const selected = voiceKeys[currentIndex % voiceKeys.length];
    voiceRotationState.set(groupKey, (currentIndex + 1) % voiceKeys.length);
    return selected;
}

function selectRandomVoiceKey(voiceKeys) {
    if (!Array.isArray(voiceKeys) || voiceKeys.length === 0) {
        return null;
    }
    if (voiceKeys.length === 1) {
        return voiceKeys[0];
    }

    const groupKey = `random:${voiceKeys.join('|')}`;
    const previous = voiceRotationState.get(groupKey) || null;
    const available = voiceKeys.filter((voiceKey) => voiceKey !== previous);
    const pool = available.length > 0 ? available : voiceKeys;
    const selected = pool[Math.floor(Math.random() * pool.length)];
    voiceRotationState.set(groupKey, selected);
    return selected;
}

function emitVoiceKey(voiceKey) {
    if (!petWindow || petWindow.isDestroyed() || typeof voiceKey !== 'string' || !voiceKey.trim()) {
        return false;
    }
    const normalizedVoiceKey = voiceKey.trim();
    const voicePath = getVoiceAssetPath(normalizedVoiceKey);
    if (!voicePath || !fs.existsSync(voicePath)) {
        log.warn(`Voice asset not found for key: ${normalizedVoiceKey}`);
        return false;
    }

    const payload = {
        voiceKey: normalizedVoiceKey,
        assetUrl: pathToFileURL(voicePath).href,
    };
    log.info(`Forwarding voice asset to pet window: ${normalizedVoiceKey}`);
    petWindow.webContents.send('play-voice-asset', payload);
    return true;
}

function playRandomPetAction() {
    const action = getRandomVrmaAction();
    if (!action || !petWindow || petWindow.isDestroyed()) {
        return false;
    }
    try {
        petWindow.webContents.send('play-random-action', action.key, action.url);
        return true;
    } catch (error) {
        log.error(`[pet-interaction] failed to send random action: ${error.message}`);
        return false;
    }
}

function handlePetInteraction(interactionType) {
    if (interactionType === 'single') {
        const voiceKey = selectRandomVoiceKey(SINGLE_CLICK_VOICE_KEYS);
        if (voiceKey) {
            emitVoiceKey(voiceKey);
        }
        playRandomPetAction();
        return;
    }

    if (interactionType === 'double') {
        createDialogWindow();
        if (hasPlayedIntroVoice) {
            emitVoiceKey(selectRandomVoiceKey(['dialog_open_a', 'reminder_start_simple_a']));
            return;
        }
        hasPlayedIntroVoice = true;
        emitVoiceKey('intro_first_open');
    }
}

function playVoiceForTaskCompletion(status) {
    if (status === 'failure') {
        emitVoiceKey('hard_failure_a');
        return;
    }
    const voiceKey = selectRotatingVoiceKey(['success_light_a', 'success_light_b']);
    if (voiceKey) {
        emitVoiceKey(voiceKey);
    }
}

function maybeAnnounceExternalCompletion({ sessionId, event, outcome }) {
    if (!sessionId || !outcome) return;
    const normalizedOutcome = outcome === 'failure' ? 'failure' : 'success';
    const allowedEvents = EXTERNAL_COMPLETION_EVENTS[normalizedOutcome];
    if (allowedEvents && event && !allowedEvents.has(event)) {
        return;
    }

    const cooldownKey = `${sessionId}:${normalizedOutcome}`;
    const now = Date.now();
    const lastAt = externalCompletionCooldown.get(cooldownKey) || 0;
    if (now - lastAt < 1500) {
        return;
    }
    externalCompletionCooldown.set(cooldownKey, now);
    playVoiceForTaskCompletion(normalizedOutcome);
}

function reapplyMacVisibility(targetWindow, options = {}) {
    if (!targetWindow || targetWindow.isDestroyed()) return;
    const mode = options.mode || 'pet';
    const level = mode === 'dialog' ? 'floating' : 'screen-saver';
    targetWindow.setAlwaysOnTop(mode !== 'dialog', level);
    if (isMac) {
        targetWindow.setVisibleOnAllWorkspaces(true, {
            visibleOnFullScreen: true,
            skipTransformProcessType: true,
        });
        if (mode !== 'dialog') {
            applyStationaryCollectionBehavior(targetWindow);
        }
    }
}

function reapplyAllWindowVisibility() {
    reapplyMacVisibility(petWindow, { mode: chatModeActive ? 'dialog' : 'pet' });
    reapplyMacVisibility(hitWindow, { mode: chatModeActive ? 'dialog' : 'pet' });
    reapplyMacVisibility(dialogWindow, { mode: 'dialog' });
}

function disableMacSpaceVisibility(targetWindow) {
    if (!targetWindow || targetWindow.isDestroyed() || !isMac) return;
    try {
        targetWindow.setVisibleOnAllWorkspaces(false);
    } catch {}
}

function enterChatMode() {
    if (chatModeActive) return;
    chatModeActive = true;

    if (petWindow && !petWindow.isDestroyed()) {
        petWindow.setAlwaysOnTop(false);
        reapplyMacVisibility(petWindow, { mode: 'dialog' });
    }

    if (hitWindow && !hitWindow.isDestroyed()) {
        hitWindow.setAlwaysOnTop(false);
        reapplyMacVisibility(hitWindow, { mode: 'dialog' });
        hitWindow.showInactive();
    }
}

function exitChatMode() {
    if (!chatModeActive) return;
    chatModeActive = false;

    if (petWindow && !petWindow.isDestroyed()) {
        petWindow.showInactive();
    }

    if (hitWindow && !hitWindow.isDestroyed()) {
        hitWindow.showInactive();
    }

    reapplyAllWindowVisibility();
    syncLinkedWindows();
}

function resolvePetRect(area) {
    return {
        x: Math.round(PET_CONFIG.width * area.left),
        y: Math.round(PET_CONFIG.height * area.top),
        width: Math.round(PET_CONFIG.width * area.width),
        height: Math.round(PET_CONFIG.height * area.height),
    };
}

function getPetVisibleRect() {
    return resolvePetRect(PET_LAYOUT.visibleArea);
}

function getPetHitRect() {
    return resolvePetRect(PET_LAYOUT.hitArea);
}

function getPetVisibleBounds(petBounds) {
    const rect = getPetVisibleRect();
    return {
        x: petBounds.x + rect.x,
        y: petBounds.y + rect.y,
        width: rect.width,
        height: rect.height,
    };
}

function getHitWindowBounds(petBounds) {
    const rect = getPetHitRect();
    return {
        x: petBounds.x + rect.x,
        y: petBounds.y + rect.y,
        width: rect.width,
        height: rect.height,
    };
}

function clampToDisplay(bounds, display) {
    const area = display.workArea;
    return {
        x: Math.max(area.x + PET_EDGE_MARGIN, Math.min(bounds.x, area.x + area.width - bounds.width - PET_EDGE_MARGIN)),
        y: Math.max(area.y + PET_EDGE_MARGIN, Math.min(bounds.y, area.y + area.height - bounds.height - PET_EDGE_MARGIN)),
    };
}

function clampPetWindowToDisplay(bounds, display) {
    const area = display.workArea;
    const visible = getPetVisibleRect();
    const minX = area.x + PET_EDGE_MARGIN - visible.x;
    const maxX = area.x + area.width - PET_EDGE_MARGIN - visible.x - visible.width;
    const minY = area.y + PET_EDGE_MARGIN - visible.y;
    const maxY = area.y + area.height - PET_EDGE_MARGIN - visible.y - visible.height;

    return {
        x: Math.max(Math.min(minX, maxX), Math.min(bounds.x, Math.max(minX, maxX))),
        y: Math.max(Math.min(minY, maxY), Math.min(bounds.y, Math.max(minY, maxY))),
    };
}

function getDialogAnchorBounds() {
    const display = petWindow && !petWindow.isDestroyed()
        ? screen.getDisplayMatching(petWindow.getBounds())
        : screen.getPrimaryDisplay();

    if (!petWindow || petWindow.isDestroyed()) {
        return {
            x: display.workArea.x + display.workArea.width - DIALOG_CONFIG.width - 24,
            y: display.workArea.y + display.workArea.height - DIALOG_CONFIG.height - 80,
        };
    }

    const petBounds = petWindow.getBounds();
    const visibleBounds = getPetVisibleBounds(petBounds);
    const preferred = {
        x: visibleBounds.x + visibleBounds.width - 36,
        y: visibleBounds.y - 18,
        width: DIALOG_CONFIG.width,
        height: DIALOG_CONFIG.height,
    };

    return clampToDisplay(preferred, display);
}

function syncLinkedWindows() {
    if (!petWindow || petWindow.isDestroyed() || !hitWindow || hitWindow.isDestroyed()) return;
    const petBounds = petWindow.getBounds();
    hitWindow.setBounds(getHitWindowBounds(petBounds));
}

function syncDialogWindowPosition() {
    if (!dialogWindow || dialogWindow.isDestroyed()) return;
    const { x, y } = getDialogAnchorBounds();
    dialogWindow.setPosition(x, y);
}

function resolveVisualState() {
    if (dialogChatBusy) {
        return 'thinking';
    }
    for (const session of externalSessions.values()) {
        if (session.state === 'thinking') {
            return 'thinking';
        }
    }
    return 'lookAround';
}

function clearTransientStateTimer() {
    if (transientStateTimer) {
        clearTimeout(transientStateTimer);
        transientStateTimer = null;
    }
}

function clearSleepMode() {
    sleepModeActive = false;
}

function touchDragActivity() {
    lastDragAt = Date.now();
    if (sleepModeActive) {
        clearSleepMode();
        currentPetState = 'lookAround';
    }
}

function setTransientState(nextState, delayMs = TASK_SEQUENCE_MS) {
    clearTransientStateTimer();
    clearSleepMode();
    currentPetState = nextState;
    broadcastPetState(true);
    transientStateTimer = setTimeout(() => {
        transientStateTimer = null;
        currentPetState = 'lookAround';
        broadcastPetState(true);
    }, delayMs);
}

function maybeEnterSleepMode() {
    if (dragReactionActive || dragLocked || dialogChatBusy) return;

    let hasBusy = false;
    for (const session of externalSessions.values()) {
        if (session.state === 'thinking') {
            hasBusy = true;
            break;
        }
    }
    if (hasBusy) return;

    if (Date.now() - lastDragAt >= DRAG_SLEEP_MS) {
        sleepModeActive = true;
        currentPetState = 'sleeping';
        broadcastPetState(true);
    }
}

function broadcastPetState(force = false) {
    const nextState = resolveVisualState();
    if (!force && nextState === currentPetState) return;
    currentPetState = nextState;
    sendToRenderer('state-change', currentPetState, getCurrentSvgPath());
}

function normalizeExternalState(rawState) {
    if (rawState === 'working' || rawState === 'thinking' || rawState === 'working-typing') {
        return 'thinking';
    }
    if (rawState === 'lookAround') {
        return 'lookAround';
    }
    return null;
}

function clearExternalSessionTimer(session) {
    if (!session || !session.clearTimer) return;
    clearTimeout(session.clearTimer);
    session.clearTimer = null;
}

function upsertExternalSession(sessionId, state, meta = {}) {
    if (!sessionId) return;
    if (!state) {
        const existing = externalSessions.get(sessionId);
        if (existing) {
            clearExternalSessionTimer(existing);
        }
        externalSessions.delete(sessionId);
        broadcastPetState();
        return;
    }

    const existing = externalSessions.get(sessionId);
    if (existing) {
        clearExternalSessionTimer(existing);
    }
    externalSessions.set(sessionId, {
        ...(existing || {}),
        state,
        agentId: meta.agentId || existing?.agentId || 'unknown',
        updatedAt: Date.now(),
        event: meta.event || '',
        clearTimer: null,
    });
    broadcastPetState();
}

function cleanupExternalSessions() {
    const now = Date.now();
    let changed = false;
    for (const [sessionId, session] of externalSessions.entries()) {
        if (now - session.updatedAt > SESSION_TTL_MS) {
            clearExternalSessionTimer(session);
            externalSessions.delete(sessionId);
            changed = true;
        }
    }
    if (changed) {
        broadcastPetState();
    }
}

function handleIncomingStateEvent(body) {
    if (!body || typeof body !== 'object') return;
    const sessionId = String(body.session_id || 'default');
    const event = typeof body.event === 'string' ? body.event : '';
    const agentId = typeof body.agent_id === 'string' ? body.agent_id : 'external';

    if (body.state === 'SessionEnd' || body.state === 'Stop') {
        upsertExternalSession(sessionId, null, { event, agentId });
        return;
    }

    if (body.state === 'thinking') {
        upsertExternalSession(sessionId, 'thinking', { event, agentId });
        return;
    }

    if (body.state === 'task-success') {
        maybeAnnounceExternalCompletion({ sessionId, event, outcome: 'success' });
        upsertExternalSession(sessionId, null, { event, agentId });
        return;
    }

    if (body.state === 'task-failure') {
        maybeAnnounceExternalCompletion({ sessionId, event, outcome: 'failure' });
        upsertExternalSession(sessionId, null, { event, agentId });
        return;
    }

    if (body.state === 'lookAround') {
        upsertExternalSession(sessionId, null, { event, agentId });
        return;
    }

    const mappedState = normalizeExternalState(body.state);
    if (mappedState === 'thinking') {
        upsertExternalSession(sessionId, mappedState, { event, agentId });
    }
}

function startStateServer() {
    if (stateServer) return;

    stateServer = http.createServer((req, res) => {
        if (req.method === 'POST' && req.url === '/play-tts') {
            const chunks = [];
            req.on('data', (chunk) => chunks.push(chunk));
            req.on('end', () => {
                try {
                    const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));
                    if (!payload || typeof payload !== 'object') {
                        throw new Error('Invalid TTS payload');
                    }
                    if (petWindow && !petWindow.isDestroyed()) {
                        log.info('Received /play-tts request, forwarding to pet window');
                        if (typeof payload.voiceKey === 'string' && payload.voiceKey.trim()) {
                            const voicePath = getVoiceAssetPath(payload.voiceKey.trim());
                            if (!voicePath || !fs.existsSync(voicePath)) {
                                throw new Error(`Unknown voice key: ${payload.voiceKey}`);
                            }
                            petWindow.webContents.send('play-voice-asset', {
                                voiceKey: payload.voiceKey.trim(),
                                assetUrl: pathToFileURL(voicePath).href,
                            });
                        } else if (typeof payload.assetUrl === 'string' && payload.assetUrl.trim()) {
                            petWindow.webContents.send('play-voice-asset', payload);
                        } else {
                            throw new Error('Invalid voice payload');
                        }
                    }
                    res.writeHead(204);
                    res.end();
                } catch (error) {
                    log.warn('Failed to process /play-tts payload:', error.message);
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: false }));
                }
            });
            return;
        }

        if (req.method === 'POST' && req.url === '/state') {
            const chunks = [];
            req.on('data', (chunk) => chunks.push(chunk));
            req.on('end', () => {
                try {
                    const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));
                    handleIncomingStateEvent(payload);
                    res.writeHead(204);
                    res.end();
                } catch (error) {
                    log.warn('Failed to parse /state payload:', error.message);
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: false }));
                }
            });
            return;
        }

        if (req.method === 'POST' && req.url === '/reminder') {
            const chunks = [];
            req.on('data', (chunk) => chunks.push(chunk));
            req.on('end', () => {
                try {
                    const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));
                    handleReminderDue(payload);
                    res.writeHead(204);
                    res.end();
                } catch (error) {
                    log.warn('Failed to process /reminder payload:', error.message);
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ ok: false }));
                }
            });
            return;
        }

        if (req.method === 'GET' && req.url === '/state') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: true, state: currentPetState }));
            return;
        }

        res.writeHead(404);
        res.end();
    });

    stateServer.listen(SERVER_PORT, '127.0.0.1', () => {
        log.info(`State server listening on 127.0.0.1:${SERVER_PORT}`);
    });
}

function stopStateServer() {
    if (!stateServer) return;
    stateServer.close();
    stateServer = null;
}

function getHookScriptPath() {
    const basePath = app.getAppPath();
    const resolved = path.join(basePath, 'src', 'hooks', 'claude-hook.js');
    return resolved.replace('app.asar', 'app.asar.unpacked');
}

function installClaudeHooks() {
    const settingsPath = path.join(os.homedir(), '.claude', 'settings.json');
    const settingsDir = path.dirname(settingsPath);

    if (!fs.existsSync(settingsDir)) {
        log.info('Claude settings directory not found, skipping hook install');
        return;
    }

    let settings = {};
    try {
        settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    } catch (error) {
        if (error.code !== 'ENOENT') {
            log.warn(`Failed to read Claude settings: ${error.message}`);
        }
    }

    if (!settings.hooks || typeof settings.hooks !== 'object') {
        settings.hooks = {};
    }

    const marker = 'claude-hook.js';
    const hookScript = getHookScriptPath();
    const desiredCommand = `node "${hookScript}"`;
    let changed = false;

    for (const eventName of CLAUDE_HOOK_EVENTS) {
        const existingEntries = Array.isArray(settings.hooks[eventName]) ? settings.hooks[eventName] : [];
        settings.hooks[eventName] = existingEntries;

        let matched = false;
        for (const entry of existingEntries) {
            if (!entry || typeof entry !== 'object' || !Array.isArray(entry.hooks)) continue;
            for (const hook of entry.hooks) {
                if (!hook || typeof hook.command !== 'string' || !hook.command.includes(marker)) continue;
                matched = true;
                const nextCommand = `${desiredCommand} "${eventName}"`;
                if (hook.command !== nextCommand) {
                    hook.command = nextCommand;
                    changed = true;
                }
            }
        }

        if (!matched) {
            settings.hooks[eventName].push({
                matcher: '',
                hooks: [
                    {
                        type: 'command',
                        command: `${desiredCommand} "${eventName}"`,
                    },
                ],
            });
            changed = true;
        }
    }

    if (!changed) return;

    fs.mkdirSync(settingsDir, { recursive: true });
    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2), 'utf8');
    log.info('Claude hooks installed for Deer Pet');
}

function startCodexMonitor() {
    try {
        const CodexLogMonitor = require('./codex-log-monitor');
        codexMonitor = new CodexLogMonitor(CODEX_AGENT_CONFIG, (sessionId, state, event) => {
            if (state === 'task-success') {
                maybeAnnounceExternalCompletion({ sessionId, event, outcome: 'success' });
                upsertExternalSession(sessionId, null, { event, agentId: 'codex' });
                return;
            }
            if (state === 'task-failure') {
                maybeAnnounceExternalCompletion({ sessionId, event, outcome: 'failure' });
                upsertExternalSession(sessionId, null, { event, agentId: 'codex' });
                return;
            }
            const mappedState = normalizeExternalState(state);
            if (mappedState === 'thinking') {
                upsertExternalSession(sessionId, 'thinking', { event, agentId: 'codex' });
                return;
            }
            upsertExternalSession(sessionId, null, { event, agentId: 'codex' });
        });
        codexMonitor.start();
        log.info('Codex log monitor started');
    } catch (error) {
        log.warn(`Codex log monitor unavailable: ${error.message}`);
    }
}

function createPetWindow() {
    const display = screen.getPrimaryDisplay();
    const visibleRect = getPetVisibleRect();
    const initialBounds = clampPetWindowToDisplay({
        x: display.workArea.x + display.workArea.width - visibleRect.x - visibleRect.width - 24,
        y: display.workArea.y + display.workArea.height - visibleRect.y - visibleRect.height - 24,
        width: PET_CONFIG.width,
        height: PET_CONFIG.height,
    }, display);

    petWindow = new BrowserWindow({
        ...PET_CONFIG,
        x: initialBounds.x,
        y: initialBounds.y,
    });

    petWindow.loadFile(resolveRendererEntry('pet.html'));
    petWindow.setIgnoreMouseEvents(true);
    petWindow.once('ready-to-show', () => {
        reapplyMacVisibility(petWindow);
        broadcastPetState(true);
    });
    petWindow.webContents.on('did-finish-load', () => {
        broadcastPetState(true);
    });
    petWindow.on('move', () => {
        if (!dragLocked) {
            syncLinkedWindows();
            syncDialogWindowPosition();
        }
    });
    petWindow.on('resize', () => {
        syncLinkedWindows();
        syncDialogWindowPosition();
    });
    petWindow.on('closed', () => {
        petWindow = null;
        if (hitWindow) hitWindow.close();
        if (dialogWindow) dialogWindow.close();
    });
}

function createHitWindow() {
    if (!petWindow) return;
    const petBounds = petWindow.getBounds();
    const hitBounds = getHitWindowBounds(petBounds);
    const hitRect = getPetHitRect();

    hitWindow = new BrowserWindow({
        width: hitBounds.width,
        height: hitBounds.height,
        x: hitBounds.x,
        y: hitBounds.y,
        transparent: true,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        hasShadow: false,
        focusable: !isMac,
        backgroundColor: '#00000000',
        webPreferences: {
            preload: path.join(__dirname, '..', 'preload', 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    hitWindow.loadFile(path.join(__dirname, '..', 'renderer', 'pet', 'hit.html'), {
        query: {
            width: String(hitRect.width),
            height: String(hitRect.height),
        },
    });
    hitWindow.setIgnoreMouseEvents(false);
    if (isMac) {
        hitWindow.setFocusable(false);
    }
    hitWindow.once('ready-to-show', () => {
        reapplyMacVisibility(hitWindow);
    });
    hitWindow.on('closed', () => {
        hitWindow = null;
    });
}

function createDialogWindow() {
    if (dialogWindow && !dialogWindow.isDestroyed()) {
        enterChatMode();
        dialogWindow.show();
        dialogWindow.focus();
        syncDialogWindowPosition();
        flushPendingReminderCards();
        return;
    }

    const { x, y } = getDialogAnchorBounds();
    dialogWindow = new BrowserWindow({
        ...DIALOG_CONFIG,
        x,
        y,
    });

    dialogWindow.loadFile(resolveRendererEntry('dialog.html'));
    dialogWindow.webContents.on('did-finish-load', () => {
        flushPendingReminderCards();
    });
    dialogWindow.once('ready-to-show', () => {
        enterChatMode();
        dialogWindow.showInactive();
        reapplyMacVisibility(dialogWindow, { mode: 'dialog' });
        dialogWindow.focus();
        flushPendingReminderCards();
    });
    dialogWindow.on('blur', () => {
        syncDialogWindowPosition();
    });
    dialogWindow.on('closed', () => {
        dialogWindow = null;
        exitChatMode();
    });
}

function flushPendingReminderCards() {
    if (!dialogWindow || dialogWindow.isDestroyed() || dialogWindow.webContents.isLoading()) {
        return;
    }
    while (pendingReminderCards.length > 0) {
        dialogWindow.webContents.send('open-reminder-card', pendingReminderCards.shift());
    }
}

function showSystemReminderNotification(payload) {
    if (!Notification.isSupported()) {
        return;
    }
    const title = typeof payload.title === 'string' && payload.title.trim() ? payload.title.trim() : 'Roxy Reminder';
    const body = typeof payload.message === 'string' && payload.message.trim() ? payload.message.trim() : 'Reminder is due.';
    try {
        new Notification({ title, body }).show();
    } catch (error) {
        log.warn(`Failed to show reminder notification: ${error.message}`);
    }
}

function handleReminderDue(payload) {
    if (!payload || typeof payload !== 'object') {
        return;
    }
    const reminderId = typeof payload.id === 'string' && payload.id.trim() ? payload.id.trim() : '';
    if (!reminderId) {
        return;
    }
    const reminderPayload = {
        reminderId,
        threadId: typeof payload.thread_id === 'string' ? payload.thread_id : null,
    };
    pendingReminderCards.push(reminderPayload);
    createDialogWindow();
    emitVoiceKey('reminder_due_a');
    playRandomPetAction();
    showSystemReminderNotification(payload);
    flushPendingReminderCards();
}

ipcMain.on('drag-lock', (_event, locked) => {
    dragLocked = !!locked;
    touchDragActivity();
    if (!dragLocked || !petWindow || petWindow.isDestroyed()) {
        dragSnapshot = null;
        syncLinkedWindows();
        return;
    }

    const petBounds = petWindow.getBounds();
    const cursor = screen.getCursorScreenPoint();
    dragSnapshot = {
        offsetX: cursor.x - petBounds.x,
        offsetY: cursor.y - petBounds.y,
    };
});

ipcMain.on('drag-move', () => {
    if (!dragLocked || !dragSnapshot || !petWindow || petWindow.isDestroyed()) return;
    touchDragActivity();

    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const nextBounds = {
        x: cursor.x - dragSnapshot.offsetX,
        y: cursor.y - dragSnapshot.offsetY,
        width: PET_CONFIG.width,
        height: PET_CONFIG.height,
    };
    const clamped = clampPetWindowToDisplay(nextBounds, display);
    petWindow.setPosition(clamped.x, clamped.y);
    syncLinkedWindows();
    syncDialogWindowPosition();
});

ipcMain.on('drag-end', () => {
    dragLocked = false;
    dragSnapshot = null;
    touchDragActivity();
    syncLinkedWindows();
    syncDialogWindowPosition();
});

ipcMain.on('start-drag-reaction', () => {
    dragReactionActive = true;
    touchDragActivity();
    broadcastPetState();
});

ipcMain.on('end-drag-reaction', () => {
    dragReactionActive = false;
    touchDragActivity();
    broadcastPetState();
});

ipcMain.on('open-chat-dialog', () => {
    createDialogWindow();
});

ipcMain.on('close-dialog', () => {
    if (dialogWindow) {
        dialogWindow.hide();
    }
    exitChatMode();
});

ipcMain.on('minimize-dialog', () => {
    if (dialogWindow) {
        dialogWindow.hide();
    }
    exitChatMode();
});

ipcMain.on('dialog-input-focus', () => {
    if (!dialogWindow || dialogWindow.isDestroyed()) return;
    dialogWindow.setAlwaysOnTop(false);
});

ipcMain.on('dialog-input-blur', () => {
    if (!dialogWindow || dialogWindow.isDestroyed()) return;
    reapplyMacVisibility(dialogWindow, { mode: 'dialog' });
});

ipcMain.on('dialog-chat-busy', (_event, active) => {
    dialogChatBusy = !!active;
    broadcastPetState();
});

ipcMain.on('play-voice-key', (_event, voiceKey) => {
    emitVoiceKey(voiceKey);
});

ipcMain.on('pet-interaction', (_event, interactionType) => {
    if (interactionType !== 'single' && interactionType !== 'double') {
        log.warn(`[pet-interaction] unsupported interaction type: ${interactionType}`);
        return;
    }
    handlePetInteraction(interactionType);
});

ipcMain.on('play-random-action', (_event, actionKey, assetUrl) => {
    log.info(`[DEBUG] play-random-action received in main: key=${actionKey}`);
    if (!petWindow || petWindow.isDestroyed()) {
        log.info('[DEBUG] petWindow is null/destroyed');
        return;
    }
    log.info(`[DEBUG] petWindow exists, sending to webContents. webContents.isLoading()=`);
    try {
        petWindow.webContents.send('play-random-action', actionKey, assetUrl);
        log.info('[DEBUG] send() called successfully');
    } catch (e) {
        log.error('[DEBUG] send() failed:', e.message);
    }
});

ipcMain.handle('get-random-action', () => {
    const action = getRandomVrmaAction();
    log.info(`[DEBUG] get-random-action returning: ${JSON.stringify(action)}`);
    return action;
});

app.whenReady().then(() => {
    createPetWindow();
    setTimeout(() => {
        createHitWindow();
        syncLinkedWindows();
        reapplyAllWindowVisibility();
    }, 100);

    startStateServer();
    installClaudeHooks();
    startCodexMonitor();
    stateCleanupTimer = setInterval(cleanupExternalSessions, 8000);
    sleepCheckTimer = setInterval(maybeEnterSleepMode, 30000);
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createPetWindow();
        setTimeout(() => {
            createHitWindow();
            syncLinkedWindows();
            reapplyAllWindowVisibility();
        }, 100);
    } else {
        reapplyAllWindowVisibility();
    }
});

app.on('before-quit', () => {
    if (stateCleanupTimer) {
        clearInterval(stateCleanupTimer);
        stateCleanupTimer = null;
    }
    if (sleepCheckTimer) {
        clearInterval(sleepCheckTimer);
        sleepCheckTimer = null;
    }
    clearTransientStateTimer();
    if (codexMonitor && typeof codexMonitor.stop === 'function') {
        codexMonitor.stop();
    }
    stopStateServer();
});

process.on('uncaughtException', (error) => {
    log.error('Uncaught Exception:', error);
});

process.on('unhandledRejection', (reason) => {
    log.error('Unhandled Rejection:', reason);
});
