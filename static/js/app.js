/**
 * Banet - Frontend Controller
 * Real-time WebSockets with automatic HTTP polling fallback,
 * One-click server switching, network optimization & router reboot controls.
 */

// State
const state = {
  activeTab: 'live',
  currentNetwork: null,
  socket: null,
  reconnectTimer: null,
  pollTimer: null,
  lastPacketTime: 0,
  isTesting: false,
  charts: {
    latency: null,
    bandwidth: null,
    history: null
  },
  liveData: {
    labels: [],
    pingHistory: [],
    jitterHistory: [],
    dlHistory: [],
    ulHistory: []
  }
};

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
  initIcons();
  setupTabs();
  setupDestinationPills();
  setupCharts();
  fetchCurrentNetwork();
  fetchNetworkList();
  fetchImmediateLiveStats();
  connectWebSocket();
  startFallbackPolling();
  setupSpeedTest();
  setupAnalytics();
  setupRenameModal();
  setupOptimizerModal();
});

function initIcons() {
  if (window.lucide) {
    lucide.createIcons();
  }
}

// --- TAB SWITCHING ---
function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      switchTab(targetTab);
    });
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  
  document.querySelectorAll('.tab-btn').forEach(btn => {
    if (btn.getAttribute('data-tab') === tabId) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  document.querySelectorAll('.tab-content').forEach(section => {
    if (section.id === `tab-${tabId}`) {
      section.classList.remove('hidden');
      section.classList.add('block');
    } else {
      section.classList.add('hidden');
      section.classList.remove('block');
    }
  });

  if (tabId === 'analytics') {
    loadAnalytics();
  }
  initIcons();
}

// --- NETWORK PROFILE & PERSISTENT NAMING ---
async function fetchCurrentNetwork() {
  try {
    const res = await fetch('/api/network/current');
    const net = await res.json();
    state.currentNetwork = net;
    updateNetworkUI(net);
  } catch (err) {
    console.error('Failed to detect network:', err);
  }
}

async function fetchNetworkList() {
  try {
    const res = await fetch('/api/network/list');
    const list = await res.json();
    const select = document.getElementById('networkFilterSelect');
    if (select) {
      const currentVal = select.value;
      select.innerHTML = '<option value="">All Saved Connections</option>';
      list.forEach(n => {
        const opt = document.createElement('option');
        opt.value = n.id;
        opt.textContent = `${n.custom_name} (${n.test_count || 0} tests)`;
        select.appendChild(opt);
      });
      select.value = currentVal;
    }
  } catch (err) {
    console.error('Failed to fetch network list:', err);
  }
}

function updateNetworkUI(net) {
  if (!net) return;
  
  const nameEl = document.getElementById('currentNetworkName');
  const ispEl = document.getElementById('currentIsp');
  const locEl = document.getElementById('currentCityCountry');
  const iconEl = document.getElementById('connectionTypeIcon');
  const speedTargetName = document.getElementById('speedTestTargetNetName');

  if (nameEl) nameEl.textContent = net.custom_name || 'Active Network';
  if (ispEl) ispEl.textContent = net.isp || 'Local Provider';
  if (locEl) locEl.textContent = `${net.city || 'Unknown'}, ${net.country || ''}`.trim().replace(/^,|,$/g, '');
  if (speedTargetName) speedTargetName.textContent = net.custom_name || 'Current Connection';

  if (iconEl && window.lucide) {
    const iconName = net.detected_type === 'wifi' ? 'wifi' : (net.detected_type === 'vpn' ? 'shield-check' : 'network');
    iconEl.setAttribute('data-lucide', iconName);
    lucide.createIcons();
  }

  // Home router destination pill update
  const gwBtn = document.getElementById('gatewayTargetBtn');
  const gwSub = document.getElementById('gatewayPillSub');
  const gwDisplay = document.getElementById('routerGatewayIpDisplay');
  const gwAdminLink = document.getElementById('openRouterAdminLink');

  if (net.gateway_ip) {
    if (gwBtn) gwBtn.setAttribute('data-target', net.gateway_ip);
    if (gwSub) gwSub.textContent = `Router (${net.gateway_ip})`;
    if (gwDisplay) gwDisplay.textContent = net.gateway_ip;
    if (gwAdminLink) {
      gwAdminLink.href = `http://${net.gateway_ip}`;
      gwAdminLink.querySelector('span').textContent = `Open Console (${net.gateway_ip})`;
    }
  }

  // Diagnostics Tab
  document.getElementById('diagCustomName').textContent = net.custom_name || '--';
  document.getElementById('diagFingerprint').textContent = net.fingerprint || '--';
  document.getElementById('diagMedium').textContent = (net.detected_type || 'Ethernet').toUpperCase();
  document.getElementById('diagSsid').textContent = net.ssid ? `Connected to "${net.ssid}"` : 'Not on Wi-Fi';
  document.getElementById('diagFirstSeen').textContent = net.first_seen ? new Date(net.first_seen).toLocaleString() : '--';
  document.getElementById('diagLastSeen').textContent = net.last_seen ? new Date(net.last_seen).toLocaleString() : '--';
  
  document.getElementById('diagPublicIp').textContent = net.public_ip || '--';
  document.getElementById('diagLocalIp').textContent = net.local_ip || '--';
  document.getElementById('diagGatewayIp').textContent = net.gateway_ip || '--';
  document.getElementById('diagIsp').textContent = `${net.isp || '--'} ${net.asn ? '(' + net.asn + ')' : ''}`;
  document.getElementById('diagLocation').textContent = `${net.city || ''}, ${net.country || ''}`.trim().replace(/^,|,$/g, '') || '--';
  document.getElementById('diagAdapter').textContent = net.adapter_name || '--';
}

function setupRenameModal() {
  const modal = document.getElementById('renameModal');
  const openBtn = document.getElementById('renameNetworkBtn');
  const closeBtn = document.getElementById('closeModalBtn');
  const cancelBtn = document.getElementById('cancelRenameBtn');
  const saveBtn = document.getElementById('saveRenameBtn');
  const input = document.getElementById('networkNameInput');

  const openModal = () => {
    if (state.currentNetwork) {
      input.value = state.currentNetwork.custom_name || '';
    }
    modal.classList.add('open');
    input.focus();
  };

  const closeModal = () => {
    modal.classList.remove('open');
  };

  if (openBtn) openBtn.addEventListener('click', openModal);
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const newName = input.value.trim();
      if (!newName || !state.currentNetwork) return;

      try {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        const res = await fetch('/api/network/rename', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            network_id: state.currentNetwork.network_id,
            custom_name: newName
          })
        });
        if (res.ok) {
          state.currentNetwork.custom_name = newName;
          updateNetworkUI(state.currentNetwork);
          fetchNetworkList();
          closeModal();
        }
      } catch (err) {
        alert('Failed to rename network: ' + err.message);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Name';
      }
    });
  }
}

