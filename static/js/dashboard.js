// Initialize socket and dashboard state
let socket = null;
const dashboardState = {
    updateInterval: null,
    isConnected: false
};

// Socket configuration
const socketConfig = {
    reconnection: true,
    reconnectionAttempts: 5,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000
};

function initializeWebSocket() {
    // Create new socket instance first
    socket = io(window.location.origin, socketConfig);

    // Then attach event listeners
    socket.on('connect', () => {
        console.log('Connected to websocket');
        dashboardState.isConnected = true;
        updateConnectionStatus('Connected');
        
        // Force update everything on reconnection
        forceUpdateAll();
        
        // Resubscribe to game state on reconnection
        socket.emit('request_game_state');
    });

    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
        updateConnectionStatus('Connection Error');
    });

    socket.on('reconnect_attempt', (attemptNumber) => {
        console.log(`Reconnection attempt ${attemptNumber}`);
        updateConnectionStatus(`Reconnecting (${attemptNumber})...`);
    });

    socket.on('disconnect', (reason) => {
        console.log('Disconnected from websocket:', reason);
        dashboardState.isConnected = false;
        updateConnectionStatus('Disconnected');
    });

    socket.on('reconnect', (attemptNumber) => {
        console.log(`Reconnected after ${attemptNumber} attempts`);
        dashboardState.isConnected = true;
        updateConnectionStatus('Connected');
    });

    socket.on('error', (error) => {
        console.error('Socket error:', error);
        showError('Socket Error: ' + error.message);
    });

    // Game-specific event handlers
    socket.on('new_track', (data) => {
        console.log('Socket: New track event received', data);
        handleNewTrack(data);
        // Force update after new track is played
        Promise.all([
            loadPlayedTracks(),
            loadCards(),
            updateGameStats(),
            updateDashboardData()
        ]).then(() => {
            console.log('Updates completed after new track');
        }).catch(error => {
            console.error('Error updating after new track:', error);
        });
    });

    socket.on('card_status_update', (data) => {
        console.log('Socket: Card status update received', data);
        handleCardStatusUpdate(data);
        // Force update when card status changes
        Promise.all([
            loadCards(),
            updateGameStats(),
            updateDashboardData()
        ]).then(() => {
            console.log('Updates completed after card status change');
        }).catch(error => {
            console.error('Error updating after card status change:', error);
        });
    });

    socket.on('game_state', (data) => {
        console.log('Socket: Game state update received', data);
        handleGameStateUpdate(data);
        // Force update when game state changes
        Promise.all([
            loadPlayedTracks(),
            loadCards(),
            updateGameStats(),
            updateDashboardData()
        ]).then(() => {
            console.log('Updates completed after game state change');
        }).catch(error => {
            console.error('Error updating after game state change:', error);
        });
    });
}

// Helper function to force update all components
async function forceUpdateAll() {
    console.log('Force updating all components...');
    try {
        await Promise.all([
            loadPlayedTracks(),
            loadCards(),
            updateGameStats(),
            updateDashboardData()
        ]);
        console.log('Force update complete');
    } catch (error) {
        console.error('Error during force update:', error);
    }
}

// Single DOMContentLoaded event listener
document.addEventListener('DOMContentLoaded', () => {
    if (typeof io !== 'undefined') {
        initializeWebSocket();
        initializeEventListeners();
        setupDashboardUpdates();
    } else {
        console.error('Socket.io not loaded');
        updateConnectionStatus('Socket.io not available');
    }
});

// Card Management Functions
function showCardModal(cardId) {
    const card = document.querySelector(`[data-card-id="${cardId}"]`).closest('.card-container');
    const modalContent = createCardModalContent(cardId, card._cardData);
    
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center';
    modal.innerHTML = `
        <div class="bg-white p-6 rounded-lg max-w-4xl w-full max-h-90vh overflow-auto">
            <div class="flex justify-between mb-4">
                <h2 class="text-2xl font-bold">Card ID: ${cardId}</h2>
                <button class="text-gray-600 hover:text-gray-800" onclick="this.closest('.fixed').remove()">✕</button>
            </div>
            ${modalContent}
        </div>
    `;
    
    document.body.appendChild(modal);
}

