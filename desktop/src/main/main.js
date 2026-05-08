const { app, BrowserWindow, ipcMain, screen } = require('electron');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const log = require('electron-log');
const { applyStationaryCollectionBehavior } = require('./mac-window');

log.transports.file.level = 'info';
log.transports.console.level = 'debug';

const isMac = process.platform === 'darwin';
const SERVER_PORT = 23333;
const PET_SIZE = 150;
const HIT_PADDING = 10;
const SESSION_TTL_MS = 10 * 60 * 1000;
const CODEX_TURN_COMPLETE_GRACE_MS = 4000;

const STATE_TO_SVG = {
    idle: 'roxy-idle.svg',
    working: 'roxy-working.svg',
    'working-typing': 'roxy-working-typing.svg',
    'react-drag': 'roxy-react-drag.svg',
};

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
        'session_meta': 'idle',
        'event_msg:task_started': 'thinking',
        'event_msg:user_message': 'thinking',
        'event_msg:agent_message': null,
        'event_msg:exec_command_end': 'working',
        'event_msg:patch_apply_end': 'working',
        'event_msg:custom_tool_call_output': 'working',
        'response_item:function_call': 'working',
        'response_item:custom_tool_call': 'working',
        'response_item:web_search_call': 'working',
        'event_msg:task_complete': 'codex-turn-end',
        'event_msg:context_compacted': 'idle',
        'event_msg:turn_aborted': 'idle',
    },
    logConfig: {
        sessionDir: '~/.codex/sessions',
        pollIntervalMs: 1500,
    },
};

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
let currentPetState = 'idle';
let dialogChatBusy = false;
const externalSessions = new Map();

function getSvgAssetPath(fileName) {
    return path.join(__dirname, '..', '..', 'assets', 'roxy', fileName);
}

function resolveRendererEntry(distFileName) {
    const distPath = path.join(RENDERER_DIST_DIR, distFileName);
    if (fs.existsSync(distPath)) {
        return distPath;
    }

    throw new Error(`Renderer bundle not found: ${distFileName}. Run "npm run build:renderer" in the desktop package first.`);
}

function getCurrentSvgPath() {
    return getSvgAssetPath(STATE_TO_SVG[currentPetState] || STATE_TO_SVG.idle);
}

