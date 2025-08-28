/**
 * State Manager Module
 *
 * Centralized frontend state management for the Musical Bingo application.
 * Manages application state, caching, and synchronization between components.
 */

class StateManager {
    constructor() {
        this.state = {
            // Game state
            activeGameId: null,
            games: new Map(),
            gameStats: null,
            
            // Player state
            user: null,
            devices: [],
            selectedDevice: null,
            
            // Playlist state
            playlists: [],
            selectedPlaylist: null,
            playedTracks: [],
            
            // Card state
            cards: new Map(),
            cardStatuses: new Map(),
            
            // UI state
            isConnected: false,
            isLoading: false,
            loadingOperations: new Set(),
            errors: [],
            notifications: [],
            
            // Connection state
            lastUpdate: null,
            updateCount: 0,
            errorCount: 0,
            lastErrorTime: null
        };
        
        // RACE CONDITION FIX: Add atomic state update protection
        this.updateQueue = [];
        this.isProcessingUpdates = false;
        this.updateLock = false;
        
        this.subscribers = new Map();
        this.cache = new Map();
        this.cacheExpiry = new Map();
        this.defaultCacheTTL = appConfig.getTiming('stateCacheTTL'); // CONFIGURATION FIX: Use centralized timing
        
        this.setupStatePersistence();
    }

    // === STATE MANAGEMENT ===

    /**
     * Get current state or specific state path
     * @param {string} path - Dot-notation path to state property (optional)
     * @returns {any} - State value
     */
    getState(path = null) {
        if (!path) {
            return { ...this.state };
        }
        
        return this.getNestedValue(this.state, path);
    }

    /**
     * Update state at specific path
     * @param {string} path - Dot-notation path to state property
     * @param {any} value - New value
     * @param {boolean} notify - Whether to notify subscribers
     */
    setState(path, value, notify = true) {
        return this.queueStateUpdate({ type: 'single', path, value, notify });
    }

    /**
     * Update multiple state paths atomically
     * @param {Object} updates - Object with path: value pairs
     * @param {boolean} notify - Whether to notify subscribers
     */
    updateState(updates, notify = true) {
        return this.queueStateUpdate({ type: 'multiple', updates, notify });
    }

    /**
     * Queue state update for atomic processing
     * RACE CONDITION FIX: Ensures state updates are processed sequentially
     * @param {Object} updateRequest - Update request object
     * @returns {Promise} - Resolves when update is complete
     */
    async queueStateUpdate(updateRequest) {
        return new Promise((resolve, reject) => {
            // PERFORMANCE FIX: Add operation ID tracking and timeout protection
            const operationId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            const timestamp = Date.now();
            
            const enhancedRequest = { 
                ...updateRequest, 
                resolve, 
                reject, 
                operationId,
                timestamp
            };
            
            this.updateQueue.push(enhancedRequest);
            
            // Timeout protection to prevent hanging operations
            setTimeout(() => {
                const requestIndex = this.updateQueue.findIndex(req => req.operationId === operationId);
                if (requestIndex !== -1) {
                    this.updateQueue.splice(requestIndex, 1);
                    reject(new Error(`State update timeout for operation ${operationId}`));
                }
            }, 5000);
            
            this.processUpdateQueue();
        });
    }

    /**
     * Process queued state updates atomically
     * RACE CONDITION FIX: Prevents concurrent state modifications
     */
    async processUpdateQueue() {
        if (this.isProcessingUpdates || this.updateQueue.length === 0) {
            return;
        }

        this.isProcessingUpdates = true;

        while (this.updateQueue.length > 0) {
            const updateRequest = this.updateQueue.shift();
            
            try {
                if (updateRequest.type === 'single') {
                    this.performSingleStateUpdate(
                        updateRequest.path, 
                        updateRequest.value, 
                        updateRequest.notify
                    );
                } else if (updateRequest.type === 'multiple') {
                    this.performMultipleStateUpdates(
                        updateRequest.updates, 
                        updateRequest.notify
                    );
                }
                
                // PERFORMANCE FIX: Proper success handling with operation tracking
                if (updateRequest.resolve) {
                    updateRequest.resolve({
                        success: true,
                        operationId: updateRequest.operationId,
                        timestamp: updateRequest.timestamp,
                        processingTime: Date.now() - updateRequest.timestamp
                    });
                }
            } catch (error) {
                console.error(`Error processing state update (${updateRequest.operationId}):`, error);
                
                // PERFORMANCE FIX: Proper error handling with reject
                if (updateRequest.reject) {
                    updateRequest.reject(new Error(`State update failed: ${error.message}`));
                } else if (updateRequest.resolve) {
                    // Fallback for legacy compatibility
                    updateRequest.resolve({
                        success: false,
                        error: error.message,
                        operationId: updateRequest.operationId
                    });
                }
            }
        }

        this.isProcessingUpdates = false;
    }