// --- OPTIMIZER & ROUTER RESTART CONTROLS ---
function setupOptimizerModal() {
  const modal = document.getElementById('optimizerModal');
  const openBtn = document.getElementById('openOptimizerBtn');
  const closeBtn = document.getElementById('closeOptimizerBtn');
  const footerCloseBtn = document.getElementById('closeOptimizerFooterBtn');

  const runOptBtn = document.getElementById('runOptimizeBtn');
  const optBox = document.getElementById('optimizeStatusBox');

  const rebootBtn = document.getElementById('rebootRouterBtn');
  const rebootBox = document.getElementById('rebootStatusBox');

  const openModal = () => modal.classList.add('open');
  const closeModal = () => modal.classList.remove('open');

  if (openBtn) openBtn.addEventListener('click', openModal);
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (footerCloseBtn) footerCloseBtn.addEventListener('click', closeModal);

  // 1. Run Quick Network Boost
  if (runOptBtn) {
    runOptBtn.addEventListener('click', async () => {
      runOptBtn.disabled = true;
      runOptBtn.innerHTML = `
        <svg class="animate-spin -ml-1 mr-1 h-3.5 w-3.5 text-white inline" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg> Optimizing...
      `;
      optBox.classList.remove('hidden');
      optBox.innerHTML = `<span>⏳ Flushing DNS client cache & refreshing routes...</span>`;

      try {
        const gw = state.currentNetwork ? state.currentNetwork.gateway_ip : "192.168.1.1";
        const res = await fetch('/api/network/optimize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gateway_ip: gw })
        });
        const data = await res.json();
        
        optBox.innerHTML = `
          <div class="space-y-1">
            <div class="text-emerald-400 font-semibold">✓ DNS resolver cache cleared successfully</div>
            <div class="text-slate-300">Latency verification: <span class="text-cyan-400">${data.after_ping_ms || '--'} ms</span></div>
          </div>
        `;
        fetchImmediateLiveStats();
      } catch (err) {
        optBox.innerHTML = `<span class="text-rose-400">Optimization notice: ${err.message}</span>`;
      } finally {
        runOptBtn.disabled = false;
        runOptBtn.innerHTML = `<span>Run Boost</span>`;
      }
    });
  }

  // 2. Restart Router
  if (rebootBtn) {
    rebootBtn.addEventListener('click', async () => {
      if (!confirm('Send reboot command to your router? Your internet connection will temporarily disconnect for ~60 seconds.')) {
        return;
      }

      rebootBtn.disabled = true;
      rebootBtn.innerHTML = `
        <svg class="animate-spin -ml-1 mr-1 h-3.5 w-3.5 text-white inline" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg> Signaling...
      `;
      rebootBox.classList.remove('hidden');
      rebootBox.innerHTML = `<span>⏳ Transmitting UPnP reboot signal to gateway...</span>`;

      try {
        const gw = state.currentNetwork ? state.currentNetwork.gateway_ip : "192.168.1.1";
        const res = await fetch('/api/network/reboot-router', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ gateway_ip: gw })
        });
        const data = await res.json();

        rebootBox.innerHTML = `
          <div class="space-y-1">
            <div class="text-purple-300 font-semibold">✓ Reboot signal sent to ${data.gateway_ip}</div>
            <div class="text-slate-400 text-[11px]">${data.message}</div>
          </div>
        `;
      } catch (err) {
        rebootBox.innerHTML = `<span class="text-rose-400">Could not send reboot signal: ${err.message}</span>`;
      } finally {
        rebootBtn.disabled = false;
        rebootBtn.innerHTML = `<i data-lucide="power" class="w-3.5 h-3.5"></i><span>Restart Router</span>`;
        initIcons();
      }
    });
  }
}

