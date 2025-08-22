/**
 * WebSocket Handler Module
 *
 * Manages real-time communication via Socket.IO for the Musical Bingo application.
 * Handles connection management, event handling, fallback polling, and error recovery.
 */

class WebSocketHandler {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.fallbackPollingInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.eventHandlers = new Map();
        this.connectionCallbacks = [];
        this.disconnectionCallbacks = [];
        
        this.config = {
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        };
    }

    /**
     * Initialize WebSocket connection
     * @param {Object} customConfig - Custom socket configuration
     */
    initialize(customConfig = {}) {
        if (typeof io === 'undefined') {
            console.error('Socket.io not loaded');
            this.handleConnectionError('Socket.io not available');
            return false;
        }

        // Merge custom config
        this.config = { ...this.config, ...customConfig };

        try {
            this.socket = io(window.location.origin, this.config);
            this.setupEventHandlers();
            return true;
        } catch (error) {
            this.handleConnectionError('Failed to initialize WebSocket', error);
            return false;
        }
    }

    /**
     * Setup core WebSocket event handlers
     */
    setupEventHandlers() {
        if (!this.socket) return;

        // Connection events
        this.socket.on('connect', () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.stopFallbackPolling();
            this.updateConnectionStatus(true);
            this.notifyConnectionCallbacks(true);
            
            // Request initial game state
            this.emit('request_game_state');
        });

        this.socket.on('disconnect', (reason) => {
            console.log('WebSocket disconnected:', reason);
            this.isConnected = false;
            this.updateConnectionStatus(false);
            this.notifyConnectionCallbacks(false);
            this.startFallbackPolling();
        });

        this.socket.on('connect_error', (error) => {
            console.error('WebSocket connection error:', error);
            this.handleConnectionError('Connection error', error);
        });

        this.socket.on('error', (error) => {
            console.error('WebSocket error:', error);
            this.handleSocketError(error);
        });

        // Game-specific events
        this.socket.on('game_state', (data) => {
            console.log('Received game state update:', data);
            this.handleGameStateUpdate(data);
        });

        this.socket.on('new_track', (data) => {
            console.log('Received new track event:', data);
            this.handleNewTrack(data);
        });

        this.socket.on('card_status_update', (data) => {
            console.log('Received card status update:', data);
            this.handleCardStatusUpdate(data);
        });
    }

    /**
     * Register event handler
     * @param {string} event - Event name
     * @param {Function} handler - Event handler function
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);

        // Also register with socket if connected
        if (this.socket) {
            this.socket.on(event, handler);
        }
    }

    /**
     * Remove event handler
     * @param {string} event - Event name
     * @param {Function} handler - Event handler function
     */
    off(event, handler) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }

        // Also remove from socket if connected
        if (this.socket) {
            this.socket.off(event, handler);
        }
    }

    /**
     * Emit event to server
     * @param {string} event - Event name
     * @param {any} data - Event data
     */
    emit(event, data = null) {
        if (this.socket && this.isConnected) {
            this.socket.emit(event, data);
        } else {
            console.warn('WebSocket not connected, cannot emit event:', event);
        }
    }

    /**
     * Add connection status change callback
     * @param {Function} callback - Callback function
     */
    onConnectionChange(callback) {
        this.connectionCallbacks.push(callback);
    }

    /**
     * Add disconnection callback
     * @param {Function} callback - Callback function
     */
    onDisconnection(callback) {
        this.disconnectionCallbacks.push(callback);
    }

    /**
     * Handle connection errors
     * @param {string} context - Error context
     * @param {Error} error - Error object
     */
    handleConnectionError(context, error = null) {
        const errorMessage = error ? error.message : context;
        
        if (window.errorHandler) {
            window.errorHandler.handleError(
                new Error(errorMessage), 
                'WebSocket Connection',
                { autoHide: true }
            );
        }

        this.startFallbackPolling();
    }

    /**
     * Handle socket errors
     * @param {Error} error - Error object
     */
    handleSocketError(error) {
        if (window.errorHandler) {
            window.errorHandler.handleError(error, 'WebSocket Error');
        }
    }

    /**
     * Update connection status in UI
     * @param {boolean} connected - Connection status
     */
    updateConnectionStatus(connected) {
        // Update WebSocket badge if function exists
        if (typeof window.updateWebsocketBadge === 'function') {
            window.updateWebsocketBadge(connected);
        }

        // Update connection status text if function exists
        if (typeof window.updateConnectionStatus === 'function') {
            window.updateConnectionStatus(connected ? 'Connected' : 'Disconnected');
        }
    }

    /**
     * Notify connection callbacks
     * @param {boolean} connected - Connection status
     */
    notifyConnectionCallbacks(connected) {
        this.connectionCallbacks.forEach(callback => {
            try {
                callback(connected);
            } catch (error) {
                console.error('Error in connection callback:', error);
            }
        });
    }

    /**
     * Start fallback polling when WebSocket is disconnected
     */
    startFallbackPolling() {
        if (this.fallbackPollingInterval) {
            return; // Already running
        }

        console.log('Starting fallback polling (every 30 seconds)');
        this.fallbackPollingInterval = setInterval(async () => {
            try {
                await this.performFallbackUpdate();
            } catch (error) {
                console.error('Error during fallback update:', error);
            }
        }, 30000); // 30 seconds
    }

    /**
     * Stop fallback polling
     */
    stopFallbackPolling() {
        if (this.fallbackPollingInterval) {
            clearInterval(this.fallbackPollingInterval);
            this.fallbackPollingInterval = null;
            console.log('Stopped fallback polling');
        }
    }

    /**
     * Perform fallback data update via HTTP requests
     */
    async performFallbackUpdate() {
        if (typeof window.forceUpdateAll === 'function') {
            await window.forceUpdateAll();
        } else {
            console.warn('forceUpdateAll function not available for fallback polling');
        }
    }

    /**
     * Handle game state updates from WebSocket
     * @param {Object} data - Game state data
     */
    handleGameStateUpdate(data) {
        // Update dashboard UI directly with received state
        if (typeof window.updateDashboardUIFromState === 'function') {
            window.updateDashboardUIFromState(data);
        }

        // Trigger custom event handlers
        this.triggerEventHandlers('game_state', data);
    }

    /**
     * Handle new track events
     * @param {Object} data - Track data
     */
    handleNewTrack(data) {
        // Handle new track event
        if (typeof window.handleNewTrack === 'function') {
            window.handleNewTrack(data);
        }

        // Trigger custom event handlers
        this.triggerEventHandlers('new_track', data);
    }

    /**
     * Handle card status updates
     * @param {Object} data - Card status data
     */
    handleCardStatusUpdate(data) {
        // Handle card status update
        if (typeof window.handleCardStatusUpdate === 'function') {
            window.handleCardStatusUpdate(data);
        }

        // Trigger custom event handlers
        this.triggerEventHandlers('card_status_update', data);
    }

    /**
     * Trigger registered event handlers
     * @param {string} event - Event name
     * @param {any} data - Event data
     */
    triggerEventHandlers(event, data) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error('Error in event handler for', event, ':', error);
                }
            });
        }
    }

    /**
     * Reconnect WebSocket manually
     * @returns {Promise<boolean>} - Success status
     */
    async reconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }

        this.isConnected = false;
        this.reconnectAttempts++;

        if (this.reconnectAttempts > this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            return false;
        }

        console.log('Attempting to reconnect WebSocket...');
        return this.initialize();
    }

    /**
     * Check WebSocket connection status
     * @returns {boolean} - Connection status
     */
    isConnectionHealthy() {
        return this.socket && this.isConnected && this.socket.connected;
    }

    /**
     * Get connection statistics
     * @returns {Object} - Connection statistics
     */
    getConnectionStats() {
        return {
            isConnected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            hasSocket: !!this.socket,
            socketConnected: this.socket ? this.socket.connected : false,
            fallbackPollingActive: !!this.fallbackPollingInterval
        };
    }

    /**
     * Cleanup WebSocket connection
     */
    cleanup() {
        this.stopFallbackPolling();
        
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }

        this.isConnected = false;
        this.eventHandlers.clear();
        this.connectionCallbacks = [];
        this.disconnectionCallbacks = [];
    }

    /**
     * Setup automatic reconnection with exponential backoff
     */
    setupAutoReconnect() {
        if (!this.socket) return;

        this.socket.on('disconnect', (reason) => {
            if (reason === 'io server disconnect') {
                // Server disconnected, manual reconnection needed
                this.socket.connect();
            }
            // For other disconnect reasons, socket.io will automatically try to reconnect
        });
    }

    /**
     * Force connection check and attempt recovery
     */
    async healthCheck() {
        if (!this.isConnectionHealthy()) {
            console.log('WebSocket health check failed, attempting recovery...');
            
            try {
                await this.reconnect();
                return true;
            } catch (error) {
                console.error('WebSocket recovery failed:', error);
                this.startFallbackPolling();
                return false;
            }
        }
        return true;
    }

    /**
     * Set up periodic health checks
     * @param {number} interval - Health check interval in milliseconds
     */
    setupHealthChecks(interval = 60000) { // 1 minute
        setInterval(() => {
            this.healthCheck();
        }, interval);
    }
}

// Create global WebSocket handler instance
const webSocketHandler = new WebSocketHandler();

// Export for use in other modules
window.webSocketHandler = webSocketHandler;

// Provide backward compatibility functions
window.initializeWebSocket = (config) => webSocketHandler.initialize(config);
