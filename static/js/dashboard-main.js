/**
 * Dashboard Main Module
 *
 * Main coordinator for the Musical Bingo dashboard application.
 * Orchestrates all modules, manages initialization, and provides the main application logic.
 */

class DashboardApplication {
    constructor() {
        this.initialized = false;
        this.components = {
            apiClient: window.apiClient,
            errorHandler: window.errorHandler,
            webSocketHandler: window.webSocketHandler,
            stateManager: window.stateManager,
            gameManager: window.gameManager,
            uiComponents: window.uiComponents
        };
        this.eventListeners = [];
    }

    // === INITIALIZATION ===

    /**
     * Initialize the dashboard application
     */
    async initialize() {
        if (this.initialized) {
            console.warn('[Dashboard] Already initialized');
            return;
        }

        try {
            console.log('[Dashboard] Starting application initialization...');
            
            // Initialize components in order
            await this.initializeComponents();
            
            // Setup event listeners
            this.setupEventListeners();
            
            // Setup state subscriptions
            this.setupStateSubscriptions();
            
            // Load initial data
            await this.loadInitialData();
            
            // Validate dashboard state
            await this.validateInitialState();
            
            this.initialized = true;
            console.log('[Dashboard] Application initialization complete');
            
            // Trigger initialization complete event
            uiComponents.triggerCustomEvent('dashboardInitialized');
            
        } catch (error) {
            console.error('[Dashboard] Initialization failed:', error);
            errorHandler.handleError(error, 'Dashboard Initialization');
        }
    }

    /**
     * Initialize all components
     */
    async initializeComponents() {
        // Initialize WebSocket connection
        const socketInitialized = webSocketHandler.initialize();
        
        // If WebSocket fails, start fallback polling after delay
        if (!socketInitialized) {
            setTimeout(() => {
                if (!webSocketHandler.isConnectionHealthy()) {
                    this.startFallbackUpdates();
                }
            }, 5000);
        }

        // Setup periodic health checks
        webSocketHandler.setupHealthChecks(60000); // Every minute
        
        console.log('[Dashboard] Components initialized');
    }

    /**
     * Setup main event listeners
     */
    setupEventListeners() {
        // DOM event listeners
        this.addEventListeners();
        
        // WebSocket event subscriptions
        this.setupWebSocketListeners();
        
        // Keyboard shortcuts
        this.setupKeyboardShortcuts();
        
        console.log('[Dashboard] Event listeners setup complete');
    }

    /**
     * Add DOM event listeners
     */
    addEventListeners() {
        // Playlist management
        this.addEventListener('btnAddPlaylist', 'click', this.handleAddPlaylist.bind(this));
        this.addEventListener('btnLoadPlaylist', 'click', this.handleLoadPlaylist.bind(this));
        
        // Device management
        this.addEventListener('btnRefreshDevices', 'click', this.handleRefreshDevices.bind(this));
        this.addEventListener('btnSelectDevice', 'click', this.handleSelectDevice.bind(this));
        
        // Card management
        this.addEventListener('btnGenerateCards', 'click', this.handleGenerateCards.bind(this));
        this.addEventListener('btnDownloadPdf', 'click', this.handleDownloadPdf.bind(this));
        
        // Playback controls
        this.addEventListener('btnPlay', 'click', this.handlePlay.bind(this));
        this.addEventListener('btnPause', 'click', this.handlePause.bind(this));
        
        // Authentication
        this.addEventListener('btnLogout', 'click', this.handleLogout.bind(this));
        
        // Modal controls
        this.addEventListener('setupModal', 'click', this.handleModalBackdropClick.bind(this));
    }

    /**
     * Helper to add event listener with cleanup tracking
     */
    addEventListener(elementId, event, handler) {
        const element = document.getElementById(elementId);
        if (element) {
            element.addEventListener(event, handler);
            this.eventListeners.push({ element, event, handler });
        }
    }

    /**
     * Setup WebSocket event listeners
     */
    setupWebSocketListeners() {
        webSocketHandler.on('game_state', this.handleGameStateUpdate.bind(this));
        webSocketHandler.on('new_track', this.handleNewTrack.bind(this));
        webSocketHandler.on('card_status_update', this.handleCardStatusUpdate.bind(this));
        
        webSocketHandler.onConnectionChange((connected) => {
            uiComponents.updateWebsocketBadge(connected);
            if (connected) {
                this.onConnectionRestored();
            }
        });
    }

