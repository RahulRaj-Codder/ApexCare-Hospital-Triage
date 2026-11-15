/**
 * Global Frontend JavaScript for ApexCare Patient Triage & Queue Management System
 * GEC Hackathon 2026 - Problem Statement 01
 */

// Web Audio API Synthesizer for Hospital PA Chimes and Emergency Buzzer
let audioCtx = null;

function getAudioContext() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    return audioCtx;
}

function playAudioAlert(type = 'ROUTINE') {
    try {
        const ctx = getAudioContext();
        const now = ctx.currentTime;

        if (type === 'CRITICAL') {
            // Urgent 3-tone warning chime
            const freqs = [880, 587.33, 880];
            freqs.forEach((freq, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(freq, now + idx * 0.15);
                gain.gain.setValueAtTime(0.2, now + idx * 0.15);
                gain.gain.exponentialRampToValueAtTime(0.01, now + (idx + 1) * 0.15);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.15);
                osc.stop(now + (idx + 1) * 0.15);
            });
        } else {
            // Gentle 2-tone melodic hospital chime
            const freqs = [523.25, 659.25];
            freqs.forEach((freq, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now + idx * 0.25);
                gain.gain.setValueAtTime(0.25, now + idx * 0.25);
                gain.gain.exponentialRampToValueAtTime(0.01, now + (idx + 1) * 0.35);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.25);
                osc.stop(now + (idx + 1) * 0.35);
            });
        }
    } catch (e) {
        console.warn("Audio chime prevented by browser gesture policy:", e);
    }
}

// Global Toast Alerts
function showLiveToast(title, message, isCritical = false) {
    const container = document.getElementById('live-alert-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `p-4 rounded-2xl shadow-xl border pointer-events-auto transition-all transform duration-300 translate-x-full ${
        isCritical
            ? 'bg-red-950/95 border-red-500/80 text-white'
            : 'bg-slate-900/95 border-slate-700 text-white'
    }`;

    toast.innerHTML = `
        <div class="flex items-start space-x-3 text-xs">
            <div class="${isCritical ? 'text-red-400' : 'text-sky-400'} text-base mt-0.5">
                <i class="fa-solid ${isCritical ? 'fa-triangle-exclamation' : 'fa-bell'}"></i>
            </div>
            <div class="flex-1">
                <div class="font-bold ${isCritical ? 'text-red-300' : 'text-sky-300'}">${title}</div>
                <div class="text-slate-300 mt-0.5 text-[11px] leading-relaxed">${message}</div>
            </div>
            <button onclick="this.parentElement.parentElement.remove()" class="text-slate-400 hover:text-white">&times;</button>
        </div>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.remove('translate-x-full'));

    setTimeout(() => {
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => toast.remove(), 400);
    }, isCritical ? 9000 : 5000);
}

// Setup Global SSE (Server-Sent Events) Stream
function initGlobalSSE() {
    if (!window.EventSource) return;

    const source = new EventSource('/api/events/stream');
    const indicator = document.getElementById('sse-indicator');

    source.onopen = () => {
        if (indicator) {
            indicator.className = "flex items-center space-x-1.5 px-2 py-1 rounded-full bg-slate-800 text-emerald-400 text-xs border border-slate-700";
        }
    };

    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'PRIORITY_ELEVATED') {
                playAudioAlert('CRITICAL');
                showLiveToast(
                    "EMERGENCY PRIORITY ELEVATED",
                    `Token ${data.payload.token_no} (${data.payload.patient_name}) assigned CRITICAL priority. Synchronous preemption executed.`,
                    true
                );
                if (typeof loadDashboardQueue === 'function') loadDashboardQueue();
                if (typeof fetchQueue === 'function') fetchQueue();
            } else if (data.type === 'PATIENT_CALLED') {
                playAudioAlert('ROUTINE');
                showLiveToast(
                    "PATIENT CALLED TO CONSULTATION",
                    `Token ${data.payload.token_no} (${data.payload.patient_name}) called to Room ${data.payload.room_no}.`,
                    false
                );
                if (typeof loadDashboardQueue === 'function') loadDashboardQueue();
                if (typeof fetchQueue === 'function') fetchQueue();
            } else if (data.type === 'DOCTOR_AVAILABLE') {
                showLiveToast(
                    "DOCTOR NOW AVAILABLE",
                    `${data.payload.doctor_name || 'Doctor'} is ready for consultation.`,
                    false
                );
            }
        } catch (e) {
            console.error("SSE JSON parsing error:", e);
        }
    };

    source.onerror = () => {
        if (indicator) {
            indicator.className = "flex items-center space-x-1.5 px-2 py-1 rounded-full bg-slate-800 text-amber-400 text-xs border border-slate-700";
        }
    };
}

document.addEventListener('DOMContentLoaded', () => {
    initGlobalSSE();
});