// --- ONE-CLICK DESTINATION OPTIONS (CLICK TO SET IMMEDIATELY) ---
function setupDestinationPills() {
  const pills = document.querySelectorAll('.destination-pill');
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      // Toggle active states
      pills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');

      const target = pill.getAttribute('data-target');
      const label = pill.getAttribute('data-label') || 'Target Server';

      const activeLabel = document.getElementById('activeTargetLabel');
      const chartLabel = document.getElementById('chartTargetLabel');
      if (activeLabel) activeLabel.textContent = label;
      if (chartLabel) chartLabel.textContent = label;

      // Immediately activate and switch target
      changeTarget(target, label);
    });
  });
}

async function changeTarget(target, label) {
  try {
    await fetch('/api/monitor/target', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target })
    });
    // Reset points
    state.liveData.pingHistory = [];
    state.liveData.jitterHistory = [];
    state.liveData.labels = [];
    fetchImmediateLiveStats();
  } catch (err) {
    console.error('Target change failed', err);
  }
}

// --- LIVE TELEMETRY: WEBSOCKET + DUAL POLLING FALLBACK ---
async function fetchImmediateLiveStats() {
  try {
    const res = await fetch('/api/monitor/live');
    if (res.ok) {
      const data = await res.json();
      handleLiveTelemetry(data);
    }
  } catch (err) {
    console.warn('Initial live stats fetch:', err);
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host || '127.0.0.1:8000';
  const wsUrl = `${protocol}//${host}/ws/live`;

  try {
    const ws = new WebSocket(wsUrl);
    state.socket = ws;

    ws.onopen = () => {
      clearTimeout(state.reconnectTimer);
      updateStatusHeader('online', 'Online & Tracking');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'speedtest_progress') {
          handleSpeedTestProgress(msg.data);
        } else {
          handleLiveTelemetry(msg);
        }
      } catch (e) {
        console.error('WS parse error', e);
      }
    };

    ws.onclose = () => {
      updateStatusHeader('online', 'Online & Tracking');
      state.reconnectTimer = setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = () => {
      ws.close();
    };
  } catch (err) {
    state.reconnectTimer = setTimeout(connectWebSocket, 3000);
  }
}

