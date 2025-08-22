/**
 * Game Manager Module
 *
 * Manages game lifecycle, validation, and state for the Musical Bingo application.
 * Handles game creation, joining, validation, and coordination with API and state management.
 */

class GameManager {
    constructor() {
        this.validationCache = new Map();
        this.validationCacheTTL = 300000; // 5 minutes
        this.maxRetries = 3;
        this.retryDelay = 1000;
    }

    // === GAME LIFECYCLE METHODS ===

    /**
     * Get or create an active game
     * @param {boolean} allowCreate - Whether to create a new game if none exists
     * @returns {Promise<Object|null>} - Active game object or null
     */
    async getOrCreateActiveGame(allowCreate = true) {
        try {
            // Check if we have an active game in state
            let activeGameId = stateManager.getActiveGame();
            
            if (activeGameId) {
                try {
                    const existing = await apiClient.getGame(activeGameId);
                    if (existing) {
                        return existing;
                    }
                } catch (error) {
                    // Game no longer valid, reset active game
                    console.log('Active game no longer valid, resetting:', error.message);
                    stateManager.setActiveGame(null);
                    activeGameId = null;
                }
            }

            // Try to find an in-progress game
            const inProgressGames = await this.getGamesByStatus('in_progress');
            if (inProgressGames.length > 0) {
                const validGame = await this.findValidGameFromList(inProgressGames, { filter_status: 'in_progress' });
                if (validGame) {
                    stateManager.setActiveGame(validGame.id);
                    return validGame;
                }
            }

            // Try to find a waiting game with playlist data
            const waitingGames = await this.getGamesByStatus('waiting');
            if (waitingGames.length > 0) {
                console.log('[GameManager] Checking waiting games using bulk validation');
                const validGame = await this.findValidGameFromList(waitingGames, { filter_status: 'waiting' });
                if (validGame) {
                    stateManager.setActiveGame(validGame.id);
                    return validGame;
                }
            }

            // Create new game if allowed and we have playlists
            if (allowCreate) {
                try {
                    const newGame = await this.createGameWithAutoPlaylist();
                    if (newGame) {
                        stateManager.setActiveGame(newGame.id);
                        return newGame;
                    }
                } catch (error) {
                    console.warn('[GameManager] Could not create auto game:', error.message);
                    
                    if (window.errorHandler) {
                        window.errorHandler.handleError(error, 'Game Creation');
                    }
                }
            }

            return null;
        } catch (error) {
            console.error('[GameManager] Error in getOrCreateActiveGame:', error);
            
            if (window.errorHandler) {
                window.errorHandler.handleError(error, 'Game Manager');
            }
            
            throw error;
        }
    }

    /**
     * Create a new game with a specific playlist
     * @param {string} playlistId - Playlist ID
     * @param {string} name - Game name (optional)
     * @returns {Promise<Object>} - Created game object
     */
    async createGameWithPlaylist(playlistId, name = null) {
        if (!playlistId) {
            throw new Error('No playlist selected');
        }

        const gameName = name || 'Quick Game ' + new Date().toLocaleTimeString();
        
        try {
            // Create the game
            const game = await apiClient.createGame({
                name: gameName,
                playlist_id: playlistId
            });

            // Join as host player immediately
            await this.joinGame(game.id);
            
            // Update state
            stateManager.updateGame(game.id, game);
            stateManager.setActiveGame(game.id);

            console.log('[GameManager] Created and joined game:', game.id);
            return game;
        } catch (error) {
            console.error('[GameManager] Error creating game with playlist:', error);
            throw error;
        }
    }

    /**
     * Create a game with automatic playlist selection
     * @param {string} playlistIdOrNull - Specific playlist ID or null for auto-selection
     * @returns {Promise<Object>} - Created game object
     */
    async createGameWithAutoPlaylist(playlistIdOrNull = null) {
        let playlistId = playlistIdOrNull;

        if (!playlistId) {
            // Try to get user playlists first
            try {
                const playlists = await apiClient.getPlaylists();
                const playlistList = Array.isArray(playlists) ? playlists : (playlists.playlists || []);
                
                if (playlistList.length > 0) {
                    // Prefer database playlist ID, fallback to Spotify ID
                    playlistId = playlistList[0].id || playlistList[0].spotify_id;
                }
            } catch (error) {
                console.warn('[GameManager] Could not get user playlists:', error);
            }

            // If no user playlists, try suitable playlists
            if (!playlistId) {
                try {
                    const suitable = await apiClient.getSuitablePlaylists();
                    const suitableList = suitable.playlists || [];
                    
                    if (suitableList.length === 0) {
                        throw new Error('No suitable playlists found. Please add a playlist first.');
                    }
                    
                    playlistId = suitableList[0].id || suitableList[0].spotify_id;
                } catch (error) {
                    throw new Error('Could not find any playlists for game creation. Please add a playlist first.');
                }
            }
        }

        return await this.createGameWithPlaylist(playlistId);
    }

