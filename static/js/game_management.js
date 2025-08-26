// game_management.js

class GameManagement {
    constructor() {
        this.initializeEventListeners();
        this.loadSavedGames();
    }

    initializeEventListeners() {
        const btnSaveGame = document.getElementById('btnSaveGame');
        if (btnSaveGame) {
            btnSaveGame.addEventListener('click', () => this.saveGame());
        }
        const btnLoadGame = document.getElementById('btnLoadGame');
        if (btnLoadGame) {
            btnLoadGame.addEventListener('click', () => this.loadGame());
        }
        // Refresh saved games list when modal opens
        const savedGamesSelect = document.getElementById('savedGamesSelect');
        if (savedGamesSelect) {
            savedGamesSelect.addEventListener('focus', () => this.loadSavedGames());
        }
    }

    async saveGame() {
        const gameNameEl = document.getElementById('gameSaveName');
        const gameDescriptionEl = document.getElementById('gameSaveDescription');

        // INPUT VALIDATION FIX: Comprehensive input validation and sanitization
        let gameName, gameDescription;
        try {
        gameName = this.validateAndSanitizeInput(gameNameEl?.value, 'string', {
            minLength: 1,
            maxLength: appConfig.getLimit('maxGameNameLength'), // CONFIGURATION FIX: Use centralized limit
            pattern: appConfig.getPattern('gameNamePattern'), // CONFIGURATION FIX: Use centralized pattern
            fieldName: 'Game Name'
        });

        gameDescription = this.validateAndSanitizeInput(gameDescriptionEl?.value, 'string', {
            required: false,
            maxLength: appConfig.getLimit('maxGameDescriptionLength'), // CONFIGURATION FIX: Use centralized limit
            fieldName: 'Game Description'
        });
        } catch (error) {
            showError(error.message);
            return;
        }

        if (!gameName) {
            showError('Game name is required');
            return;
        }
        try {
            const response = await this.fetchJSON('/game_management/api/save_game', {
                method: 'POST',
                body: JSON.stringify({
                    name: gameName,
                    description: gameDescription
                })
            });

            showSuccess('Game saved successfully');
            await this.loadSavedGames();

            // Clear the form
            document.getElementById('gameSaveName').value = '';
            document.getElementById('gameSaveDescription').value = '';

        } catch (error) {
            showError('Failed to save game: ' + error.message);
        }
    }

    async loadSavedGames() {
        try {
            const response = await this.fetchJSON('/game_management/api/list_saved_games');
            const savedGamesSelect = document.getElementById('savedGamesSelect');
            savedGamesSelect.innerHTML = '<option value="">Select a saved game...</option>';

            response.saved_games.forEach(game => {
                const option = document.createElement('option');
                option.value = game.filename;
                const date = new Date(game.timestamp).toLocaleString();
                option.textContent = `${game.name} (${date})`;
                option.title = game.description || 'No description';
                savedGamesSelect.appendChild(option);
            });
        } catch (error) {
            showError('Failed to load saved games: ' + error.message);
        }
    }

    async loadGame() {
        const filenameSelect = document.getElementById('savedGamesSelect');
        
        // INPUT VALIDATION FIX: Validate filename selection
        let filename;
        try {
            filename = this.validateAndSanitizeInput(filenameSelect?.value, 'filename', {
                required: true,
                maxLength: appConfig.getLimit('maxFilenameLength'), // CONFIGURATION FIX: Use centralized limit
                fieldName: 'Selected Game File'
            });
        } catch (error) {
            showError(error.message);
            return;
        }
    
        try {
            const response = await this.fetchJSON(`/game_management/api/load_game/${filename}`, {
                method: 'POST'
            });
    
            showSuccess('Game loaded successfully');
    
            // Force full update including card validation
            await this.forceFullUpdate();
    
            // Reset the select
            document.getElementById('savedGamesSelect').value = '';
    
        } catch (error) {
            showError('Failed to load game: ' + error.message);
        }
    }