// Polling Fallback ensures telemetry NEVER freezes even if WebSockets are blocked
function startFallbackPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    const now = Date.now();
    // If no WebSocket message arrived in the last 2 seconds, poll HTTP
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN || (now - state.lastPacketTime > 2000)) {
      try {
        const res = await fetch('/api/monitor/live');
        if (res.ok) {
          const data = await res.json();
          handleLiveTelemetry(data);
        }
      } catch (e) {
        updateStatusHeader('offline', 'Disconnected');
      }
    }
  }, 1000);
}

function updateStatusHeader(status, text) {
  const dot = document.getElementById('headerStatusDot');
  const textEl = document.getElementById('headerStatusText');
  if (dot) dot.className = `status-dot ${status}`;
  if (textEl) {
    textEl.textContent = text;
    textEl.className = status === 'online' ? 'font-medium text-emerald-400' : (status === 'degraded' ? 'font-medium text-amber-400' : 'font-medium text-rose-400');
  }
}

function handleLiveTelemetry(data) {
  if (!data) return;
  state.lastPacketTime = Date.now();

  const livePingEl = document.getElementById('livePing');
  const minPingEl = document.getElementById('minPing');
  const avgPingEl = document.getElementById('avgPing');
  const maxPingEl = document.getElementById('maxPing');

  const liveJitterEl = document.getElementById('liveJitter');
  const jitterBadge = document.getElementById('jitterBadge');

  const liveLossEl = document.getElementById('livePacketLoss');
  const lossBadge = document.getElementById('lossBadge');

  const liveDlEl = document.getElementById('liveDownloadRate');
  const liveUlEl = document.getElementById('liveUploadRate');

  // Ping readout
  if (data.ping_ms !== null && data.ping_ms !== undefined) {
    livePingEl.textContent = data.ping_ms;
  } else {
    livePingEl.textContent = '--';
  }

  minPingEl.textContent = (data.min_ping !== null && data.min_ping !== undefined) ? data.min_ping : '--';
  avgPingEl.textContent = (data.avg_ping !== null && data.avg_ping !== undefined) ? data.avg_ping : '--';
  maxPingEl.textContent = (data.max_ping !== null && data.max_ping !== undefined) ? data.max_ping : '--';

  // Jitter readout
  const j = (data.jitter_ms !== null && data.jitter_ms !== undefined) ? data.jitter_ms : 0.0;
  liveJitterEl.textContent = j.toFixed(1);

  if (j < 6) {
    jitterBadge.textContent = 'Ultra Low';
    jitterBadge.className = 'badge badge-green';
  } else if (j < 15) {
    jitterBadge.textContent = 'Stable';
    jitterBadge.className = 'badge badge-blue';
  } else {
    jitterBadge.textContent = 'High Variance';
    jitterBadge.className = 'badge badge-yellow';
  }

  // Packet Loss
  const loss = (data.packet_loss_pct !== null && data.packet_loss_pct !== undefined) ? data.packet_loss_pct : 0;
  liveLossEl.textContent = loss.toFixed(1);
  if (loss === 0) {
    lossBadge.textContent = '0% Drops';
    lossBadge.className = 'badge badge-green';
  } else if (loss < 3) {
    lossBadge.textContent = `${loss.toFixed(1)}% Minor`;
    lossBadge.className = 'badge badge-yellow';
  } else {
    lossBadge.textContent = `${loss.toFixed(1)}% Drops!`;
    lossBadge.className = 'badge badge-red';
  }

  // Bandwidth
  liveDlEl.textContent = `${data.download_mbps !== undefined ? data.download_mbps : 0.0} Mbps`;
  liveUlEl.textContent = `${data.upload_mbps !== undefined ? data.upload_mbps : 0.0} Mbps`;

  // Push to Live Charts
  const nowStr = new Date().toLocaleTimeString();
  const maxHistory = 30;

  state.liveData.labels.push(nowStr);
  state.liveData.pingHistory.push(data.ping_ms !== null ? data.ping_ms : 0);
  state.liveData.jitterHistory.push(j);
  state.liveData.dlHistory.push(data.download_mbps || 0);
  state.liveData.ulHistory.push(data.upload_mbps || 0);

  if (state.liveData.labels.length > maxHistory) {
    state.liveData.labels.shift();
    state.liveData.pingHistory.shift();
    state.liveData.jitterHistory.shift();
    state.liveData.dlHistory.shift();
    state.liveData.ulHistory.shift();
  }

  if (state.charts.latency) {
    state.charts.latency.update('none');
  }
  if (state.charts.bandwidth) {
    state.charts.bandwidth.update('none');
  }
}