function sendToRenderer(channel, ...args) {
    if (petWindow && !petWindow.isDestroyed()) {
        petWindow.webContents.send(channel, ...args);
    }
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

function clampToDisplay(bounds, display) {
    const area = display.workArea;
    return {
        x: Math.max(area.x + 10, Math.min(bounds.x, area.x + area.width - bounds.width - 10)),
        y: Math.max(area.y + 10, Math.min(bounds.y, area.y + area.height - bounds.height - 10)),
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
    const preferred = {
        x: petBounds.x + petBounds.width - 36,
        y: petBounds.y - 18,
        width: DIALOG_CONFIG.width,
        height: DIALOG_CONFIG.height,
    };

    return clampToDisplay(preferred, display);
}

function syncLinkedWindows() {
    if (!petWindow || petWindow.isDestroyed() || !hitWindow || hitWindow.isDestroyed()) return;
    const petBounds = petWindow.getBounds();
    hitWindow.setBounds({
        x: petBounds.x,
        y: petBounds.y,
        width: PET_CONFIG.width,
        height: PET_CONFIG.height,
    });
}

function syncDialogWindowPosition() {
    if (!dialogWindow || dialogWindow.isDestroyed()) return;
    const { x, y } = getDialogAnchorBounds();
    dialogWindow.setPosition(x, y);
}

function resolveVisualState() {
    if (dragReactionActive) {
        return 'react-drag';
    }

    if (dialogChatBusy) {
        return 'working-typing';
    }

    let hasBusy = false;
    for (const session of externalSessions.values()) {
        if (session.state === 'working' || session.state === 'working-typing') {
            hasBusy = true;
        }
    }

    if (hasBusy) return 'working-typing';
    return 'idle';
}

function broadcastPetState(force = false) {
    const nextState = resolveVisualState();
    if (!force && nextState === currentPetState) return;
    currentPetState = nextState;
    sendToRenderer('state-change', currentPetState, getCurrentSvgPath());
}

function normalizeExternalState(rawState) {
    if (rawState === 'working' || rawState === 'thinking' || rawState === 'working-typing') {
        return 'working-typing';
    }
    return null;
}

function clearExternalSessionTimer(session) {
    if (!session || !session.clearTimer) return;
    clearTimeout(session.clearTimer);
    session.clearTimer = null;
}

function scheduleExternalSessionClear(sessionId, delayMs = CODEX_TURN_COMPLETE_GRACE_MS) {
    if (!sessionId) return;
    const session = externalSessions.get(sessionId);
    if (!session) return;
    clearExternalSessionTimer(session);
    session.clearTimer = setTimeout(() => {
        const latest = externalSessions.get(sessionId);
        if (!latest) return;
        clearExternalSessionTimer(latest);
        externalSessions.delete(sessionId);
        broadcastPetState();
    }, delayMs);
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

    if (event === 'SessionEnd' || event === 'Stop') {
        upsertExternalSession(sessionId, null, { event, agentId });
        return;
    }

    const mappedState = normalizeExternalState(body.state);
    if (!mappedState) {
        if (body.state === 'idle' || body.state === 'sleeping' || body.state === 'attention') {
            upsertExternalSession(sessionId, null, { event, agentId });
        }
        return;
    }

    upsertExternalSession(sessionId, mappedState, { event, agentId });
}

function startStateServer() {
    if (stateServer) return;

    stateServer = http.createServer((req, res) => {
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
            const mappedState = normalizeExternalState(state);
            if (mappedState) {
                upsertExternalSession(sessionId, mappedState, { event, agentId: 'codex' });
                return;
            }
            if (state === 'idle' || state === 'attention') {
                if (event === 'event_msg:task_complete') {
                    scheduleExternalSessionClear(sessionId, CODEX_TURN_COMPLETE_GRACE_MS);
                    return;
                }
                upsertExternalSession(sessionId, null, { event, agentId: 'codex' });
            }
        });
        codexMonitor.start();
        log.info('Codex log monitor started');
    } catch (error) {
        log.warn(`Codex log monitor unavailable: ${error.message}`);
    }
}

function createPetWindow() {
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    const initialX = width - PET_CONFIG.width - 40;
    const initialY = height - PET_CONFIG.height - 40;

    petWindow = new BrowserWindow({
        ...PET_CONFIG,
        x: initialX,
        y: initialY,
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

    hitWindow = new BrowserWindow({
        width: PET_CONFIG.width,
        height: PET_CONFIG.height,
        x: petBounds.x,
        y: petBounds.y,
        transparent: true,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        hasShadow: false,
        focusable: !isMac,
        webPreferences: {
            preload: path.join(__dirname, '..', 'preload', 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    hitWindow.loadFile(path.join(__dirname, '..', 'renderer', 'pet', 'hit.html'));
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
        return;
    }

    const { x, y } = getDialogAnchorBounds();
    dialogWindow = new BrowserWindow({
        ...DIALOG_CONFIG,
        x,
        y,
    });

    dialogWindow.loadFile(resolveRendererEntry('dialog.html'));
    dialogWindow.once('ready-to-show', () => {
        enterChatMode();
        dialogWindow.showInactive();
        reapplyMacVisibility(dialogWindow, { mode: 'dialog' });
        dialogWindow.focus();
    });
    dialogWindow.on('blur', () => {
        syncDialogWindowPosition();
    });
    dialogWindow.on('closed', () => {
        dialogWindow = null;
        exitChatMode();
    });
}

ipcMain.on('drag-lock', (_event, locked) => {
    dragLocked = !!locked;
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

    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const nextBounds = {
        x: cursor.x - dragSnapshot.offsetX,
        y: cursor.y - dragSnapshot.offsetY,
        width: PET_CONFIG.width,
        height: PET_CONFIG.height,
    };
    const clamped = clampToDisplay(nextBounds, display);
    petWindow.setPosition(clamped.x, clamped.y);
    syncLinkedWindows();
    syncDialogWindowPosition();
});

ipcMain.on('drag-end', () => {
    dragLocked = false;
    dragSnapshot = null;
    syncLinkedWindows();
    syncDialogWindowPosition();
});

ipcMain.on('start-drag-reaction', () => {
    dragReactionActive = true;
    broadcastPetState();
});

ipcMain.on('end-drag-reaction', () => {
    dragReactionActive = false;
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