function createCardModalContent(cardId, cardData) {
    let content = `
        <div class="grid grid-cols-5 gap-1">
            ${['B','I','N','G','O'].map(letter => 
                `<div class="bg-gray-500 text-white p-2 text-center font-bold">${letter}</div>`
            ).join('')}`;

    cardData.tracks.forEach((track, i) => {
        const isMatched = cardData.matches?.includes(i);
        content += `
            <div class="border p-2 text-xs ${isMatched ? 'bg-green-200' : ''} min-h-[80px]">
                <div class="font-bold">${track.artist}</div>
                <div>${track.name}</div>
            </div>`;
    });

    content += '</div>';
    return content;
}

async function validateCard(cardId) {
    try {
        socket.emit('card_validated', { card_id: cardId });
        const response = await fetchJSON(`/card/api/check_card/${cardId}`);
        showSuccess(`Card ${cardId}: ${response.status}`);
        await loadCards();
    } catch (error) {
        showError(error.message);
    }
}

async function validateCardPosition(cardId, trackId, position) {
    try {
        const response = await fetchJSON('/card/api/validate_card', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ card_id: cardId, track_id: trackId, position: position })
        });

        if (response.valid) {
            if (response.has_bingo) {
                showSuccess(`BINGO! Card ${cardId} has won!`);
            } else {
                showSuccess('Position validated successfully');
            }
            await loadCards();
        }
        return response;
    } catch (error) {
        showError(error.message);
        return null;
    }
}

