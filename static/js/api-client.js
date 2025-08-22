/**
 * API Client Module
 * 
 * Centralized API communication layer for the Musical Bingo application.
 * Handles all HTTP requests, authentication, CSRF protection, error handling,
 * and response processing.
 */

class ApiClient {
    constructor() {
        this.baseUrl = '';
        this.defaultHeaders = {
            'Content-Type': 'application/json'
        };
    }

    /**
     * Read cookie by name
     * @param {string} name - Cookie name
     * @returns {string|null} - Cookie value or null
     */
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    /**
     * Core HTTP request method with authentication and error handling
     * @param {string} url - Request URL
     * @param {Object} options - Fetch options
     * @returns {Promise<any>} - JSON response
     */
    async makeRequest(url, options = {}) {
        const headers = {
            ...this.defaultHeaders,
            ...options.headers
        };

        // Session-based authentication - handled automatically via secure cookies
        // Add CSRF token for state-changing requests
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
            const csrf = this.getCookie('music_bingo_csrf');
            if (csrf) {
                headers['X-CSRF-Token'] = csrf;
            }
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
                credentials: 'include' // Include session cookies
            });

            if (!response.ok) {
                // Handle authentication errors
                if (response.status === 401 || response.status === 403) {
                    const authError = new Error('Session expired or not authenticated');
                    authError.isAuthError = true;
                    authError.status = response.status;
                    throw authError;
                }

                // Handle other HTTP errors
                let errorMessage = `HTTP error! status: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorData.message || errorMessage;
                } catch (e) {
                    // Could not parse error response as JSON
                }

                const error = new Error(errorMessage);
                error.status = response.status;
                throw error;
            }

            return await response.json();
        } catch (error) {
            console.error(`API request failed for ${url}:`, error);
            
            // Re-throw with additional context
            if (!error.isAuthError && !error.status) {
                error.isNetworkError = true;
            }
            throw error;
        }
    }

    // === GAME API METHODS ===

    /**
     * Get games with optional status filter
     * @param {string} status - Game status filter (optional)
     * @returns {Promise<Array>} - Array of games
     */
    async getGames(status = null) {
        const params = status ? '?status=' + encodeURIComponent(status) : '';
        return this.makeRequest('/game/api/games' + params);
    }

    /**
     * Get specific game by ID
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Game object
     */
    async getGame(gameId) {
        return this.makeRequest('/game/api/games/' + gameId);
    }

    /**
     * Create a new game
     * @param {Object} gameData - Game creation data
     * @returns {Promise<Object>} - Created game object
     */
    async createGame(gameData) {
        return this.makeRequest('/game/api/games', {
            method: 'POST',
            body: JSON.stringify(gameData)
        });
    }

    /**
     * Start a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Response object
     */
    async startGame(gameId) {
        return this.makeRequest('/game/api/games/' + gameId + '/start', {
            method: 'POST'
        });
    }

    /**
     * Join a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Response object
     */
    async joinGame(gameId) {
        return this.makeRequest('/game/api/games/' + gameId + '/join', {
            method: 'POST'
        });
    }

    /**
     * Check if game exists
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Existence check result
     */
    async checkGameExists(gameId) {
        return this.makeRequest('/game/api/games/' + gameId + '/exists');
    }

    /**
     * Bulk validate games
     * @param {Array} gameIds - Array of game IDs
     * @param {Object} options - Validation options
     * @returns {Promise<Object>} - Validation results
     */
    async validateGamesBatch(gameIds, options = {}) {
        return this.makeRequest('/game/api/games/validate-batch', {
            method: 'POST',
            body: JSON.stringify({
                game_ids: gameIds,
                include_track_count: options.include_track_count || true,
                filter_status: options.filter_status || null
            })
        });
    }

    // === PLAYLIST API METHODS ===

    /**
     * Get user playlists
     * @returns {Promise<Array>} - Array of playlists
     */
    async getPlaylists() {
        return this.makeRequest('/playlist/api/playlists');
    }

    /**
     * Add a playlist
     * @param {string} playlistId - Spotify playlist ID
     * @param {boolean} isDefault - Whether to set as default
     * @returns {Promise<Object>} - Response object
     */
    async addPlaylist(playlistId, isDefault = false) {
        return this.makeRequest('/playlist/api/add_playlist', {
            method: 'POST',
            body: JSON.stringify({ 
                playlist_id: playlistId, 
                is_default: isDefault 
            })
        });
    }

    /**
     * Get suitable playlists for games
     * @returns {Promise<Object>} - Suitable playlists response
     */
    async getSuitablePlaylists() {
        return this.makeRequest('/playlist/api/suitable-for-games');
    }

    // === CARD API METHODS ===

    /**
     * Get all cards
     * @returns {Promise<Object>} - Cards data
     */
    async getCards() {
        return this.makeRequest('/card/api/get_cards');
    }

    /**
     * Generate cards
     * @param {number} numCards - Number of cards to generate
     * @returns {Promise<Object>} - Generation result
     */
    async generateCards(numCards) {
        return this.makeRequest('/card/api/generate_cards', {
            method: 'POST',
            body: JSON.stringify({ num_cards: numCards })
        });
    }

    /**
     * Check specific card
     * @param {string} cardId - Card ID
     * @returns {Promise<Object>} - Card check result
     */
    async checkCard(cardId) {
        return this.makeRequest('/card/api/check_card/' + cardId);
    }

    /**
     * Validate card position
     * @param {string} cardId - Card ID
     * @param {string} trackId - Track ID
     * @param {number} position - Position on card
     * @returns {Promise<Object>} - Validation result
     */
    async validateCardPosition(cardId, trackId, position) {
        return this.makeRequest('/card/api/validate_card', {
            method: 'POST',
            body: JSON.stringify({ 
                card_id: cardId, 
                track_id: trackId, 
                position: position 
            })
        });
    }

    // === DEVICE API METHODS ===

    /**
     * Get Spotify devices
     * @returns {Promise<Object>} - Devices data
     */
    async getDevices() {
        return this.makeRequest('/device/api/get_devices');
    }

    /**
     * Select Spotify device
     * @param {string} deviceId - Device ID
     * @returns {Promise<Object>} - Selection result
     */
    async selectDevice(deviceId) {
        return this.makeRequest('/device/api/select_device', {
            method: 'POST',
            body: JSON.stringify({ device_id: deviceId })
        });
    }

    // === PLAYBACK API METHODS ===

    /**
     * Start playback for a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Playback result
     */
    async playGame(gameId) {
        return this.makeRequest('/playback/api/games/' + gameId + '/play', {
            method: 'POST'
        });
    }

    /**
     * Pause playback for a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Pause result
     */
    async pauseGame(gameId) {
        return this.makeRequest('/playback/api/games/' + gameId + '/pause', {
            method: 'POST'
        });
    }

    /**
     * Get played tracks for a game
     * @param {string} gameId - Game ID
     * @returns {Promise<Object>} - Played tracks data
     */
    async getPlayedTracks(gameId) {
        return this.makeRequest('/playback/api/games/' + gameId + '/played-tracks');
    }

    // === DASHBOARD API METHODS ===

    /**
     * Get dashboard data
     * @returns {Promise<Object>} - Dashboard data
     */
    async getDashboardData() {
        return this.makeRequest('/dashboard/api/dashboard_data');
    }

    /**
     * Get dashboard statistics
     * @returns {Promise<Object>} - Dashboard stats
     */
    async getDashboardStats() {
        return this.makeRequest('/dashboard/api/dashboard_stats');
    }

    // === AUTH API METHODS ===

    /**
     * Logout user
     * @returns {Promise<Object>} - Logout result
     */
    async logout() {
        return this.makeRequest('/auth/logout', {
            method: 'POST'
        });
    }

    // === SOUND API METHODS ===

    /**
     * Get available sound files
     * @returns {Promise<Object>} - Sound files list
     */
    async getSounds() {
        return this.makeRequest('/sound/api/list_sounds');
    }
}

// Create global API client instance
const apiClient = new ApiClient();

// Export for use in other modules
window.apiClient = apiClient;
