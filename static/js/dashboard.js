// Near top of file
let socket = io(window.location.origin);

socket.on('connect', () => {
    console.log('Connected to websocket');
    updateConnectionStatus('Connected');
});

socket.on('card_status_update', (data) => {
    console.log('Card status update:', data);
    const { card_id, status, matches } = data;
    updateCardStatus(card_id, status, matches);
    loadCards();
});

socket.on('disconnect', () => {
    console.log('Disconnected from websocket');
    updateConnectionStatus('Disconnected');
});

function updateCardStatus(cardId, status, matches) {
    const card = document.querySelector(`[data-card-id="${cardId}"]`);
    if (card) {
        const statusButton = card.querySelector('button');
        statusButton.textContent = status;
        statusButton.className = status === 'BINGO!' ? 
            'bg-green-500 text-white px-4 py-2 rounded hover:opacity-90' : 
            'bg-blue-500 text-white px-4 py-2 rounded hover:opacity-90';
    }
}

async function validateCard(cardId) {
    try {
        socket.emit('card_validated', { card_id: cardId });
        const response = await fetchJSON(`/card/api/check_card/${cardId}`);
        showSuccess(`Card ${cardId}: ${response.status}`);
    } catch (error) {
        showError(error.message);
    }
}


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

// Utility function for fetch requests
async function fetchJSON(url, options = {}) {
    try {
        const response = await fetch(url, options);
        const contentType = response.headers.get('content-type');

        if (!response.ok) {
            if (contentType && contentType.includes('application/json')) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            } else {
                throw new Error(`Unexpected response: ${await response.text()}`);
            }
        }

        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        } else {
            throw new Error('Expected JSON response, but got something else.');
        }
    } catch (err) {
        showError(`Error: ${err.message}`);
        console.error(`Error fetching ${url}:`, err);
        throw err;
    }
}

// Notification functions
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

// Load playlists and display them
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

// Load available devices and display them
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
            window.location.href = '/auth/login'; // Redirect to Spotify login
        } else {
            showError('Failed to load devices');
        }
    }
}

// Load played tracks and display them
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

// Load current Bingo cards
async function loadCards() {
    try {
        const data = await fetchJSON('/card/api/get_cards');
        const cardsContainer = document.getElementById('cardsContainer');
        cardsContainer.innerHTML = '';
        Object.entries(data.cards).forEach(([cardId, cardData]) => {
            cardsContainer.appendChild(createBingoCardDisplay(cardId, cardData));
        });
    } catch (error) {
        console.error('Error loading cards:', error);
    }
}

function initializeWebSocket() {
    socket = io.connect(window.location.origin);

    socket.on('connect_error', (error) => {
        console.error('WebSocket connection error:', error);
        updateConnectionStatus('Connection error');
    });

    socket.on('connect_timeout', () => {
        console.error('WebSocket connection timeout');
        updateConnectionStatus('Connection timeout');
    });

    socket.on('connect', () => {
        console.log('Connected to WebSocket');
        updateConnectionStatus('Connected');
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from WebSocket');
        updateConnectionStatus('Disconnected');
    });

    socket.on('game_state', (state) => {
        console.log('Received game state:', state);
        updateGameState(state);
    });

    socket.on('new_track', (trackData) => {
        console.log('New track played:', trackData);
        showSuccess(`Now playing: ${trackData.artist} - ${trackData.name}`);
        loadPlayedTracks();
        loadCards();
    });

    socket.on('bingo_winner', (data) => {
        console.log('Bingo winner:', data);
        showSuccess(`BINGO! Card ${data.card_id} has won!`);
        loadCards();
    });

    socket.on('error', (error) => {
        console.error('WebSocket error:', error);
        showError(error.message);
    });

    socket.on('card_status_update', (data) => {
        const { card_id, status, matches } = data;
        showSuccess(`Card ${card_id} status updated: ${status}`);
        loadCards();
    });
}

function updateConnectionStatus(status) {
    const statusEl = document.getElementById('connectionStatus');
    if (statusEl) {
        statusEl.textContent = `Connection: ${status}`;
        statusEl.className = status === 'Connected' ? 'text-green-600' : 'text-red-600';
    }
}

function updateGameState(state) {
    loadCards();
    loadPlayedTracks();
}