// Data Loading Functions
async function loadPlaylists() {
    try {
        const data = await fetchJSON('/playlist/api/get_playlists');
        const sel = document.getElementById('playlistSelect');
        sel.innerHTML = '';
        data.playlists.forEach(pl => {
            const opt = document.createElement('option');
            opt.value = pl.id;
            opt.textContent = pl.name;
            if (pl.is_default) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch (error) {
        console.error('Error loading playlists:', error);
    }
}

async function loadDevices() {
    try {
        const data = await fetchJSON('/device/api/get_devices');
        const devSel = document.getElementById('deviceSelect');
        devSel.innerHTML = '';
        if (data.devices && Array.isArray(data.devices)) {
            data.devices.forEach(device => {
                const opt = document.createElement('option');
                opt.value = device.id;
                opt.textContent = `${device.name} ${device.is_active ? '(active)' : ''} ${device.is_restricted ? '[restricted]' : ''}`;
                if (device.is_active) opt.selected = true;
                devSel.appendChild(opt);
            });
        }
    } catch (error) {
        console.error('Error loading devices:', error);
        if (error.message.includes('Spotify authentication required')) {
            window.location.href = '/auth/login';
        } else {
            showError('Failed to load devices');
        }
    }
}

async function loadPlayedTracks() {
    try {
        const data = await fetchJSON('/playback/api/played_tracks');
        const listElem = document.getElementById('playedTracksList');
        listElem.innerHTML = '';
        data.played_tracks.forEach(t => {
            const li = document.createElement('li');
            li.textContent = `${t.artist} - ${t.name}`;
            listElem.appendChild(li);
        });
    } catch (error) {
        console.error('Error loading played tracks:', error);
    }
}

async function loadCards() {
    console.log('Loading cards...');
    try {
        const data = await fetchJSON('/card/api/get_cards');
        console.log('Received cards data:', data);
        const cardsContainer = document.getElementById('cardsContainer');
        if (cardsContainer) {
            cardsContainer.innerHTML = '';
            Object.entries(data.cards).forEach(([cardId, cardData]) => {
                cardsContainer.appendChild(createBingoCardDisplay(cardId, cardData));
            });
            console.log('Cards display updated');
        }
    } catch (error) {
        console.error('Error loading cards:', error);
    }
}

// Event Handlers
function handleCardStatusUpdate(data) {
    const { card_id, status, matches } = data;
    console.log('Card status update:', data);
    updateCardDisplay(card_id, status, matches);
    loadCards();
}

function handleNewTrack(trackData) {
    console.log('New track played:', trackData);
    showSuccess(`Now playing: ${trackData.artist} - ${trackData.name}`);
    
    // Debug log for update sequence
    console.log('Starting updates after new track...');
    
    // Update everything in sequence
    Promise.all([
        loadPlayedTracks(),
        loadCards(),
        updateGameStats(),
        updateDashboardData()
    ]).then(() => {
        console.log('All updates completed after new track');
    }).catch(error => {
        console.error('Error updating after new track:', error);
    });
}

function handleGameStateUpdate(state) {
    console.log('Game state update:', state);
    updateDashboardData();
}

function handleSocketError(error) {
    console.error('Socket error:', error);
    showError(error.message || 'An error occurred');
}

// Event Listeners Setup
function initializeEventListeners() {
    // Playlist Management
    const btnAddPlaylist = document.getElementById('btnAddPlaylist');
    if (btnAddPlaylist) {
        btnAddPlaylist.addEventListener('click', async () => {
            const playlistId = document.getElementById('newPlaylistID').value.trim();
            const isDefault = document.getElementById('newPlaylistDefault').checked;
            const msgEl = document.getElementById('addPlaylistMsg');

            if (!playlistId) {
                msgEl.textContent = 'Please enter a playlist ID';
                return;
            }

            try {
                await fetchJSON('/playlist/api/add_playlist', {
                    method: 'POST',
                    body: JSON.stringify({ playlist_id: playlistId, is_default: isDefault })
                });
                showSuccess('Playlist added successfully');
                await loadPlaylists();
            } catch (error) {
                msgEl.textContent = error.message;
            }
        });
    }

    // Load Playlist
    const btnLoadPlaylist = document.getElementById('btnLoadPlaylist');
    if (btnLoadPlaylist) {
        btnLoadPlaylist.addEventListener('click', async () => {
            const playlistSelect = document.getElementById('playlistSelect');
            const msgEl = document.getElementById('playlistMsg');

            if (!playlistSelect.value) {
                msgEl.textContent = 'Please select a playlist';
                return;
            }

            try {
                const res = await fetchJSON('/playlist/api/load_playlist', {
                    method: 'POST',
                    body: JSON.stringify({ playlist_id: playlistSelect.value })
                });
                showSuccess(res.message);
                msgEl.textContent = '';
            } catch (error) {
                msgEl.textContent = error.message;
            }
        });
    }

    // Device Management
    setupDeviceManagement();

    // Card Generation
    const btnGenerateCards = document.getElementById('btnGenerateCards');
    if (btnGenerateCards) {
        btnGenerateCards.addEventListener('click', async () => {
            const numCards = document.getElementById('numCardsInput').value || 16;
            try {
                const res = await fetchJSON('/card/api/generate_cards', {
                    method: 'POST',
                    body: JSON.stringify({ num_cards: numCards })
                });
                showSuccess(res.message);
                await loadCards();
            } catch (error) {
                showError(error.message);
            }
        });
    }

    // PDF Download
    const btnDownloadPdf = document.getElementById('btnDownloadPdf');
    if (btnDownloadPdf) {
        btnDownloadPdf.addEventListener('click', handleDownloadPdf);
    }

    // Playback Controls
    setupPlaybackControls();

    // Keyboard Shortcuts
    setupKeyboardShortcuts();
}

function setupDeviceManagement() {
    const btnRefreshDevices = document.getElementById('btnRefreshDevices');
    if (btnRefreshDevices) {
        btnRefreshDevices.addEventListener('click', loadDevices);
    }

    const btnSelectDevice = document.getElementById('btnSelectDevice');
    if (btnSelectDevice) {
        btnSelectDevice.addEventListener('click', async () => {
            const deviceId = document.getElementById('deviceSelect').value;
            const msgEl = document.getElementById('deviceMsg');

            if (!deviceId) {
                msgEl.textContent = 'Please select a device';
                return;
            }

            try {
                const res = await fetchJSON('/device/api/select_device', {
                    method: 'POST',
                    body: JSON.stringify({ device_id: deviceId })
                });
                showSuccess('Device selected successfully');
                msgEl.textContent = '';
            } catch (error) {
                msgEl.textContent = error.message;
            }
        });
    }
}

function setupPlaybackControls() {
    const btnPlay = document.getElementById('btnPlay');
    if (btnPlay) {
        btnPlay.addEventListener('click', async () => {
            try {
                const res = await fetchJSON('/playback/api/play', { method: 'POST' });
                showSuccess(`Playing: ${res.track.artist} - ${res.track.name}`);
                await loadPlayedTracks();
                await loadCards();
            } catch (error) {
                showError(error.message);
            }
        });
    }

    const btnPause = document.getElementById('btnPause');
    if (btnPause) {
        btnPause.addEventListener('click', async () => {
            try {
                await fetchJSON('/playback/api/pause', { method: 'POST' });
                showSuccess('Playback paused');
            } catch (error) {
                showError(error.message);
            }
        });
    }

    const btnNewRound = document.getElementById('btnNewRound');
    if (btnNewRound) {
        btnNewRound.addEventListener('click', async () => {
            try {
                await fetchJSON('/game/api/new_round', { method: 'POST' });
                showSuccess('New round started');
                document.getElementById('playedTracksList').innerHTML = '';
                await loadCards();
            } catch (error) {
                showError(error.message);
            }
        });
    }
}

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (event) => {
        if (event.target.tagName === 'INPUT') return;

        switch(event.key.toLowerCase()) {
            case ' ':
                event.preventDefault();
                document.getElementById('btnPlay')?.click();
                break;
            case 'p':
                event.preventDefault();
                document.getElementById('btnPause')?.click();
                break;
            case 'r':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    document.getElementById('btnNewRound')?.click();
                }
                break;
            case 'd':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    document.getElementById('btnRefreshDevices')?.click();
                }
                break;
        }
    });
}