// --- CHARTS CONFIGURATION ---
function setupCharts() {
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.font.family = "'JetBrains Mono', Consolas, monospace";

  // 1. Live Latency & Jitter Stream Chart
  const ctxLatency = document.getElementById('liveLatencyChart');
  if (ctxLatency) {
    state.charts.latency = new Chart(ctxLatency.getContext('2d'), {
      type: 'line',
      data: {
        labels: state.liveData.labels,
        datasets: [
          {
            label: 'Ping (ms)',
            data: state.liveData.pingHistory,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.12)',
            borderWidth: 2,
            tension: 0.35,
            fill: true,
            pointRadius: 0
          },
          {
            label: 'Jitter (ms)',
            data: state.liveData.jitterHistory,
            borderColor: '#818cf8',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            borderDash: [4, 4],
            tension: 0.35,
            pointRadius: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: { display: false },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            suggestedMin: 0,
            suggestedMax: 100
          }
        },
        plugins: {
          legend: { position: 'top', align: 'end', labels: { boxWidth: 12, font: { size: 10 } } }
        }
      }
    });
  }

  // 2. Live Bandwidth Chart
  const ctxBandwidth = document.getElementById('liveBandwidthChart');
  if (ctxBandwidth) {
    state.charts.bandwidth = new Chart(ctxBandwidth.getContext('2d'), {
      type: 'line',
      data: {
        labels: state.liveData.labels,
        datasets: [
          {
            label: 'Download (Mbps)',
            data: state.liveData.dlHistory,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.15)',
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 0
          },
          {
            label: 'Upload (Mbps)',
            data: state.liveData.ulHistory,
            borderColor: '#a855f7',
            backgroundColor: 'rgba(168, 85, 247, 0.1)',
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: { display: false },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            suggestedMin: 0,
            suggestedMax: 5
          }
        },
        plugins: {
          legend: { position: 'top', align: 'end', labels: { boxWidth: 12, font: { size: 10 } } }
        }
      }
    });
  }
}

// --- SPEED TEST BENCHMARK ---
function setupSpeedTest() {
  const startBtn = document.getElementById('startSpeedTestBtn');
  if (!startBtn) return;

  startBtn.addEventListener('click', async () => {
    if (state.isTesting) return;

    try {
      state.isTesting = true;
      startBtn.disabled = true;
      startBtn.classList.add('opacity-50', 'cursor-not-allowed');
      startBtn.innerHTML = `
        <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg>
        BENCHMARK RUNNING...
      `;

      updateGauge(0, 'INIT', 'Initializing...');

      const networkId = state.currentNetwork ? state.currentNetwork.network_id : null;
      const url = networkId ? `/api/speedtest/start?network_id=${networkId}` : '/api/speedtest/start';
      
      const res = await fetch(url, { method: 'POST' });
      if (!res.ok) {
        throw new Error('Could not initiate benchmark');
      }
    } catch (err) {
      alert('Speed test error: ' + err.message);
      resetSpeedTestButton();
    }
  });
}