    /**
     * Perform single state update (internal method)
     * @param {string} path - State path
     * @param {any} value - New value
     * @param {boolean} notify - Whether to notify subscribers
     */
    performSingleStateUpdate(path, value, notify) {
        const oldValue = this.getNestedValue(this.state, path);
        this.setNestedValue(this.state, path, value);
        
        if (notify) {
            this.notifySubscribers(path, value, oldValue);
        }

        this.updateLastModified();
    }

    /**
     * Perform multiple state updates (internal method)
     * @param {Object} updates - Updates object
     * @param {boolean} notify - Whether to notify subscribers
     */
    performMultipleStateUpdates(updates, notify) {
        const oldValues = {};
        
        // Apply all updates atomically
        Object.entries(updates).forEach(([path, value]) => {
            oldValues[path] = this.getNestedValue(this.state, path);
            this.setNestedValue(this.state, path, value);
        });
        
        if (notify) {
            // Notify all affected subscribers
            Object.entries(updates).forEach(([path, value]) => {
                this.notifySubscribers(path, value, oldValues[path]);
            });
        }

        this.updateLastModified();
    }

    /**
     * Reset state to initial values
     */
    resetState() {
        const initialState = {
            activeGameId: null,
            games: new Map(),
            gameStats: null,
            user: null,
            devices: [],
            selectedDevice: null,
            playlists: [],
            selectedPlaylist: null,
            playedTracks: [],
            cards: new Map(),
            cardStatuses: new Map(),
            isConnected: false,
            isLoading: false,
            loadingOperations: new Set(),
            errors: [],
            notifications: [],
            lastUpdate: null,
            updateCount: 0,
            errorCount: 0,
            lastErrorTime: null
        };

        this.state = initialState;
        this.notifySubscribers('*', this.state, {});
        this.updateLastModified();
    }

    // === SUBSCRIPTION SYSTEM ===

    /**
     * Subscribe to state changes
     * @param {string} path - State path to watch (* for all)
     * @param {Function} callback - Callback function
     * @returns {Function} - Unsubscribe function
     */
    subscribe(path, callback) {
        if (!this.subscribers.has(path)) {
            this.subscribers.set(path, new Set());
        }
        
        this.subscribers.get(path).add(callback);
        
        // Return unsubscribe function
        return () => {
            const pathSubscribers = this.subscribers.get(path);
            if (pathSubscribers) {
                pathSubscribers.delete(callback);
                if (pathSubscribers.size === 0) {
                    this.subscribers.delete(path);
                }
            }
        };
    }

    /**
     * Notify subscribers of state changes
     * @param {string} path - Changed state path
     * @param {any} newValue - New value
     * @param {any} oldValue - Old value
     */
    notifySubscribers(path, newValue, oldValue) {
        // Notify specific path subscribers
        const pathSubscribers = this.subscribers.get(path);
        if (pathSubscribers) {
            pathSubscribers.forEach(callback => {
                try {
                    callback(newValue, oldValue, path);
                } catch (error) {
                    console.error('Error in state subscriber:', error);
                }
            });
        }

        // Notify wildcard subscribers
        const wildcardSubscribers = this.subscribers.get('*');
        if (wildcardSubscribers) {
            wildcardSubscribers.forEach(callback => {
                try {
                    callback(newValue, oldValue, path);
                } catch (error) {
                    console.error('Error in wildcard subscriber:', error);
                }
            });
        }
    }

    // === GAME STATE METHODS ===

    /**
     * Set active game
     * @param {string} gameId - Game ID
     */
    setActiveGame(gameId) {
        this.setState('activeGameId', gameId);
        window.activeGameId = gameId; // Backward compatibility
    }

    /**
     * Get active game
     * @returns {string|null} - Active game ID
     */
    getActiveGame() {
        return this.getState('activeGameId');
    }

