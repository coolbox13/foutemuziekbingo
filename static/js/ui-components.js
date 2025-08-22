/**
 * UI Components Module
 *
 * Reusable UI components and DOM manipulation utilities for the Musical Bingo application.
 * Handles UI updates, component rendering, modal management, and user interface interactions.
 */

class UIComponents {
    constructor() {
        this.modals = new Map();
        this.loadingElements = new Set();
        this.notifications = new Map();
        this.setupUIEventListeners();
    }

    // === DOM MANIPULATION UTILITIES ===

    /**
     * Update element content safely
     * @param {string} id - Element ID
     * @param {string|number} value - Content value
     * @param {string} fallback - Fallback value if element not found
     */
    updateElement(id, value, fallback = '—') {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value !== undefined && value !== null ? value : fallback;
        }
    }

    /**
     * Update element with HTML content
     * @param {string} id - Element ID
     * @param {string} html - HTML content
     * @param {string} fallback - Fallback HTML if element not found
     */
    updateElementHTML(id, html, fallback = '') {
        const element = document.getElementById(id);
        if (element) {
            element.innerHTML = html !== undefined && html !== null ? html : fallback;
        }
    }

    /**
     * Show/hide element
     * @param {string} id - Element ID
     * @param {boolean} show - Whether to show the element
     */
    toggleElement(id, show) {
        const element = document.getElementById(id);
        if (element) {
            if (show) {
                element.style.display = '';
                element.classList.remove('hidden');
            } else {
                element.classList.add('hidden');
            }
        }
    }

    /**
     * Add CSS class to element
     * @param {string} id - Element ID
     * @param {string} className - CSS class to add
     */
    addClass(id, className) {
        const element = document.getElementById(id);
        if (element) {
            element.classList.add(className);
        }
    }

    /**
     * Remove CSS class from element
     * @param {string} id - Element ID
     * @param {string} className - CSS class to remove
     */
    removeClass(id, className) {
        const element = document.getElementById(id);
        if (element) {
            element.classList.remove(className);
        }
    }

    /**
     * Set loading state for an element
     * @param {string} id - Element ID
     * @param {boolean} loading - Loading state
     * @param {string} loadingText - Text to show while loading
     */
    setElementLoading(id, loading, loadingText = 'Loading...') {
        const element = document.getElementById(id);
        if (!element) return;

        if (loading) {
            element.dataset.originalContent = element.innerHTML;
            element.innerHTML = '<span class="flex items-center justify-center"><i data-lucide="loader-2" class="h-4 w-4 animate-spin mr-2"></i>' + loadingText + '</span>';
            element.disabled = true;
            this.loadingElements.add(id);
        } else {
            if (element.dataset.originalContent) {
                element.innerHTML = element.dataset.originalContent;
                delete element.dataset.originalContent;
            }
            element.disabled = false;
            this.loadingElements.delete(id);
        }

        // Re-initialize Lucide icons
        this.updateLucideIcons();
    }

    // === NOTIFICATION SYSTEM ===

    /**
     * Show success message
     * @param {string} message - Success message
     * @param {number} duration - Auto-hide duration (0 for no auto-hide)
     */
    showSuccess(message, duration = 4000) {
        this.showNotification(message, 'success', duration);
    }

    /**
     * Show error message
     * @param {string} message - Error message (can contain HTML)
     * @param {number} duration - Auto-hide duration (0 for no auto-hide)
     */
    showError(message, duration = 8000) {
        this.showNotification(message, 'error', duration);
    }

    /**
     * Show warning message
     * @param {string} message - Warning message
     * @param {number} duration - Auto-hide duration (0 for no auto-hide)
     */
    showWarning(message, duration = 6000) {
        this.showNotification(message, 'warning', duration);
    }

    /**
     * Show info message
     * @param {string} message - Info message
     * @param {number} duration - Auto-hide duration (0 for no auto-hide)
     */
    showInfo(message, duration = 5000) {
        this.showNotification(message, 'info', duration);
    }

    /**
     * Show notification with custom type
     * @param {string} message - Notification message
     * @param {string} type - Notification type (success, error, warning, info)
     * @param {number} duration - Auto-hide duration (0 for no auto-hide)
     */
    showNotification(message, type = 'info', duration = 5000) {
        const id = 'notification-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        
        // Create notification element
        const notification = document.createElement('div');
        notification.id = id;
        notification.className = this.getNotificationClasses(type);
        
        // Add icon and message
        const icon = this.getNotificationIcon(type);
        notification.innerHTML = '<div class="flex items-center"><i data-lucide="' + icon + '" class="h-5 w-5 mr-3 flex-shrink-0"></i><div class="flex-1">' + message + '</div><button class="ml-3 p-1 hover:bg-white hover:bg-opacity-20 rounded" onclick="uiComponents.hideNotification(\'' + id + '\')"><i data-lucide="x" class="h-4 w-4"></i></button></div>';

        // Add to container or create container
        let container = document.getElementById('notifications-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notifications-container';
            container.className = 'fixed top-4 right-4 z-50 space-y-2 max-w-md';
            document.body.appendChild(container);
        }

        container.appendChild(notification);
        this.notifications.set(id, notification);

        // Initialize Lucide icons
        this.updateLucideIcons();

        // Auto-hide if duration specified
        if (duration > 0) {
            setTimeout(() => {
                this.hideNotification(id);
            }, duration);
        }

        return id;
    }

    /**
     * Hide notification
     * @param {string} id - Notification ID
     */
    hideNotification(id) {
        const notification = this.notifications.get(id);
        if (notification) {
            notification.style.transform = 'translateX(100%)';
            notification.style.opacity = '0';
            
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
                this.notifications.delete(id);
            }, 300);
        }
    }

    /**
     * Get CSS classes for notification type
     * @param {string} type - Notification type
     * @returns {string} - CSS classes
     */
    getNotificationClasses(type) {
        const baseClasses = 'transform transition-all duration-300 ease-in-out p-4 rounded-lg shadow-lg text-white max-w-md';
        
        const typeClasses = {
            success: 'bg-green-500 border-green-600',
            error: 'bg-red-500 border-red-600',
            warning: 'bg-yellow-500 border-yellow-600',
            info: 'bg-blue-500 border-blue-600'
        };

        return baseClasses + ' ' + (typeClasses[type] || typeClasses.info);
    }

    /**
     * Get icon for notification type
     * @param {string} type - Notification type
     * @returns {string} - Icon name
     */
    getNotificationIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'alert-circle',
            warning: 'alert-triangle',
            info: 'info'
        };

        return icons[type] || icons.info;
    }

    // === MODAL MANAGEMENT ===

    /**
     * Show modal
     * @param {string} modalId - Modal element ID
     * @param {Object} options - Modal options
     */
    showModal(modalId, options = {}) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        // Store modal state
        this.modals.set(modalId, { 
            element: modal, 
            options: options,
            isVisible: true
        });

        // Show modal
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
        
        // Add backdrop click handler if enabled
        if (options.closeOnBackdrop !== false) {
            modal.addEventListener('click', this.handleBackdropClick.bind(this, modalId));
        }

        // Focus management
        if (options.focusElement) {
            setTimeout(() => {
                const focusEl = document.getElementById(options.focusElement);
                if (focusEl) focusEl.focus();
            }, 100);
        }

        // Trigger custom event
        this.triggerCustomEvent('modalShown', { modalId: modalId, options: options });
    }

    /**
     * Hide modal
     * @param {string} modalId - Modal element ID
     */
    hideModal(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        // Hide modal
        modal.classList.add('hidden');
        modal.style.display = 'none';

        // Remove from state
        if (this.modals.has(modalId)) {
            const modalState = this.modals.get(modalId);
            modalState.isVisible = false;
            
            // Remove backdrop click handler
            modal.removeEventListener('click', this.handleBackdropClick);
        }

        // Trigger custom event
        this.triggerCustomEvent('modalHidden', { modalId: modalId });
    }

    /**
     * Toggle modal visibility
     * @param {string} modalId - Modal element ID
     * @param {boolean} show - Force show/hide state (optional)
     * @param {Object} options - Modal options
     */
    toggleModal(modalId, show = null, options = {}) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        const isVisible = this.modals.has(modalId) && this.modals.get(modalId).isVisible;
        const shouldShow = show !== null ? show : !isVisible;

        if (shouldShow) {
            this.showModal(modalId, options);
        } else {
            this.hideModal(modalId);
        }
    }

    /**
     * Handle backdrop click for modal
     * @param {string} modalId - Modal element ID
     * @param {Event} event - Click event
     */
    handleBackdropClick(modalId, event) {
        if (event.target === event.currentTarget) {
            this.hideModal(modalId);
        }
    }

    // === STATUS BADGES ===

    /**
     * Update connection status badge
     * @param {string} status - Connection status ('connected', 'disconnected', 'checking')
     */
    updateConnectionStatus(status) {
        this.updateElement('connectionStatus', status.charAt(0).toUpperCase() + status.slice(1));
        
        const statusEl = document.getElementById('connectionStatus');
        if (statusEl && statusEl.parentElement) {
            const badge = statusEl.parentElement;
            badge.className = 'px-2 py-1 rounded text-xs font-medium ' + this.getConnectionStatusClasses(status);
        }
    }

    /**
     * Update WebSocket badge
     * @param {boolean} connected - WebSocket connection status
     */
    updateWebsocketBadge(connected) {
        const badgeEl = document.getElementById('websocketStatus');
        if (!badgeEl) return;

        badgeEl.textContent = connected ? 'Connected' : 'Disconnected';
        badgeEl.className = 'px-2 py-1 rounded text-xs font-medium text-white ' + 
            (connected ? 'bg-green-500' : 'bg-red-500');
        
        if (connected) {
            badgeEl.classList.add('connection-pulse');
        } else {
            badgeEl.classList.remove('connection-pulse');
        }
    }

    /**
     * Update Spotify badge
     * @param {string} status - Spotify status ('connected', 'disconnected', 'checking')
     */
    updateSpotifyBadge(status) {
        const badgeEl = document.getElementById('spotifyStatus');
        if (!badgeEl) return;

        const statusText = {
            'connected': 'Connected',
            'disconnected': 'Disconnected', 
            'checking': 'Checking...'
        };

        badgeEl.textContent = statusText[status] || 'Unknown';
        badgeEl.className = 'px-2 py-1 rounded text-xs font-medium text-white ' + 
            this.getSpotifyStatusClasses(status);
    }

    /**
     * Get CSS classes for connection status
     * @param {string} status - Connection status
     * @returns {string} - CSS classes
     */
    getConnectionStatusClasses(status) {
        const classes = {
            'connected': 'bg-green-500 text-white',
            'disconnected': 'bg-red-500 text-white',
            'checking': 'bg-yellow-500 text-white'
        };
        return classes[status] || 'bg-gray-500 text-white';
    }

    /**
     * Get CSS classes for Spotify status
     * @param {string} status - Spotify status
     * @returns {string} - CSS classes
     */
    getSpotifyStatusClasses(status) {
        const classes = {
            'connected': 'spotify-connected',
            'disconnected': 'spotify-disconnected',
            'checking': 'bg-yellow-500'
        };
        return classes[status] || 'bg-gray-500';
    }

    // === DASHBOARD UI UPDATES ===

    /**
     * Update statistics display
     * @param {Object} stats - Statistics object
     */
    updateStatisticsDisplay(stats) {
        if (!stats) return;

        // Update individual stat elements
        this.updateElement('totalTracks', stats.total_tracks || 0);
        this.updateElement('playedTracks', stats.played_tracks || 0);
        this.updateElement('totalCards', stats.total_cards || 0);
        this.updateElement('completedCards', stats.completed_cards || 0);
        this.updateElement('activeDevices', stats.active_devices || 0);
        this.updateElement('gameStatus', stats.game_status || 'No active game');

        // Update progress bars if they exist
        this.updateProgressBar('trackProgress', stats.played_tracks || 0, stats.total_tracks || 1);
        this.updateProgressBar('cardProgress', stats.completed_cards || 0, stats.total_cards || 1);
    }

    /**
     * Update progress bar
     * @param {string} id - Progress bar element ID
     * @param {number} current - Current progress value
     * @param {number} total - Total progress value
     */
    updateProgressBar(id, current, total) {
        const progressBar = document.getElementById(id);
        if (!progressBar) return;

        const percentage = total > 0 ? Math.round((current / total) * 100) : 0;
        
        // Update progress bar width
        const progressFill = progressBar.querySelector('.progress-fill') || progressBar;
        progressFill.style.width = percentage + '%';
        
        // Update text if exists
        const progressText = progressBar.querySelector('.progress-text');
        if (progressText) {
            progressText.textContent = current + ' / ' + total + ' (' + percentage + '%)';
        }
    }

    /**
     * Show setup guide
     */
    showSetupGuide() {
        const cardsContainer = document.getElementById('cardsContainer');
        if (cardsContainer) {
            cardsContainer.innerHTML = '<div class="text-center py-12"><i data-lucide="music" class="h-16 w-16 mx-auto mb-4 text-gray-400"></i><h3 class="text-lg font-semibold text-gray-700 mb-2">Welcome to Musical Bingo!</h3><p class="text-gray-600 mb-4">To get started, you need to add a Spotify playlist.</p><button id="openSetupModalBtn" class="bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg font-medium">Add Playlist</button></div>';
            
            // Add event listener for setup button
            const setupBtn = document.getElementById('openSetupModalBtn');
            if (setupBtn) {
                setupBtn.addEventListener('click', () => {
                    this.showModal('setupModal');
                });
            }
            
            this.updateLucideIcons();
        }
    }

    // === CARD DISPLAY ===

    /**
     * Update card display with status and matches
     * @param {string} cardId - Card ID
     * @param {string} status - Card status
     * @param {Array} matches - Card matches
     */
    updateCardDisplay(cardId, status, matches = []) {
        const cardElement = document.getElementById('card-' + cardId);
        if (!cardElement) return;

        // Update card status
        const statusElement = cardElement.querySelector('.card-status');
        if (statusElement) {
            statusElement.textContent = status;
            statusElement.className = 'card-status px-2 py-1 rounded text-xs font-medium ' + 
                this.getCardStatusClasses(status);
        }

        // Update matches count
        const matchesElement = cardElement.querySelector('.card-matches');
        if (matchesElement) {
            matchesElement.textContent = matches.length + ' matches';
        }

        // Highlight matched positions
        matches.forEach(match => {
            const positionElement = cardElement.querySelector('[data-position="' + match.position + '"]');
            if (positionElement) {
                positionElement.classList.add('matched');
            }
        });

        // Add bingo effect if status is BINGO
        if (status === 'BINGO!' || status === 'WINNER') {
            cardElement.classList.add('bingo-winner');
            this.addBingoEffect(cardElement);
        }
    }

    /**
     * Get CSS classes for card status
     * @param {string} status - Card status
     * @returns {string} - CSS classes
     */
    getCardStatusClasses(status) {
        const classes = {
            'BINGO!': 'bg-gold-500 text-white',
            'WINNER': 'bg-gold-500 text-white',
            'In Progress': 'bg-blue-500 text-white',
            'Ready': 'bg-green-500 text-white',
            'No matches': 'bg-gray-500 text-white'
        };
        return classes[status] || 'bg-gray-500 text-white';
    }

    /**
     * Add bingo winner effect
     * @param {HTMLElement} cardElement - Card element
     */
    addBingoEffect(cardElement) {
        // Add confetti or sparkle effect
        cardElement.style.animation = 'bingoWinner 2s ease-in-out';
        
        // Remove animation after completion
        setTimeout(() => {
            cardElement.style.animation = '';
        }, 2000);
    }

    // === SETUP AND UTILITIES ===

    /**
     * Setup UI event listeners
     */
    setupUIEventListeners() {
        // Close modals with Escape key
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                this.modals.forEach((modalState, modalId) => {
                    if (modalState.isVisible) {
                        this.hideModal(modalId);
                    }
                });
            }
        });

        // Handle browser back button for modals
        window.addEventListener('popstate', () => {
            this.modals.forEach((modalState, modalId) => {
                if (modalState.isVisible) {
                    this.hideModal(modalId);
                }
            });
        });
    }

    /**
     * Update Lucide icons
     */
    updateLucideIcons() {
        if (typeof lucide !== 'undefined' && lucide.createIcons) {
            lucide.createIcons();
        }
    }

    /**
     * Trigger custom event
     * @param {string} eventName - Event name
     * @param {Object} detail - Event detail data
     */
    triggerCustomEvent(eventName, detail = {}) {
        const event = new CustomEvent(eventName, { detail: detail });
        document.dispatchEvent(event);
    }

    /**
     * Get UI component statistics
     * @returns {Object} - Statistics object
     */
    getStats() {
        return {
            activeModals: Array.from(this.modals.keys()).filter(id => this.modals.get(id).isVisible),
            loadingElements: Array.from(this.loadingElements),
            activeNotifications: this.notifications.size
        };
    }

    /**
     * Clear all notifications
     */
    clearAllNotifications() {
        this.notifications.forEach((notification, id) => {
            this.hideNotification(id);
        });
    }

    /**
     * Reset UI components state
     */
    reset() {
        this.clearAllNotifications();
        this.modals.forEach((modalState, modalId) => {
            if (modalState.isVisible) {
                this.hideModal(modalId);
            }
        });
        this.loadingElements.clear();
    }
}

// Create global UI components instance
const uiComponents = new UIComponents();

// Export for use in other modules
window.uiComponents = uiComponents;

// Provide backward compatibility functions
window.updateElement = function(id, value, fallback) { uiComponents.updateElement(id, value, fallback); };
window.showSuccess = function(message, duration) { uiComponents.showSuccess(message, duration); };
window.showError = function(message, duration) { uiComponents.showError(message, duration); };
window.showWarning = function(message, duration) { uiComponents.showWarning(message, duration); };
window.showInfo = function(message, duration) { uiComponents.showInfo(message, duration); };
window.toggleSetupModal = function(show) { uiComponents.toggleModal('setupModal', show); };
window.showSetupGuide = function() { uiComponents.showSetupGuide(); };
window.updateConnectionStatus = function(status) { uiComponents.updateConnectionStatus(status); };
window.updateWebsocketBadge = function(connected) { uiComponents.updateWebsocketBadge(connected); };
window.updateSpotifyBadge = function(status) { uiComponents.updateSpotifyBadge(status); };
window.updateStatisticsDisplay = function(stats) { uiComponents.updateStatisticsDisplay(stats); };
window.updateCardDisplay = function(cardId, status, matches) { uiComponents.updateCardDisplay(cardId, status, matches); };