function handleSpeedTestProgress(data) {
  const stage = data.stage;
  const msg = data.message || '';
  const progress = data.progress || 0;

  const msgEl = document.getElementById('speedTestStatusMsg');
  if (msgEl) msgEl.textContent = msg;

  if (stage === 'init') {
    updateGauge(0, 'INIT', msg);
  } else if (stage === 'ping') {
    updateGauge(progress, 'PING', `${data.ping_ms || 0} ms`);
    document.getElementById('gaugeSpeedVal').textContent = data.ping_ms || '0';
    document.getElementById('gaugeUnitVal').textContent = 'ms Latency';
  } else if (stage === 'download') {
    const mbps = data.download_mbps || 0;
    updateGauge(progress, 'DOWNLOAD', msg);
    document.getElementById('gaugeSpeedVal').textContent = mbps ? mbps.toFixed(1) : '--';
    document.getElementById('gaugeUnitVal').textContent = 'Mbps Download';
  } else if (stage === 'upload') {
    const dl = data.download_mbps ? data.download_mbps.toFixed(1) : '--';
    const up = data.upload_mbps ? data.upload_mbps.toFixed(1) : '--';
    updateGauge(progress, 'UPLOAD', msg);
    document.getElementById('gaugeSpeedVal').textContent = up !== '--' ? up : dl;
    document.getElementById('gaugeUnitVal').textContent = 'Mbps Upload';
  } else if (stage === 'complete') {
    const result = data.result;
    updateGauge(100, 'DONE', 'Benchmark Complete');
    document.getElementById('gaugeSpeedVal').textContent = result.download_mbps;
    document.getElementById('gaugeUnitVal').textContent = 'Mbps Down';

    renderSpeedTestResult(result);
    resetSpeedTestButton();
    fetchNetworkList();
  } else if (stage === 'error') {
    updateGauge(0, 'ERROR', msg);
    resetSpeedTestButton();
  }
}

function updateGauge(percentage, stageLabel, detailMsg) {
  const ring = document.getElementById('speedGaugeRing');
  const stageBadge = document.getElementById('gaugeStageBadge');

  if (stageBadge) stageBadge.textContent = stageLabel;

  if (ring) {
    const circumference = 534; // 2 * PI * 85
    const offset = circumference - (percentage / 100.0) * circumference;
    ring.style.strokeDashoffset = offset;
  }
}

function resetSpeedTestButton() {
  state.isTesting = false;
  const btn = document.getElementById('startSpeedTestBtn');
  if (btn) {
    btn.disabled = false;
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
    btn.innerHTML = `<i data-lucide="play" class="w-5 h-5 fill-current"></i><span>START SPEED TEST</span>`;
    initIcons();
  }
}

function renderSpeedTestResult(res) {
  const card = document.getElementById('testResultCard');
  if (!card) return;

  document.getElementById('resDownload').textContent = res.download_mbps;
  document.getElementById('resUpload').textContent = res.upload_mbps;
  document.getElementById('resPing').textContent = res.ping_ms;
  document.getElementById('resJitter').textContent = res.jitter_ms;

  document.getElementById('gradeGaming').textContent = res.gaming_grade || 'A';
  document.getElementById('gradeStreaming').textContent = res.streaming_grade || 'A (4K)';
  document.getElementById('gradeVideo').textContent = res.video_call_grade || 'A';
  document.getElementById('gradeBufferbloat').textContent = res.bufferbloat_grade || 'A';

  document.getElementById('resultNetworkTag').textContent = res.network_name || 'Network';
  document.getElementById('resultTimestamp').textContent = new Date(res.timestamp).toLocaleTimeString();

  card.scrollIntoView({ behavior: 'smooth' });
}

// --- ANALYTICS & HISTORY ---
function setupAnalytics() {
  const filterSelect = document.getElementById('networkFilterSelect');
  if (filterSelect) {
    filterSelect.addEventListener('change', () => {
      loadAnalytics(filterSelect.value);
    });
  }

  document.getElementById('exportCsvBtn').addEventListener('click', () => {
    const netId = filterSelect.value;
    window.location.href = netId ? `/api/export/csv?network_id=${netId}` : '/api/export/csv';
  });

  document.getElementById('exportJsonBtn').addEventListener('click', () => {
    const netId = filterSelect.value;
    window.location.href = netId ? `/api/export/json?network_id=${netId}` : '/api/export/json';
  });

  document.getElementById('clearHistoryBtn').addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear test history? This cannot be undone.')) return;
    const netId = filterSelect.value;
    const url = netId ? `/api/speedtest/clear?network_id=${netId}` : '/api/speedtest/clear';
    await fetch(url, { method: 'POST' });
    loadAnalytics(netId);
    fetchNetworkList();
  });
}