// Helper function to create a bingo card display
function createBingoCardDisplay(cardId, cardData) {
    const div = document.createElement('div');
    div.className = 'card-container border rounded-lg p-4 mb-4 flex justify-between items-center';
    div.setAttribute('data-card-id', cardId);
    div._cardData = cardData;  // Store card data for modal use

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

async function validateCard(cardId) {
    try {
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

// Initialize event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initialize WebSocket
    initializeWebSocket();

    // Load initial data
    Promise.all([
        loadPlaylists(),
        loadDevices(),
        loadPlayedTracks(),
        loadCards()
    ]).catch(error => console.error('Error during initialization:', error));

    // Add Playlist button
    document.getElementById('btnAddPlaylist').addEventListener('click', async () => {
        const playlistId = document.getElementById('newPlaylistID').value.trim();
        const isDefault = document.getElementById('newPlaylistDefault').checked;
        const msgEl = document.getElementById('addPlaylistMsg');

        if (!playlistId) {
            msgEl.textContent = 'Please enter a playlist ID';
            return;
        }

        try {
            const res = await fetchJSON('/playlist/api/add_playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ playlist_id: playlistId, is_default: isDefault })
            });
            showSuccess('Playlist added successfully');
            await loadPlaylists();
        } catch (error) {
            msgEl.textContent = error.message;
        }
    });

    // Load Playlist button
    document.getElementById('btnLoadPlaylist').addEventListener('click', async () => {
        const playlistSelect = document.getElementById('playlistSelect');
        const msgEl = document.getElementById('playlistMsg');

        if (!playlistSelect.value) {
            msgEl.textContent = 'Please select a playlist';
            return;
        }

        try {
            const res = await fetchJSON('/playlist/api/load_playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ playlist_id: playlistSelect.value })
            });
            showSuccess(res.message);
            msgEl.textContent = '';
        } catch (error) {
            msgEl.textContent = error.message;
        }
    });

    // Device selection
    document.getElementById('btnRefreshDevices').addEventListener('click', () => {
        loadDevices().catch(error => {
            showError('Failed to refresh devices');
        });
    });

    document.getElementById('btnSelectDevice').addEventListener('click', async () => {
        const deviceId = document.getElementById('deviceSelect').value;
        const msgEl = document.getElementById('deviceMsg');

        if (!deviceId) {
            msgEl.textContent = 'Please select a device';
            return;
        }

        try {
            const res = await fetchJSON('/device/api/select_device', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: deviceId })
            });
            showSuccess('Device selected successfully');
            msgEl.textContent = '';
        } catch (error) {
            msgEl.textContent = error.message;
        }
    });

    // Generate Cards button
    document.getElementById('btnGenerateCards').addEventListener('click', async () => {
        const numCards = document.getElementById('numCardsInput').value || 16;
        try {
            const res = await fetchJSON('/card/api/generate_cards', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ num_cards: numCards })
            });
            showSuccess(res.message);
            await loadCards();
        } catch (error) {
            showError(error.message);
        }
    });

    const downloadPdfButton = document.getElementById('btnDownloadPdf');
        if (downloadPdfButton) {
            downloadPdfButton.addEventListener('click', async () => {
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
            });
        }

    // Play button
    document.getElementById('btnPlay').addEventListener('click', async () => {
        const msgEl = document.getElementById('playbackMsg');
        msgEl.textContent = '';

        try {
            const res = await fetchJSON('/playback/api/play', {
                method: 'POST'
            });
            showSuccess(`Playing: ${res.track.artist} - ${res.track.name}`);
            await loadPlayedTracks();
            await loadCards();
        } catch (error) {
            msgEl.textContent = error.message;
        }
    });

    // Pause button
    document.getElementById('btnPause').addEventListener('click', async () => {
        const msgEl = document.getElementById('playbackMsg');
        msgEl.textContent = '';

        try {
            const res = await fetchJSON('/playback/api/pause', {
                method: 'POST'
            });
            showSuccess('Playback paused');
        }         catch (error) {
            msgEl.textContent = error.message;
        }
    });

    // New Round button
    document.getElementById('btnNewRound').addEventListener('click', async () => {
        const msgEl = document.getElementById('playbackMsg');
        msgEl.textContent = '';

        try {
            const res = await fetchJSON('/game/api/new_round', {
                method: 'POST'
            });
            showSuccess('New round started');
            document.getElementById('playedTracksList').innerHTML = '';
            await loadCards();
        } catch (error) {
            msgEl.textContent = error.message;
        }
    });

    // Add keyboard shortcuts
    document.addEventListener('keydown', (event) => {
        if (event.target.tagName === 'INPUT') return; // Don't trigger if typing in an input

        switch(event.key.toLowerCase()) {
            case ' ':  // Spacebar
                event.preventDefault();
                document.getElementById('btnPlay').click();
                break;
            case 'p':
                event.preventDefault();
                document.getElementById('btnPause').click();
                break;
            case 'r':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    document.getElementById('btnNewRound').click();
                }
                break;
            case 'd':
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault();
                    document.getElementById('btnRefreshDevices').click();
                }
                break;
        }
    });
});

