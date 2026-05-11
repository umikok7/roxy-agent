#!/usr/bin/env node

const http = require('http');

const SERVER_PORT = 23333;
const EVENT_TO_STATE = {
    SessionStart: 'lookAround',
    SessionEnd: 'sleeping',
    UserPromptSubmit: 'thinking',
    PreToolUse: 'thinking',
    PostToolUse: 'task-success',
    PostToolUseFailure: 'task-failure',
    Stop: 'task-success',
    SubagentStart: 'thinking',
    SubagentStop: 'task-success',
};

function inferStopOutcome(payload) {
    if (!payload || typeof payload !== 'object') {
        return 'task-success';
    }

    const textCandidates = [
        payload.stop_reason,
        payload.reason,
        payload.outcome,
        payload.result,
        payload.status,
        payload.error,
        payload.message,
    ]
        .filter((value) => typeof value === 'string' && value.trim())
        .join(' ')
        .toLowerCase();

    if (!textCandidates) {
        return 'task-success';
    }

    if (
        textCandidates.includes('error') ||
        textCandidates.includes('fail') ||
        textCandidates.includes('abort') ||
        textCandidates.includes('cancel') ||
        textCandidates.includes('reached') ||
        textCandidates.includes('max_steps')
    ) {
        return 'task-failure';
    }

    return 'task-success';
}

function readStdinJson() {
    return new Promise((resolve) => {
        const chunks = [];
        let finished = false;

        function done() {
            if (finished) return;
            finished = true;
            try {
                const raw = Buffer.concat(chunks).toString('utf8').trim();
                resolve(raw ? JSON.parse(raw) : {});
            } catch {
                resolve({});
            }
        }

        process.stdin.on('data', (chunk) => chunks.push(chunk));
        process.stdin.on('end', done);
        setTimeout(done, 400);
    });
}

function postState(payload) {
    return new Promise((resolve) => {
        const body = JSON.stringify(payload);
        const req = http.request(
            {
                hostname: '127.0.0.1',
                port: SERVER_PORT,
                path: '/state',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body),
                },
                timeout: 150,
            },
            (res) => {
                res.resume();
                resolve();
            }
        );

        req.on('error', resolve);
        req.on('timeout', () => {
            req.destroy();
            resolve();
        });
        req.end(body);
    });
}

async function main() {
    const event = process.argv[2];
    const payload = await readStdinJson();
    const mappedState = EVENT_TO_STATE[event];
    if (!mappedState) return;
    const state = event === 'Stop' ? inferStopOutcome(payload) : mappedState;
    await postState({
        state,
        event,
        agent_id: 'claude-code',
        session_id: payload.session_id || 'default',
    });
}

main().finally(() => process.exit(0));
