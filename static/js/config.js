/**
 * Configuration Module
 * 
 * CONFIGURATION FIX: Centralized configuration to replace hardcoded values
 * Provides a single source of truth for application constants and settings.
 */

class AppConfig {
    constructor() {
        // CONFIGURATION FIX: Centralized timing configurations
        this.timing = {
            // WebSocket configurations
            websocketReconnectDelay: 1000,              // 1 second
            websocketReconnectDelayMax: 5000,           // 5 seconds
            websocketFallbackPollingInterval: 30000,    // 30 seconds
            websocketHealthCheckInterval: 60000,        // 1 minute
            
            // UI timings
            notificationDuration: 5000,                 // 5 seconds
            errorCooldown: 60000,                       // 1 minute
            modalTransitionDelay: 100,                  // 100ms
            uiUpdateDelay: 5000,                        // 5 seconds for fallback
            
            // State persistence
            stateSaveInterval: 30000,                   // 30 seconds
            stateCacheTTL: 300000,                      // 5 minutes
            stateExpiryTime: 3600000,                   // 1 hour
            
            // Game management
            cardValidationCacheTTL: 300000,             // 5 minutes
            gameOperationRetryDelay: 1000,              // 1 second
            
            // Dashboard refresh
            fallbackUpdateInterval: 30000               // 30 seconds
        };

        // CONFIGURATION FIX: Centralized UI limitations and defaults
        this.limits = {
            // Input validation limits
            maxGameNameLength: 100,
            maxGameDescriptionLength: 500,
            maxFilenameLength: 255,
            maxPlaylistIdLength: 100,
            minPlaylistIdLength: 5,
            
            // Card generation limits
            defaultCardCount: 16,
            minCardCount: 1,
            maxCardCount: 100,
            
            // Error handling limits
            maxErrorHistorySize: 10,
            maxFallbackErrors: 5,
            maxReconnectAttempts: 5
        };

        // CONFIGURATION FIX: Centralized validation patterns
        this.patterns = {
            gameNamePattern: /^[a-zA-Z0-9\s\-_\.]+$/,
            playlistIdPattern: /^[a-zA-Z0-9_-]+$/,
            filenamePattern: /^[^\/\\:*?"<>|]+$/,
            idPattern: /^[a-zA-Z0-9_-]+$/
        };

        // CONFIGURATION FIX: Centralized UI messages and templates
        this.messages = {
            errors: {
                required: (field) => `${field} is required`,
                empty: (field) => `${field} cannot be empty`,
                minLength: (field, min) => `${field} must be at least ${min} characters`,
                maxLength: (field, max) => `${field} must not exceed ${max} characters`,
                invalidChars: (field) => `${field} contains invalid characters`,
                invalidNumber: (field) => `${field} must be a valid number`,
                invalidInteger: (field) => `${field} must be a valid integer`,
                outOfRange: (field, min, max) => `${field} must be between ${min} and ${max}`,
                invalidFilename: (field) => `${field} contains invalid filename characters`,
                pathTraversal: (field) => `${field} cannot contain relative path components`
            },
            success: {
                gameLoaded: 'Game loaded successfully',
                cardGenerated: 'Cards generated successfully',
                playlistAdded: 'Playlist added successfully',
                deviceSelected: 'Device selected successfully'
            },
            info: {
                noCardsYet: '<div class="text-center py-12"><i data-lucide="music" class="h-16 w-16 mx-auto mb-4 text-gray-400"></i><h3 class="text-lg font-semibold text-gray-700 mb-2">Welcome to Musical Bingo!</h3><p class="text-gray-600 mb-4">To get started, you need to add a Spotify playlist.</p><button id="openSetupModalBtn" class="bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg font-medium">Add Playlist</button></div>',
                noTracksPlayed: '<div class="text-center text-gray-500 py-4">No tracks played yet</div>'
            }
        };

        // CONFIGURATION FIX: Environment-specific configurations
        this.api = {
            defaultTimeout: 20000,                      // 20 seconds
            retryAttempts: 3,
            retryBaseDelay: 1000                        // 1 second
        };

        // Make configuration immutable to prevent accidental changes
        Object.freeze(this.timing);
        Object.freeze(this.limits);
        Object.freeze(this.patterns);
        Object.freeze(this.messages);
        Object.freeze(this.api);
        Object.freeze(this);
    }

    /**
     * Get timing configuration
     * @param {string} key - Timing configuration key
     * @returns {number} - Timing value in milliseconds
     */
    getTiming(key) {
        return this.timing[key] || 0;
    }

    /**
     * Get limit configuration
     * @param {string} key - Limit configuration key
     * @returns {number} - Limit value
     */
    getLimit(key) {
        return this.limits[key] || 0;
    }

    /**
     * Get validation pattern
     * @param {string} key - Pattern configuration key
     * @returns {RegExp} - Validation pattern
     */
    getPattern(key) {
        return this.patterns[key] || /.*/;
    }

    /**
     * Get message template
     * @param {string} category - Message category (errors, success, info)
     * @param {string} key - Message key
     * @returns {string|function} - Message template
     */
    getMessage(category, key) {
        return this.messages[category]?.[key] || '';
    }

    /**
     * Get API configuration
     * @param {string} key - API configuration key
     * @returns {any} - API configuration value
     */
    getApiConfig(key) {
        return this.api[key];
    }
}

// Create global configuration instance
const appConfig = new AppConfig();

// Export for use in other modules
window.appConfig = appConfig;

// Provide backward compatibility constants
window.APP_CONFIG = {
    // Legacy support for direct access to common values
    DEFAULT_NOTIFICATION_DURATION: appConfig.getTiming('notificationDuration'),
    DEFAULT_WEBSOCKET_TIMEOUT: appConfig.getTiming('websocketHealthCheckInterval'),
    DEFAULT_CARD_COUNT: appConfig.getLimit('defaultCardCount'),
    MAX_CARD_COUNT: appConfig.getLimit('maxCardCount'),
    FALLBACK_POLLING_INTERVAL: appConfig.getTiming('websocketFallbackPollingInterval')
};