    /**
     * Start a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Start result
     */
    async startGame(gameId) {
        try {
            const result = await apiClient.startGame(gameId);
            
            // Update game state
            const game = stateManager.getGame(gameId);
            if (game) {
                stateManager.updateGame(gameId, Object.assign({}, game, { status: 'in_progress' }));
            }

            console.log('[GameManager] Started game:', gameId);
            return result;
        } catch (error) {
            console.error('[GameManager] Error starting game:', error);
            throw error;
        }
    }

    /**
     * Join a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object|null>} - Join result or null if already joined
     */
    async joinGame(gameId) {
        try {
            const result = await apiClient.joinGame(gameId);
            console.log('[GameManager] Joined game:', gameId);
            return result;
        } catch (error) {
            // If already joined or game not in waiting state, ignore error
            console.log('[GameManager] Could not join game (may already be joined):', error.message);
            return null;
        }
    }

    // === GAME VALIDATION METHODS ===

    /**
     * Validate games using bulk validation API
     * @param {Array} gameIds - Array of game IDs
     * @param {Object} options - Validation options
     * @returns {Promise<Object>} - Validation results
     */
    async validateGamesBatch(gameIds, options = {}) {
        if (!gameIds || gameIds.length === 0) {
            return { success: true, validation_results: [], summary: {} };
        }

        // Check cache first
        const cacheKey = this.createValidationCacheKey(gameIds, options);
        const cached = this.getValidationCache(cacheKey);
        if (cached) {
            console.log('[GameManager] Using cached validation results');
            return cached;
        }

        console.log('[GameManager] Starting bulk validation for ' + gameIds.length + ' games');

        try {
            stateManager.setLoading('gameValidation', true);
            
            const response = await apiClient.validateGamesBatch(gameIds, options);
            
            console.log('[GameManager] Bulk validation completed:', {
                total_requested: response.total_requested,
                total_processed: response.total_processed,
                processing_time_ms: response.processing_time_ms,
                summary: response.summary
            });

            // Cache the results
            this.setValidationCache(cacheKey, response);

            return response;
        } catch (error) {
            console.error('[GameManager] Bulk validation failed:', error);
            
            // Return fallback response
            return {
                success: false,
                validation_results: [],
                summary: { invalid: gameIds.length },
                error: error.message
            };
        } finally {
            stateManager.setLoading('gameValidation', false);
        }
    }

    /**
     * Check if a game exists
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Existence check result
     */
    async checkGameExists(gameId) {
        try {
            const result = await apiClient.checkGameExists(gameId);
            return result;
        } catch (error) {
            console.error('[GameManager] Game existence check failed for ' + gameId + ':', error);
            return { game_id: gameId, exists: false, accessible: false, status: null };
        }
    }

    /**
     * Find the first valid game from a list using bulk validation
     * @param {Array} games - Array of game objects or IDs
     * @param {Object} options - Validation options
     * @returns {Promise<Object|null>} - First valid game or null
     */
    async findValidGameFromList(games, options = {}) {
        if (!games || games.length === 0) {
            return null;
        }

        console.log('[GameManager] Finding valid game from ' + games.length + ' candidates');

        // Extract game IDs
        const gameIds = games.map(game => game.id || game);

        // Use bulk validation to check all games efficiently
        const validation = await this.validateGamesBatch(gameIds, {
            include_track_count: true,
            filter_status: options.filter_status
        });

        if (!validation.success || !validation.validation_results) {
            console.warn('[GameManager] Bulk validation failed, falling back to first game');
            return games[0];
        }

        // Find the first valid game
        for (const result of validation.validation_results) {
            if (result.status === 'valid' && result.can_generate_cards) {
                // Find the original game object
                const validGame = games.find(game => (game.id || game) === result.game_id);
                if (validGame) {
                    console.log('[GameManager] Found valid game: ' + result.game_id);
                    
                    // Update state with game info
                    if (typeof validGame === 'object') {
                        stateManager.updateGame(result.game_id, validGame);
                    }
                    
                    return validGame;
                }
            }
        }

        // If no valid games found, log the summary
        console.warn('[GameManager] No valid games found:', validation.summary);
        return null;
    }