    async forceFullUpdate() {
        const event = new CustomEvent('gameLoaded');
        document.dispatchEvent(event);
        
        // Wait a short moment for the cards to load before validating
        setTimeout(async () => {
            try {
                const cardsResponse = await this.fetchJSON('/card/api/get_cards');
                if (cardsResponse.cards) {
                    const validationPromises = Object.keys(cardsResponse.cards).map(cardId => 
                        this.fetchJSON(`/card/api/check_card/${cardId}`)
                    );
                    await Promise.all(validationPromises);
                }
            } catch (error) {
                console.error('Error validating cards after load:', error);
                if (window.errorHandler) {
                    window.errorHandler.handleError(error, 'Card Validation After Load', { autoHide: true });
                }
            }
        }, 500);
    }

    /**
     * Validate and sanitize user input
     * INPUT VALIDATION FIX: Comprehensive input validation with type checking and sanitization
     * @param {any} input - Raw input value
     * @param {string} type - Expected type (string, number, email, etc.)
     * @param {Object} options - Validation options
     * @returns {any} - Validated and sanitized input
     * @throws {Error} - If validation fails
     */
    validateAndSanitizeInput(input, type, options = {}) {
        const {
            required = false,
            minLength = 0,
            maxLength = Infinity,
            min = -Infinity,
            max = Infinity,
            pattern = null,
            fieldName = 'Input',
            allowEmpty = !required
        } = options;

        // Handle null/undefined inputs
        if (input === null || input === undefined || input === '') {
            if (required) {
                throw new Error(`${fieldName} is required`);
            }
            return allowEmpty ? '' : null;
        }
        // Convert input to string for initial processing
        let value = String(input).trim();

        // Check if empty after trimming
        if (value === '' && required) {
            throw new Error(`${fieldName} cannot be empty`);
        }
        // Type-specific validation and conversion
        switch (type) {
            case 'string':
                // XSS Prevention: Remove potentially dangerous characters
                value = value.replace(/[<>'"&]/g, '');
                
                // Length validation
                if (value.length < minLength) {
                    throw new Error(`${fieldName} must be at least ${minLength} characters`);
                }
                if (value.length > maxLength) {
                    throw new Error(`${fieldName} must not exceed ${maxLength} characters`);
                }
                
                // Pattern validation
                if (pattern && !pattern.test(value)) {
                    throw new Error(`${fieldName} contains invalid characters`);
                }
                
                return value;

            case 'number':
                const numValue = parseFloat(value);
                if (isNaN(numValue)) {
                    throw new Error(`${fieldName} must be a valid number`);
                }
                if (numValue < min) {
                    throw new Error(`${fieldName} must be at least ${min}`);
                }
                if (numValue > max) {
                    throw new Error(`${fieldName} must not exceed ${max}`);
                }
                return numValue;

            case 'integer':
                const intValue = parseInt(value, 10);
                if (isNaN(intValue) || !Number.isInteger(intValue)) {
                    throw new Error(`${fieldName} must be a valid integer`);
                }
                if (intValue < min) {
                    throw new Error(`${fieldName} must be at least ${min}`);
                }
                if (intValue > max) {
                    throw new Error(`${fieldName} must not exceed ${max}`);
                }
                return intValue;

            case 'filename':
                // Validate filename - no path traversal, valid characters only
                if (/[\/\\:*?"<>|]/.test(value)) {
                    throw new Error(`${fieldName} contains invalid filename characters`);
                }
                if (value.startsWith('.') || value.includes('..')) {
                    throw new Error(`${fieldName} cannot contain relative path components`);
                }
                return value;

            default:
                return value;
        }
    }

    // Utility function for making JSON requests
    async fetchJSON(url, options = {}) {
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
            if (window.errorHandler) {
                window.errorHandler.handleError(error, `Fetch Request (${url})`, { autoHide: true });
            }
            throw error;
        }
    }
}

// Create instance when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.gameManagement = new GameManagement();
});