    /**
     * Setup state management subscriptions
     */
    setupStateSubscriptions() {
        // Subscribe to loading state changes
        stateManager.subscribe('isLoading', (isLoading) => {
            this.updateGlobalLoadingState(isLoading);
        });
        
        // Subscribe to active game changes
        stateManager.subscribe('activeGameId', (gameId) => {
            this.onActiveGameChanged(gameId);
        });
        
        // Subscribe to error state changes
        stateManager.subscribe('errors', (errors) => {
            this.handleStateErrors(errors);
        });
        
        // Subscribe to notifications
        stateManager.subscribe('notifications', (notifications) => {
            this.handleStateNotifications(notifications);
        });
    }

    /**
     * Setup keyboard shortcuts
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (event) => {
            // Ctrl/Cmd + Enter: Play/Pause
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault();
                this.togglePlayback();
            }
            
            // Ctrl/Cmd + G: Generate cards
            if ((event.ctrlKey || event.metaKey) && event.key === 'g') {
                event.preventDefault();
                this.handleGenerateCards();
            }
            
            // Ctrl/Cmd + R: Refresh data
            if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
                event.preventDefault();
                this.refreshAllData();
            }
        });
    }

    // === DATA LOADING ===

    /**
     * Load initial application data
     */
    async loadInitialData() {
        try {
            console.log('[Dashboard] Loading initial data...');
            
            stateManager.setLoading('initialLoad', true);
            
            // Load data in parallel
            const loadPromises = [
                this.loadPlaylists(),
                this.loadDevices(), 
                this.loadPlayedTracks(),
                this.loadCards(),
                this.updateGameStats(),
                this.updateDashboardData()
            ];
            
            await Promise.all(loadPromises);
            
            console.log('[Dashboard] Initial data load complete');
            
        } catch (error) {
            console.error('[Dashboard] Error loading initial data:', error);
            errorHandler.handleError(error, 'Initial Data Load');
        } finally {
            stateManager.setLoading('initialLoad', false);
        }
    }

    /**
     * Load playlists data
     */
    async loadPlaylists() {
        try {
            const data = await apiClient.getPlaylists();
            const playlistSelect = document.getElementById('playlistSelect');
            
            if (playlistSelect) {
                playlistSelect.innerHTML = '';
                
                // Support both legacy format and new list of Playlist objects
                const list = Array.isArray(data.playlists) ? data.playlists : (Array.isArray(data) ? data : []);
                
                list.forEach(playlist => {
                    const option = document.createElement('option');
                    option.value = playlist.id || playlist.spotify_id;
                    option.textContent = playlist.name || 'Unnamed Playlist';
                    playlistSelect.appendChild(option);
                });
                
                // Update state
                stateManager.setState('playlists', list);
            }
        } catch (error) {
            console.error('[Dashboard] Error loading playlists:', error);
            errorHandler.handleError(error, 'Playlist Loading');
        }
    }