    /**
     * Validate all cards using current game state
     * @returns {Promise<void>}
     */
    async validateAllCards() {
        console.log('[GameManager] Validating all cards using bulk API...');
        
        try {
            stateManager.setLoading('cardValidation', true);
            
            const cardsData = await apiClient.getCards();
            if (!cardsData.cards) {
                return;
            }

            const cardIds = Object.keys(cardsData.cards);
            if (cardIds.length === 0) {
                return;
            }

            console.log('[GameManager] Validating ' + cardIds.length + ' cards');

            // Update state with cards data
            stateManager.updateCards(cardsData.cards);

            // Note: Individual card validation is typically done via the card API
            // This method updates the UI with the current card states
            
        } catch (error) {
            console.error('[GameManager] Error validating cards:', error);
            
            if (window.errorHandler) {
                window.errorHandler.handleError(error, 'Card Validation');
            }
        } finally {
            stateManager.setLoading('cardValidation', false);
        }
    }

    // === VALIDATION CACHE METHODS ===

    /**
     * Create cache key for validation results
     * @param {Array} gameIds - Game IDs
     * @param {Object} options - Validation options
     * @returns {string} - Cache key
     */
    createValidationCacheKey(gameIds, options) {
        const sortedIds = gameIds.slice().sort();
        const optionsStr = JSON.stringify(options);
        return 'validation:' + sortedIds.join(',') + ':' + optionsStr;
    }

    /**
     * Get validation results from cache
     * @param {string} cacheKey - Cache key
     * @returns {Object|null} - Cached validation results or null
     */
    getValidationCache(cacheKey) {
        const cached = this.validationCache.get(cacheKey);
        if (!cached) {
            return null;
        }

        // Check if cache is expired
        if (Date.now() > cached.expiry) {
            this.validationCache.delete(cacheKey);
            return null;
        }

        return cached.data;
    }

    /**
     * Set validation results in cache
     * @param {string} cacheKey - Cache key
     * @param {Object} data - Validation results
     */
    setValidationCache(cacheKey, data) {
        this.validationCache.set(cacheKey, {
            data: data,
            expiry: Date.now() + this.validationCacheTTL
        });

        // Clean up old cache entries
        this.cleanupValidationCache();
    }

    /**
     * Clean up expired validation cache entries
     */
    cleanupValidationCache() {
        const now = Date.now();
        for (const entry of this.validationCache.entries()) {
            const key = entry[0];
            const value = entry[1];
            if (now > value.expiry) {
                this.validationCache.delete(key);
            }
        }
    }

    // === GAME QUERY METHODS ===

    /**
     * Get games by status
     * @param {string} status - Game status
     * @returns {Promise<Array>} - Array of games
     */
    async getGamesByStatus(status) {
        try {
            const games = await apiClient.getGames(status);
            return Array.isArray(games) ? games : [];
        } catch (error) {
            console.error('[GameManager] Error getting games by status ' + status + ':', error);
            return [];
        }
    }
}

// Create global game manager instance
const gameManager = new GameManager();

// Export for use in other modules
window.gameManager = gameManager;

// Provide backward compatibility functions
window.getOrCreateActiveGame = function(allowCreate) { return gameManager.getOrCreateActiveGame(allowCreate); };
window.createGameWithPlaylist = function(playlistId) { return gameManager.createGameWithPlaylist(playlistId); };
window.createGameWithAutoPlaylist = function(playlistId) { return gameManager.createGameWithAutoPlaylist(playlistId); };
window.startGame = function(gameId) { return gameManager.startGame(gameId); };
window.joinGame = function(gameId) { return gameManager.joinGame(gameId); };
window.validateGamesBatch = function(gameIds, options) { return gameManager.validateGamesBatch(gameIds, options); };
window.checkGameExists = function(gameId) { return gameManager.checkGameExists(gameId); };
window.findValidGameFromList = function(games, options) { return gameManager.findValidGameFromList(games, options); };
window.validateAllCards = function() { return gameManager.validateAllCards(); };
