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
        const gameName = document.getElementById('gameSaveName').value;
        const gameDescription = document.getElementById('gameSaveDescription').value;

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
        const filename = document.getElementById('savedGamesSelect').value;
        if (!filename) {
            showError('Please select a game to load');
            return;
        }

        try {
            const response = await this.fetchJSON(`/game_management/api/load_game/${filename}`, {
                method: 'POST'
            });

            showSuccess('Game loaded successfully');

            // Emit a custom event that dashboard.js can listen for
            const event = new CustomEvent('gameLoaded', { 
                detail: { gameInfo: response.game_info } 
            });
            document.dispatchEvent(event);

            // Reset the select
            document.getElementById('savedGamesSelect').value = '';

        } catch (error) {
            showError('Failed to load game: ' + error.message);
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
            throw error;
        }
    }
}

// Create instance when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.gameManagement = new GameManagement();
});