    /**
     * Update game data
     * @param {string} gameId - Game ID
     * @param {Object} gameData - Game data
     */
    updateGame(gameId, gameData) {
        const games = this.getState('games');
        games.set(gameId, { ...games.get(gameId), ...gameData });
        this.setState('games', games);
    }

    /**
     * Get game data
     * @param {string} gameId - Game ID
     * @returns {Object|null} - Game data
     */
    getGame(gameId) {
        return this.getState('games').get(gameId) || null;
    }

    // === CARD STATE METHODS ===

    /**
     * Update cards data
     * @param {Object} cardsData - Cards data object
     */
    updateCards(cardsData) {
        const cardsMap = new Map();
        Object.entries(cardsData).forEach(([cardId, cardData]) => {
            cardsMap.set(cardId, cardData);
        });
        this.setState('cards', cardsMap);
    }

    /**
     * Update card status
     * @param {string} cardId - Card ID
     * @param {string} status - Card status
     * @param {Array} matches - Card matches
     */
    updateCardStatus(cardId, status, matches = []) {
        const cardStatuses = this.getState('cardStatuses');
        cardStatuses.set(cardId, { status, matches, updatedAt: Date.now() });
        this.setState('cardStatuses', cardStatuses);
    }

    /**
     * Get card status
     * @param {string} cardId - Card ID
     * @returns {Object|null} - Card status
     */
    getCardStatus(cardId) {
        return this.getState('cardStatuses').get(cardId) || null;
    }

    // === LOADING STATE METHODS ===

    /**
     * Set loading state for specific operation
     * @param {string} operation - Operation name
     * @param {boolean} isLoading - Loading state
     */
    setLoading(operation, isLoading) {
        const loadingOperations = this.getState('loadingOperations');
        
        if (isLoading) {
            loadingOperations.add(operation);
        } else {
            loadingOperations.delete(operation);
        }
        
        this.updateState({
            loadingOperations,
            isLoading: loadingOperations.size > 0
        });
    }

    /**
     * Check if specific operation is loading
     * @param {string} operation - Operation name
     * @returns {boolean} - Loading state
     */
    isOperationLoading(operation) {
        return this.getState('loadingOperations').has(operation);
    }

    /**
     * Check if any operation is loading
     * @returns {boolean} - Global loading state
     */
    isAnyLoading() {
        return this.getState('isLoading');
    }

    // === CACHING METHODS ===

    /**
     * Cache data with TTL
     * @param {string} key - Cache key
     * @param {any} data - Data to cache
     * @param {number} ttl - Time to live in milliseconds
     */
    setCache(key, data, ttl = this.defaultCacheTTL) {
        this.cache.set(key, data);
        this.cacheExpiry.set(key, Date.now() + ttl);
    }

    /**
     * Get cached data
     * @param {string} key - Cache key
     * @returns {any|null} - Cached data or null if expired/not found
     */
    getCache(key) {
        const expiryTime = this.cacheExpiry.get(key);
        
        if (!expiryTime || Date.now() > expiryTime) {
            // Cache expired or doesn't exist
            this.cache.delete(key);
            this.cacheExpiry.delete(key);
            return null;
        }
        
        return this.cache.get(key);
    }

    /**
     * Clear cache by key or all cache
     * @param {string} key - Cache key (optional, clears all if not provided)
     */
    clearCache(key = null) {
        if (key) {
            this.cache.delete(key);
            this.cacheExpiry.delete(key);
        } else {
            this.cache.clear();
            this.cacheExpiry.clear();
        }
    }

    // === ERROR AND NOTIFICATION METHODS ===

    /**
     * Add error to state
     * @param {string} message - Error message
     * @param {string} type - Error type
     * @param {Object} metadata - Additional error metadata
     */
    addError(message, type = 'error', metadata = {}) {
        const errors = [...this.getState('errors')];
        errors.push({
            id: Date.now() + Math.random(),
            message,
            type,
            timestamp: Date.now(),
            metadata
        });
        
        // Keep only last 10 errors
        if (errors.length > 10) {
            errors.splice(0, errors.length - 10);
        }
        
        this.setState('errors', errors);
    }

    /**
     * Clear errors
     */
    clearErrors() {
        this.setState('errors', []);
    }

