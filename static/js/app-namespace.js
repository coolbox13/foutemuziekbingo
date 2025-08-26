/**
 * App Namespace Module
 *
 * Centralized namespace to reduce global variable pollution while maintaining 
 * backward compatibility. Consolidates all app modules under a single global object.
 * 
 * ARCHITECTURE FIX: Reduces global pollution by organizing modules under window.MusicBingoApp
 */

// Create centralized app namespace
window.MusicBingoApp = window.MusicBingoApp || {
    modules: {},
    state: {},
    config: {},
    events: new EventTarget()
};

/**
 * Register a module with the app namespace
 * @param {string} name - Module name
 * @param {Object} module - Module object
 */
window.MusicBingoApp.registerModule = function(name, module) {
    this.modules[name] = module;
    console.log(`[MusicBingoApp] Registered module: ${name}`);
};

/**
 * Get a registered module
 * @param {string} name - Module name
 * @returns {Object|null} - Module object or null if not found
 */
window.MusicBingoApp.getModule = function(name) {
    return this.modules[name] || null;
};

/**
 * Emit app-level event
 * @param {string} eventName - Event name
 * @param {Object} data - Event data
 */
window.MusicBingoApp.emit = function(eventName, data = {}) {
    const event = new CustomEvent(eventName, { detail: data });
    this.events.dispatchEvent(event);
    console.log(`[MusicBingoApp] Emitted event: ${eventName}`, data);
};

/**
 * Listen for app-level events
 * @param {string} eventName - Event name
 * @param {Function} callback - Event callback
 */
window.MusicBingoApp.on = function(eventName, callback) {
    this.events.addEventListener(eventName, callback);
};

/**
 * Remove event listener
 * @param {string} eventName - Event name  
 * @param {Function} callback - Event callback
 */
window.MusicBingoApp.off = function(eventName, callback) {
    this.events.removeEventListener(eventName, callback);
};

/**
 * Get/set global app state
 * @param {string} key - State key
 * @param {any} value - State value (optional, for setter)
 * @returns {any} - State value
 */
window.MusicBingoApp.state = function(key, value) {
    if (value !== undefined) {
        this.state[key] = value;
        this.emit('stateChanged', { key, value });
        return value;
    }
    return this.state[key];
};

/**
 * Initialize the application namespace
 */
window.MusicBingoApp.initialize = function() {
    console.log('[MusicBingoApp] Application namespace initialized');
    this.emit('appInitialized');
};

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.MusicBingoApp.initialize();
    });
} else {
    window.MusicBingoApp.initialize();
}

// Provide shorthand access
window.App = window.MusicBingoApp;