async function loadAnalytics(networkId = '') {
  try {
    const summaryUrl = networkId ? `/api/analytics/summary?network_id=${networkId}` : '/api/analytics/summary';
    const historyUrl = networkId ? `/api/speedtest/history?network_id=${networkId}&limit=50` : '/api/speedtest/history?limit=50';

    const [sumRes, histRes] = await Promise.all([
      fetch(summaryUrl),
      fetch(historyUrl)
    ]);

    const summary = await sumRes.json();
    const history = await histRes.json();

    document.getElementById('statMaxDown').textContent = (summary.max_download || 0).toFixed(1);
    document.getElementById('statAvgDown').textContent = (summary.avg_download || 0).toFixed(1);
    document.getElementById('statMaxUp').textContent = (summary.max_upload || 0).toFixed(1);
    document.getElementById('statAvgUp').textContent = (summary.avg_upload || 0).toFixed(1);
    document.getElementById('statMinPing').textContent = (summary.min_ping || 0).toFixed(1);
    document.getElementById('statTotalTests').textContent = summary.total_tests || 0;

    renderHistoryTable(history);
    renderHistoryChart(history);
  } catch (err) {
    console.error('Failed to load analytics:', err);
  }
}

function renderHistoryTable(records) {
  const tbody = document.getElementById('historyTableBody');
  const countEl = document.getElementById('tableRecordCount');
  if (!tbody) return;

  if (countEl) countEl.textContent = `${records.length} record${records.length === 1 ? '' : 's'}`;

  if (!records || records.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="px-4 py-8 text-center text-slate-500 font-sans">
          No speed tests recorded yet for this connection profile.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = records.map(r => `
    <tr class="hover:bg-white/[0.02] transition">
      <td class="px-4 py-3 text-slate-400 font-sans text-xs">${new Date(r.timestamp).toLocaleDateString()} ${new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
      <td class="px-4 py-3 font-semibold text-slate-200 font-sans">${escapeHtml(r.network_name)}</td>
      <td class="px-4 py-3 text-right text-cyan-400 font-bold">${r.download_mbps} Mbps</td>
      <td class="px-4 py-3 text-right text-indigo-400 font-bold">${r.upload_mbps} Mbps</td>
      <td class="px-4 py-3 text-right text-emerald-400">${r.ping_ms} ms</td>
      <td class="px-4 py-3 text-right text-slate-400">${r.jitter_ms || 0} ms</td>
      <td class="px-4 py-3 text-center">
        <span class="badge ${r.gaming_grade === 'A+' || r.gaming_grade === 'A' ? 'badge-green' : 'badge-yellow'} font-bold">
          ${r.gaming_grade || 'A'}
        </span>
      </td>
      <td class="px-4 py-3 text-center">
        <button class="text-slate-500 hover:text-rose-400 p-1 delete-test-btn" data-id="${r.id}" title="Delete record">
          <i data-lucide="trash" class="w-3.5 h-3.5"></i>
        </button>
      </td>
    </tr>
  `).join('');

  initIcons();

  tbody.querySelectorAll('.delete-test-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      if (confirm('Delete this speed test entry?')) {
        await fetch(`/api/speedtest/${id}`, { method: 'DELETE' });
        loadAnalytics(document.getElementById('networkFilterSelect').value);
      }
    });
  });
}

function renderHistoryChart(records) {
  const ctx = document.getElementById('historySpeedChart');
  if (!ctx) return;

  const reversed = [...records].reverse();
  const labels = reversed.map(r => new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  const dlData = reversed.map(r => r.download_mbps);
  const upData = reversed.map(r => r.upload_mbps);

  if (state.charts.history) {
    state.charts.history.destroy();
  }

  state.charts.history = new Chart(ctx.getContext('2d'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Download (Mbps)',
          data: dlData,
          backgroundColor: 'rgba(6, 182, 212, 0.7)',
          borderRadius: 6,
          barPercentage: 0.6
        },
        {
          label: 'Upload (Mbps)',
          data: upData,
          backgroundColor: 'rgba(99, 102, 241, 0.7)',
          borderRadius: 6,
          barPercentage: 0.6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { grid: { display: false } },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          suggestedMin: 0
        }
      },
      plugins: {
        legend: { position: 'top', align: 'end' }
      }
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