    /**
     * Add notification
     * @param {string} message - Notification message
     * @param {string} type - Notification type
     * @param {number} duration - Auto-hide duration
     */
    addNotification(message, type = 'info', duration = appConfig.getTiming('notificationDuration')) {
        const notifications = [...this.getState('notifications')];
        const id = Date.now() + Math.random();
        
        notifications.push({
            id,
            message,
            type,
            timestamp: Date.now(),
            duration
        });
        
        this.setState('notifications', notifications);
        
        // Auto-remove notification
        if (duration > 0) {
            setTimeout(() => {
                this.removeNotification(id);
            }, duration);
        }
    }

    /**
     * Remove notification
     * @param {string} id - Notification ID
     */
    removeNotification(id) {
        const notifications = this.getState('notifications').filter(n => n.id !== id);
        this.setState('notifications', notifications);
    }

    // === UTILITY METHODS ===

    /**
     * Get nested object value by dot notation path
     * @param {Object} obj - Object to traverse
     * @param {string} path - Dot notation path
     * @returns {any} - Value at path
     */
    getNestedValue(obj, path) {
        return path.split('.').reduce((current, key) => {
            return current && current[key] !== undefined ? current[key] : undefined;
        }, obj);
    }

    /**
     * Set nested object value by dot notation path
     * @param {Object} obj - Object to modify
     * @param {string} path - Dot notation path
     * @param {any} value - Value to set
     */
    setNestedValue(obj, path, value) {
        const keys = path.split('.');
        const lastKey = keys.pop();
        
        const target = keys.reduce((current, key) => {
            if (!current[key] || typeof current[key] !== 'object') {
                current[key] = {};
            }
            return current[key];
        }, obj);
        
        target[lastKey] = value;
    }

    /**
     * Update last modified timestamp
     */
    updateLastModified() {
        this.state.lastUpdate = Date.now();
        this.state.updateCount++;
    }

    /**
     * Get state statistics
     * @returns {Object} - State statistics
     */
    getStateStats() {
        return {
            lastUpdate: this.getState('lastUpdate'),
            updateCount: this.getState('updateCount'),
            errorCount: this.getState('errorCount'),
            subscriberCount: Array.from(this.subscribers.values()).reduce((sum, set) => sum + set.size, 0),
            cacheSize: this.cache.size,
            stateSize: JSON.stringify(this.state).length
        };
    }

    // === PERSISTENCE ===

    /**
     * Setup state persistence to localStorage
     */
    setupStatePersistence() {
        // Load persisted state on initialization
        this.loadPersistedState();
        
        // Save state periodically
        setInterval(() => {
            this.saveStateToStorage();
        }, appConfig.getTiming('stateSaveInterval')); // CONFIGURATION FIX: Use centralized timing
        
        // Save state on page unload
        window.addEventListener('beforeunload', () => {
            this.saveStateToStorage();
        });
    }

    /**
     * Save important state to localStorage
     */
    saveStateToStorage() {
        try {
            const persistentState = {
                activeGameId: this.getState('activeGameId'),
                selectedDevice: this.getState('selectedDevice'),
                selectedPlaylist: this.getState('selectedPlaylist'),
                lastUpdate: this.getState('lastUpdate')
            };
            
            localStorage.setItem('musicBingoState', JSON.stringify(persistentState));
        } catch (error) {
            console.error('Failed to save state to localStorage:', error);
        }
    }

    /**
     * Load persisted state from localStorage
     */
    loadPersistedState() {
        try {
            const saved = localStorage.getItem('musicBingoState');
            if (saved) {
                const persistentState = JSON.parse(saved);
                
                // Only restore if saved recently (within 1 hour)
                const oneHour = appConfig.getTiming('stateExpiryTime'); // CONFIGURATION FIX: Use centralized timing
                if (persistentState.lastUpdate && (Date.now() - persistentState.lastUpdate) < oneHour) {
                    this.updateState({
                        activeGameId: persistentState.activeGameId,
                        selectedDevice: persistentState.selectedDevice,
                        selectedPlaylist: persistentState.selectedPlaylist
                    }, false);
                    
                    // Set global activeGameId for backward compatibility
                    if (persistentState.activeGameId) {
                        window.activeGameId = persistentState.activeGameId;
                    }
                }
            }
        } catch (error) {
            console.error('Failed to load persisted state:', error);
        }
    }
}

// Create global state manager instance
const stateManager = new StateManager();

// Export for use in other modules
window.stateManager = stateManager;

// Provide backward compatibility
window.activeGameId = stateManager.getActiveGame();