    /**
     * Load devices data
     */
    async loadDevices() {
        try {
            const data = await apiClient.getDevices();
            const deviceSelect = document.getElementById('deviceSelect');
            
            if (deviceSelect && data.devices && Array.isArray(data.devices)) {
                deviceSelect.innerHTML = '';
                
                data.devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.id;
                    option.textContent = device.name + (device.is_active ? ' (Active)' : '');
                    deviceSelect.appendChild(option);
                });
                
                // Update state
                stateManager.setState('devices', data.devices);
                
                // Update Spotify badge based on active devices
                const hasActive = data.devices.some(d => d.is_active);
                uiComponents.updateSpotifyBadge(hasActive ? 'connected' : 'disconnected');
            }
        } catch (error) {
            console.error('[Dashboard] Error loading devices:', error);
            errorHandler.handleError(error, 'Device Loading');
            uiComponents.updateSpotifyBadge('disconnected');
        }
    }

    /**
     * Load played tracks data
     */
    async loadPlayedTracks() {
        const activeGameId = stateManager.getActiveGame();
        if (!activeGameId) {
            console.log('[Dashboard] No active game, skipping played tracks load');
            return;
        }

        try {
            const data = await apiClient.getPlayedTracks(activeGameId);
            
            // Update UI
            const playedTracksContainer = document.getElementById('playedTracksContainer');
            if (playedTracksContainer && data.played_tracks) {
                this.updatePlayedTracksDisplay(data.played_tracks);
            }
            
            // Update state
            stateManager.setState('playedTracks', data.played_tracks || []);
            
        } catch (error) {
            if (error.message.includes('404')) {
                console.warn('[Dashboard] Game not found or no playlist data. Resetting active game.');
                stateManager.setActiveGame(null);
            } else {
                console.error('[Dashboard] Error loading played tracks:', error);
                errorHandler.handleError(error, 'Played Tracks Loading');
            }
        }
    }

    /**
     * Load cards data
     */
    async loadCards() {
        try {
            console.log('[Dashboard] Loading cards...');
            const data = await apiClient.getCards();
            
            if (data.cards) {
                this.updateCardsDisplay(data.cards);
                stateManager.updateCards(data.cards);
            }
            
        } catch (error) {
            console.error('[Dashboard] Error loading cards:', error);
            errorHandler.handleError(error, 'Cards Loading');
        }
    }

    /**
     * Update dashboard data
     */
    async updateDashboardData() {
        try {
            const [dashboardData, stats] = await Promise.all([
                apiClient.getDashboardData(),
                apiClient.getDashboardStats()
            ]);
            
            console.log('[Dashboard] Received dashboard data:', dashboardData);
            console.log('[Dashboard] Received stats:', stats);
            
            // Update statistics display
            uiComponents.updateStatisticsDisplay(stats);
            
            // Update Spotify badge based on device presence
            const devices = await apiClient.getDevices().catch(() => ({ devices: [] }));
            const hasActive = Array.isArray(devices.devices) && devices.devices.some(d => d.is_active);
            uiComponents.updateSpotifyBadge(hasActive ? 'connected' : 'disconnected');
            
        } catch (error) {
            console.error('[Dashboard] Error updating dashboard data:', error);
            errorHandler.handleError(error, 'Dashboard Data Update');
        }
    }

    /**
     * Update game statistics
     */
    async updateGameStats() {
        try {
            const stats = await apiClient.getDashboardStats();
            stateManager.setState('gameStats', stats);
            uiComponents.updateStatisticsDisplay(stats);
            return stats;
        } catch (error) {
            console.error('[Dashboard] Error updating game stats:', error);
            errorHandler.handleError(error, 'Game Stats Update');
        }
    }

    /**
     * Validate initial dashboard state
     */
    async validateInitialState() {
        try {
            await gameManager.validateDashboardState();
        } catch (error) {
            console.error('[Dashboard] Error validating initial state:', error);
            errorHandler.handleError(error, 'Initial State Validation');
        }
    }

    // === EVENT HANDLERS ===

    /**
     * Handle add playlist
     */
    async handleAddPlaylist() {
        const playlistIdInput = document.getElementById('newPlaylistID');
        const isDefaultCheckbox = document.getElementById('newPlaylistDefault');
        const msgElement = document.getElementById('addPlaylistMsg');

        const playlistId = playlistIdInput?.value?.trim();
        const isDefault = isDefaultCheckbox?.checked || false;

        if (!playlistId) {
            if (msgElement) msgElement.textContent = 'Please enter a playlist ID';
            return;
        }

        try {
            stateManager.setLoading('addPlaylist', true);
            
            await apiClient.addPlaylist(playlistId, isDefault);
            uiComponents.showSuccess('Playlist added successfully');
            
            // Reload playlists
            await this.loadPlaylists();
            
            // Clear form
            if (playlistIdInput) playlistIdInput.value = '';
            if (isDefaultCheckbox) isDefaultCheckbox.checked = false;
            if (msgElement) msgElement.textContent = '';
            
        } catch (error) {
            console.error('[Dashboard] Error adding playlist:', error);
            if (msgElement) msgElement.textContent = error.message;
            errorHandler.handleError(error, 'Add Playlist');
        } finally {
            stateManager.setLoading('addPlaylist', false);
        }
    }

    /**
     * Handle load playlist
     */
    async handleLoadPlaylist() {
        const playlistSelect = document.getElementById('playlistSelect');
        const msgElement = document.getElementById('playlistMsg');

        const playlistId = playlistSelect?.value;
        if (!playlistId) {
            if (msgElement) msgElement.textContent = 'Please select a playlist';
            return;
        }

        try {
            stateManager.setLoading('loadPlaylist', true);
            
            // Create a new game with the selected playlist and start it
            const game = await gameManager.createGameWithPlaylist(playlistId);
            await gameManager.startGame(game.id);
            
            uiComponents.showSuccess('Playlist loaded into a new game and started');
            if (msgElement) msgElement.textContent = '';
            
            // Refresh all data
            await this.refreshAllData();
            
        } catch (error) {
            console.error('[Dashboard] Error loading playlist:', error);
            if (msgElement) msgElement.textContent = error.message;
            errorHandler.handleError(error, 'Load Playlist');
        } finally {
            stateManager.setLoading('loadPlaylist', false);
        }
    }

    /**
     * Handle refresh devices
     */
    async handleRefreshDevices() {
        try {
            stateManager.setLoading('refreshDevices', true);
            await this.loadDevices();
            uiComponents.showSuccess('Devices refreshed');
        } catch (error) {
            errorHandler.handleError(error, 'Refresh Devices');
        } finally {
            stateManager.setLoading('refreshDevices', false);
        }
    }

    /**
     * Handle select device
     */
    async handleSelectDevice() {
        const deviceSelect = document.getElementById('deviceSelect');
        const msgElement = document.getElementById('deviceMsg');

        const deviceId = deviceSelect?.value;
        if (!deviceId) {
            if (msgElement) msgElement.textContent = 'Please select a device';
            return;
        }

        try {
            stateManager.setLoading('selectDevice', true);
            
            await apiClient.selectDevice(deviceId);
            uiComponents.showSuccess('Device selected successfully');
            
            if (msgElement) msgElement.textContent = '';
            stateManager.setState('selectedDevice', deviceId);
            
        } catch (error) {
            console.error('[Dashboard] Error selecting device:', error);
            if (msgElement) msgElement.textContent = error.message;
            errorHandler.handleError(error, 'Select Device');
        } finally {
            stateManager.setLoading('selectDevice', false);
        }
    }

    /**
     * Handle generate cards
     */
    async handleGenerateCards() {
        const numCardsInput = document.getElementById('numCardsInput');
        const numCards = parseInt(numCardsInput?.value) || 16;

        try {
            stateManager.setLoading('generateCards', true);
            
            const result = await apiClient.generateCards(numCards);
            uiComponents.showSuccess(result.message || 'Cards generated successfully');
            
            // Reload cards
            await this.loadCards();
            
        } catch (error) {
            console.error('[Dashboard] Error generating cards:', error);
            errorHandler.handleError(error, 'Generate Cards');
        } finally {
            stateManager.setLoading('generateCards', false);
        }
    }

    /**
     * Handle download PDF
     */
    async handleDownloadPdf() {
        try {
            // This would typically trigger a download
            window.open('/card/api/download_cards_pdf', '_blank');
            uiComponents.showSuccess('PDF download started');
        } catch (error) {
            console.error('[Dashboard] Error downloading PDF:', error);
            errorHandler.handleError(error, 'PDF Download');
        }
    }

    /**
     * Handle play button
     */
    async handlePlay() {
        try {
            stateManager.setLoading('playback', true);
            
            const game = await gameManager.getOrCreateActiveGame(true);
            if (!game) {
                throw new Error('No active game available');
            }

            const result = await apiClient.playGame(game.id);
            uiComponents.showSuccess('Playing: ' + result.track.artist + ' - ' + result.track.name);
            
            // Refresh data
            await Promise.all([
                this.loadPlayedTracks(),
                this.loadCards()
            ]);
            
        } catch (error) {
            console.error('[Dashboard] Error playing:', error);
            errorHandler.handleError(error, 'Playback');
        } finally {
            stateManager.setLoading('playback', false);
        }
    }

    /**
     * Handle pause button
     */
    async handlePause() {
        try {
            stateManager.setLoading('playback', true);
            
            const game = await gameManager.getOrCreateActiveGame(false);
            if (!game) {
                throw new Error('No active game');
            }

            await apiClient.pauseGame(game.id);
            uiComponents.showSuccess('Playback paused');
            
        } catch (error) {
            console.error('[Dashboard] Error pausing:', error);
            errorHandler.handleError(error, 'Playback');
        } finally {
            stateManager.setLoading('playback', false);
        }
    }

    /**
     * Handle logout
     */
    async handleLogout() {
        try {
            await apiClient.logout();
            window.location.href = '/auth/login/page';
        } catch (error) {
            // Even if logout fails, redirect to login
            window.location.href = '/auth/login/page';
        }
    }

    /**
     * Handle modal backdrop click
     */
    handleModalBackdropClick(event) {
        if (event.target === event.currentTarget) {
            uiComponents.hideModal('setupModal');
        }
    }

    /**
     * Toggle playback (play/pause)
     */
    async togglePlayback() {
        // This would need more sophisticated logic to determine current state
        // For now, default to play
        await this.handlePlay();
    }

    // === WEBSOCKET EVENT HANDLERS ===

    /**
     * Handle game state updates from WebSocket
     */
    handleGameStateUpdate(data) {
        console.log('[Dashboard] Game state update received:', data);
        
        if (data) {
            // Update UI elements directly
            uiComponents.updateElement('numTracks', data.unplayed_tracks ? data.unplayed_tracks.length : 0);
            uiComponents.updateElement('playedTracks', data.played_tracks ? data.played_tracks.length : 0);
            uiComponents.updateElement('totalCards', data.cards ? Object.keys(data.cards).length : 0);
        }
    }

    /**
     * Handle new track events
     */
    handleNewTrack(data) {
        console.log('[Dashboard] New track event received:', data);
        
        // Update played tracks display
        if (data.track) {
            this.refreshPlayedTracks();
        }
    }

    /**
     * Handle card status updates
     */
    handleCardStatusUpdate(data) {
        console.log('[Dashboard] Card status update received:', data);
        
        if (data.card_id) {
            uiComponents.updateCardDisplay(data.card_id, data.status, data.matches);
            stateManager.updateCardStatus(data.card_id, data.status, data.matches);
        }
    }

    /**
     * Handle connection restored
     */
    onConnectionRestored() {
        console.log('[Dashboard] Connection restored, refreshing data...');
        this.refreshAllData();
    }

    // === STATE HANDLERS ===

    /**
     * Update global loading state
     */
    updateGlobalLoadingState(isLoading) {
        const loadingIndicator = document.getElementById('globalLoadingIndicator');
        if (loadingIndicator) {
            loadingIndicator.style.display = isLoading ? 'block' : 'none';
        }
    }

    /**
     * Handle active game changes
     */
    onActiveGameChanged(gameId) {
        console.log('[Dashboard] Active game changed to:', gameId);
        
        // Update backward compatibility
        window.activeGameId = gameId;
        
        // Refresh game-related data
        if (gameId) {
            this.refreshGameRelatedData();
        }
    }

    /**
     * Handle state errors
     */
    handleStateErrors(errors) {
        // State errors are handled by the error system, just log for debugging
        if (errors.length > 0) {
            console.log('[Dashboard] State errors:', errors);
        }
    }

    /**
     * Handle state notifications
     */
    handleStateNotifications(notifications) {
        // State notifications are handled by the notification system
        if (notifications.length > 0) {
            console.log('[Dashboard] State notifications:', notifications);
        }
    }

    // === DATA REFRESH METHODS ===

    /**
     * Refresh all dashboard data
     */
    async refreshAllData() {
        try {
            console.log('[Dashboard] Refreshing all data...');
            
            const refreshPromises = [
                this.loadPlaylists(),
                this.loadDevices(),
                this.loadPlayedTracks(), 
                this.loadCards(),
                this.updateGameStats(),
                this.updateDashboardData()
            ];
            
            await Promise.all(refreshPromises);
            console.log('[Dashboard] All data refreshed');
            
        } catch (error) {
            console.error('[Dashboard] Error refreshing data:', error);
            errorHandler.handleError(error, 'Data Refresh');
        }
    }

    /**
     * Refresh game-related data
     */
    async refreshGameRelatedData() {
        try {
            await Promise.all([
                this.loadPlayedTracks(),
                this.loadCards(),
                this.updateGameStats()
            ]);
        } catch (error) {
            console.error('[Dashboard] Error refreshing game data:', error);
        }
    }

    /**
     * Refresh played tracks
     */
    async refreshPlayedTracks() {
        try {
            await this.loadPlayedTracks();
        } catch (error) {
            console.error('[Dashboard] Error refreshing played tracks:', error);
        }
    }

    // === UI UPDATE METHODS ===

    /**
     * Update played tracks display
     */
    updatePlayedTracksDisplay(playedTracks) {
        const container = document.getElementById('playedTracksContainer');
        if (!container || !playedTracks) return;

        if (playedTracks.length === 0) {
            container.innerHTML = '<div class="text-center text-gray-500 py-4">No tracks played yet</div>';
            return;
        }

        const tracksHTML = playedTracks.map((track, index) => 
            '<div class="flex items-center p-2 bg-white rounded border mb-2">' +
            '<span class="text-sm text-gray-600 mr-3">' + (index + 1) + '.</span>' +
            '<div class="flex-1">' +
            '<div class="font-medium">' + (track.name || 'Unknown Track') + '</div>' +
            '<div class="text-sm text-gray-600">' + (track.artist || 'Unknown Artist') + '</div>' +
            '</div>' +
            '</div>'
        ).join('');

        container.innerHTML = tracksHTML;
    }

    /**
     * Update cards display
     */
    updateCardsDisplay(cards) {
        const container = document.getElementById('cardsContainer');
        if (!container || !cards) return;

        const cardIds = Object.keys(cards);
        if (cardIds.length === 0) {
            container.innerHTML = '<div class="text-center text-gray-500 py-8">No cards generated yet. Click "Generate Cards" to create some!</div>';
            return;
        }

        const cardsHTML = cardIds.map(cardId => {
            const card = cards[cardId];
            const status = stateManager.getCardStatus(cardId);
            
            return '<div id="card-' + cardId + '" class="card-item bg-white rounded-lg border p-4 mb-4">' +
                   '<div class="flex justify-between items-start mb-3">' +
                   '<h3 class="font-semibold">Card ' + cardId + '</h3>' +
                   '<span class="card-status px-2 py-1 rounded text-xs">' + (status?.status || 'Ready') + '</span>' +
                   '</div>' +
                   '<div class="card-grid grid grid-cols-5 gap-1 text-xs">' +
                   this.renderCardGrid(card) +
                   '</div>' +
                   '<div class="mt-3 text-sm text-gray-600">' +
                   '<span class="card-matches">' + (status?.matches?.length || 0) + ' matches</span>' +
                   '</div>' +
                   '</div>';
        }).join('');

        container.innerHTML = cardsHTML;
    }

    /**
     * Render card grid
     */
    renderCardGrid(card) {
        if (!card || !card.grid) return '';
        
        return card.grid.map((row, rowIndex) =>
            row.map((track, colIndex) => {
                const position = rowIndex * 5 + colIndex;
                return '<div class="card-cell p-2 bg-gray-50 rounded text-center" data-position="' + position + '">' +
                       '<div class="font-medium text-xs">' + (track?.name || 'Empty') + '</div>' +
                       '<div class="text-xs text-gray-500 mt-1">' + (track?.artist || '') + '</div>' +
                       '</div>';
            }).join('')
        ).join('');
    }

    // === FALLBACK UPDATES ===

    /**
     * Start fallback polling updates
     */
    startFallbackUpdates() {
        console.log('[Dashboard] Starting fallback update polling');
        
        setInterval(async () => {
            try {
                await this.refreshAllData();
            } catch (error) {
                console.error('[Dashboard] Error during fallback update:', error);
            }
        }, 30000); // Every 30 seconds
    }

    // === CLEANUP ===

    /**
     * Cleanup application resources
     */
    cleanup() {
        // Remove event listeners
        this.eventListeners.forEach(({ element, event, handler }) => {
            element.removeEventListener(event, handler);
        });
        this.eventListeners = [];

        // Cleanup components
        if (webSocketHandler) {
            webSocketHandler.cleanup();
        }

        if (uiComponents) {
            uiComponents.reset();
        }

        this.initialized = false;
        console.log('[Dashboard] Application cleanup complete');
    }

    // === UTILITY METHODS ===

    /**
     * Get application statistics
     */
    getStats() {
        return {
            initialized: this.initialized,
            activeGameId: stateManager.getActiveGame(),
            connectionHealthy: webSocketHandler.isConnectionHealthy(),
            loadingOperations: stateManager.getState('loadingOperations').size,
            ...webSocketHandler.getConnectionStats(),
            ...uiComponents.getStats(),
            ...gameManager.getStats()
        };
    }
}

// === INITIALIZATION ===

// Create global dashboard application instance
const dashboardApp = new DashboardApplication();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('[Dashboard] DOM loaded, initializing application...');
    dashboardApp.initialize();
});

// Export for use in other modules
window.dashboardApp = dashboardApp;

// Provide backward compatibility
window.forceUpdateAll = function() { return dashboardApp.refreshAllData(); };
window.updateDashboardUIFromState = function(state) { dashboardApp.handleGameStateUpdate(state); };
window.handleNewTrack = function(data) { dashboardApp.handleNewTrack(data); };
window.handleCardStatusUpdate = function(data) { dashboardApp.handleCardStatusUpdate(data); };
window.initializeEventListeners = function() { console.log('[Dashboard] initializeEventListeners called - now handled in dashboardApp.initialize()'); };