// Utility Functions
async function fetchJSON(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `HTTP error! status: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`Error fetching ${url}:`, error);
        showError(error.message);
        throw error;
    }
}

function createBingoCardDisplay(cardId, cardData) {
    const div = document.createElement('div');
    div.className = 'card-container border rounded-lg p-4 mb-4 flex justify-between items-center';
    div.setAttribute('data-card-id', cardId);
    div._cardData = cardData;

    div.innerHTML = `
        <div class="text-lg font-bold">Card ID: ${cardId}</div>
        <div class="flex gap-2">
            <button onclick="showCardModal('${cardId}')" class="bg-blue-500 text-white px-4 py-2 rounded hover:opacity-90">
                View Card
            </button>
            <button onclick="validateCard('${cardId}')" class="${cardData.bingo_status === 'BINGO!' ? 'bg-green-500' : 'bg-gray-500'} text-white px-4 py-2 rounded hover:opacity-90">
                ${cardData.bingo_status || 'Check Card'}
            </button>
        </div>
    `;
    return div;
}

async function handleDownloadPdf() {
    try {
        const response = await fetch('/card/api/download_cards_pdf');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'bingo_cards.pdf';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Error downloading PDF:', error);
        showError('Failed to download the PDF. Please try again.');
    }
}

function updateConnectionStatus(status) {
    const statusEl = document.getElementById('connectionStatus');
    if (statusEl) {
        statusEl.textContent = `Connection: ${status}`;
        statusEl.className = status === 'Connected' ? 'text-green-600' : 'text-red-600';
    }
}

function showNotification(message, type = 'info') {
    const container = document.getElementById('notificationContainer');
    const notification = document.createElement('div');
    notification.className = `p-4 rounded-lg shadow-lg mb-2 ${
        type === 'error' ? 'bg-red-500' :
        type === 'success' ? 'bg-green-500' :
        'bg-blue-500'
    } text-white`;
    notification.textContent = message;
    container.appendChild(notification);
    setTimeout(() => notification.remove(), 5000);
}

function showError(message) {
    showNotification(message, 'error');
}

function showSuccess(message) {
    showNotification(message, 'success');
}

function updateCardDisplay(cardId, status, matches) {
    const card = document.querySelector(`[data-card-id="${cardId}"]`);
    if (card) {
        const statusButton = card.querySelector('button:last-child');
        statusButton.textContent = status;
        statusButton.className = status === 'BINGO!' ? 
            'bg-green-500 text-white px-4 py-2 rounded hover:opacity-90' : 
            'bg-gray-500 text-white px-4 py-2 rounded hover:opacity-90';
        
        // Update the stored card data
        if (card._cardData) {
            card._cardData.matches = matches;
            card._cardData.bingo_status = status;
        }
    }
}

async function updateDashboardData() {
    console.log('Starting dashboard data update...');
    try {
        const [dashboardData, stats] = await Promise.all([
            fetchJSON('/dashboard/api/dashboard_data'),
            fetchJSON('/dashboard/api/dashboard_stats')
        ]);
        console.log('Received dashboard data:', dashboardData);
        console.log('Received stats:', stats);
        
        updateDashboardUI(dashboardData);
        if (stats) {
            updateStatisticsDisplay(stats);
        }
    } catch (error) {
        console.error('Error updating dashboard:', error);
    }
}
function updateDashboardUI(data) {
    // Update game state information
    if (data.game_state) {
        updateElement('numTracks', data.game_state.num_tracks || 0);
        updateElement('playedTracks', data.game_state.played_tracks || 0);
        updateElement('totalCards', data.game_state.cards || 0);
    }
    
    // Update card summaries if present
    if (data.card_summaries) {
        const container = document.getElementById('cardSummariesContainer');
        if (container) {
            container.innerHTML = Object.entries(data.card_summaries)
                .map(([cardId, status]) => `
                    <div class="flex justify-between items-center p-2 border-b">
                        <span class="font-medium">${cardId}</span>
                        <span class="${getStatusClass(status)}">${status}</span>
                    </div>
                `).join('');
        }
    }
}

function getStatusClass(status) {
    switch(status) {
        case 'BINGO!':
            return 'text-green-600 font-bold';
        case 'Row bingo':
        case 'Column bingo':
            return 'text-blue-600 font-bold';
        default:
            return 'text-gray-600';
    }
}

function updateElement(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

async function updateGameStats() {
    console.log('Starting game stats update...');
    try {
        const stats = await fetchJSON('/dashboard/api/dashboard_stats');
        console.log('Received new game stats:', stats);
        updateStatisticsDisplay(stats);
        return stats;
    } catch (error) {
        console.error('Error updating game stats:', error);
        return null;
    }
}

function updateStatisticsDisplay(stats) {
    if (!stats) return;
    
    // Update all statistics counters with null checks
    const counters = {
        'totalTracksCount': stats.total_tracks || 0,
        'playedTracksCount': stats.played_tracks || 0,
        'remainingTracksCount': stats.remaining_tracks || 0,
        'cardsWithMatches': stats.cards_with_matches || 0,
        'bingoCount': stats.bingos || 0
    };

    Object.entries(counters).forEach(([id, value]) => {
        updateElement(id, value);
    });
}

function setupDashboardUpdates() {
    console.log('Setting up dashboard updates...');
    
    // Initial load of data
    Promise.all([
        loadPlaylists(),
        loadDevices(),
        loadPlayedTracks(),
        loadCards(),
        updateGameStats(),
        updateDashboardData()
    ]).then(() => {
        console.log('Initial data load complete');
    }).catch(error => {
        console.error('Error loading initial data:', error);
    });

    // Set up periodic updates with shorter interval
    dashboardState.updateInterval = setInterval(async () => {
        console.log('Running periodic update...');
        try {
            await Promise.all([
                loadPlayedTracks(),
                loadCards(),
                updateGameStats(),
                updateDashboardData()
            ]);
            console.log('Periodic update complete');
        } catch (error) {
            console.error('Error during periodic update:', error);
        }
    }, 3000); // Reduced to 3 seconds for more responsive updates
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (socket) {
        socket.close();
    }
    if (dashboardState.updateInterval) {
        clearInterval(dashboardState.updateInterval);
    }
});