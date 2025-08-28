/**
 * Error Handler Module
 *
 * Centralized error handling and user feedback system for the Musical Bingo application.
 * Provides graceful error handling, user notifications, and recovery mechanisms.
 */

class ErrorHandler {
    constructor() {
        this.errorCount = 0;
        this.lastErrorTime = null;
        this.maxErrors = 5;
        this.errorCooldown = appConfig.getTiming('errorCooldown'); // CONFIGURATION FIX: Use centralized timing
        this.logQueue = [];
        this.isLoggingToServer = true; // Can be toggled to disable server logging
        this.setupGlobalErrorHandling();
        this.setupConsoleInterception();
    }

    /**
     * Setup global error handling for unhandled errors
     */
    setupGlobalErrorHandling() {
        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            this.handleError(event.reason, 'Unhandled Promise Rejection');
            event.preventDefault();
        });

        // Handle general JavaScript errors
        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            this.handleError(event.error, 'JavaScript Error');
        });
    }

    /**
     * Setup console interception to capture console messages
     */
    setupConsoleInterception() {
        // Store original console methods
        const originalConsole = {
            log: console.log.bind(console),
            error: console.error.bind(console),
            warn: console.warn.bind(console),
            info: console.info.bind(console),
            debug: console.debug.bind(console)
        };

        // Intercept console.error and console.warn
        console.error = (...args) => {
            originalConsole.error(...args);
            this.logConsoleMessage('error', args.join(' '), { stack: new Error().stack });
        };

        console.warn = (...args) => {
            originalConsole.warn(...args);
            this.logConsoleMessage('warn', args.join(' '));
        };

        // Optionally intercept info and debug (commented out to reduce noise)
        // console.info = (...args) => {
        //     originalConsole.info(...args);
        //     this.logConsoleMessage('info', args.join(' '));
        // };

        // console.debug = (...args) => {
        //     originalConsole.debug(...args);
        //     this.logConsoleMessage('debug', args.join(' '));
        // };

        // Store original methods for potential restoration
        this.originalConsole = originalConsole;
    }

    /**
     * Log console message to server
     * @param {string} level - Log level (error, warn, info, debug)
     * @param {string} message - Console message
     * @param {Object} options - Additional options
     */
    logConsoleMessage(level, message, options = {}) {
        if (!this.isLoggingToServer) return;

        // Skip messages from our own error handler to avoid loops
        if (message.includes('[ErrorHandler]') || message.includes('[FRONTEND-')) return;

        // Send to server logs
        this.sendConsoleToServer(level, message, options);
    }

    /**
     * Main error handling method
     * @param {Error|string} error - Error object or message
     * @param {string} context - Context where error occurred
     * @param {Object} options - Additional options
     */
    handleError(error, context = 'Unknown', options = {}) {
        const errorInfo = this.processError(error, context);
        
        // Rate limiting for error notifications
        if (this.shouldShowError()) {
            this.showUserError(errorInfo, options);
        }

        // Log error for debugging
        this.logError(errorInfo);

        // Handle specific error types
        this.handleSpecificErrorTypes(errorInfo, options);
    }

    /**
     * Process error into standardized format
     * @param {Error|string} error - Raw error
     * @param {string} context - Error context
     * @returns {Object} - Processed error info
     */
    processError(error, context) {
        const now = Date.now();
        
        // Extract error details
        let message, type, isAuthError, isNetworkError, status;
        
        if (error instanceof Error) {
            message = error.message;
            type = error.constructor.name;
            isAuthError = error.isAuthError || false;
            isNetworkError = error.isNetworkError || false;
            status = error.status;
        } else if (typeof error === 'string') {
            message = error;
            type = 'String';
        } else {
            message = 'Unknown error occurred';
            type = 'Unknown';
        }

        return {
            message,
            type,
            context,
            isAuthError,
            isNetworkError,
            status,
            timestamp: now,
            stack: error instanceof Error ? error.stack : null
        };
    }

    /**
     * Check if error should be shown to user (rate limiting)
     * @returns {boolean} - Whether to show error
     */
    shouldShowError() {
        const now = Date.now();
        
        // Reset error count after cooldown period
        if (this.lastErrorTime && (now - this.lastErrorTime) > this.errorCooldown) {
            this.errorCount = 0;
        }

        // Check if we're under the error limit
        if (this.errorCount < this.maxErrors) {
            this.errorCount++;
            this.lastErrorTime = now;
            return true;
        }

        return false;
    }

    /**
     * Show error to user with appropriate styling and actions
     * @param {Object} errorInfo - Processed error information
     * @param {Object} options - Display options
     */
    showUserError(errorInfo, options = {}) {
        const { message, isAuthError, isNetworkError, status } = errorInfo;
        const { autoHide = true, duration = appConfig.getTiming('notificationDuration') } = options;

        // Authentication errors get special treatment
        if (isAuthError) {
            this.showError(
                'Session expired or not authenticated. Please <a href="/auth/login/page" class="underline text-blue-300">log in</a>.',
                { type: 'auth', autoHide: false }
            );
            return;
        }

        // Network errors
        if (isNetworkError) {
            this.showError(
                'Network connection issue. Please check your internet connection and try again.',
                { type: 'network', autoHide: true, duration: 8000 }
            );
            return;
        }

        // HTTP status specific errors
        if (status) {
            const statusMessage = this.getStatusMessage(status);
            if (statusMessage) {
                this.showError(statusMessage, { type: 'http', autoHide, duration });
                return;
            }
        }

        // Generic error
        this.showError(message, { type: 'error', autoHide, duration });
    }

    /**
     * Get user-friendly message for HTTP status codes
     * @param {number} status - HTTP status code
     * @returns {string|null} - User-friendly message
     */
    getStatusMessage(status) {
        const statusMessages = {
            400: 'Invalid request. Please check your input and try again.',
            403: 'Access forbidden. You may not have permission for this action.',
            404: 'The requested resource was not found.',
            409: 'Conflict detected. The resource may have been modified.',
            429: 'Too many requests. Please wait a moment and try again.',
            500: 'Server error occurred. Please try again later.',
            502: 'Service temporarily unavailable. Please try again later.',
            503: 'Service temporarily unavailable. Please try again later.'
        };

        return statusMessages[status] || null;
    }

    /**
     * Handle specific error types with custom logic
     * @param {Object} errorInfo - Error information
     * @param {Object} options - Options
     */
    handleSpecificErrorTypes(errorInfo, options = {}) {
        const { isAuthError, context, message } = errorInfo;

        // Authentication errors - redirect if needed
        if (isAuthError && options.redirectOnAuth !== false) {
            setTimeout(() => {
                if (window.location.pathname !== '/auth/login/page') {
                    window.location.href = '/auth/login/page';
                }
            }, 2000);
        }

        // Game-specific errors
        if (context.includes('game') || context.includes('Game')) {
            this.handleGameError(errorInfo);
        }

        // WebSocket errors
        if (context.includes('socket') || context.includes('Socket')) {
            this.handleSocketError(errorInfo);
        }
    }

    /**
     * Handle game-specific errors
     * @param {Object} errorInfo - Error information
     */
    handleGameError(errorInfo) {
        const { message } = errorInfo;
        
        // Reset active game if it's invalid
        if (message.includes('not found') || message.includes('404')) {
            if (window.activeGameId) {
                console.log('Resetting invalid active game ID');
                window.activeGameId = null;
            }
        }
    }

    /**
     * Handle WebSocket-specific errors
     * @param {Object} errorInfo - Error information
     */
    handleSocketError(errorInfo) {
        // WebSocket errors are typically handled by the WebSocket handler
        // but we can log them here for monitoring
        console.warn('WebSocket error handled by ErrorHandler:', errorInfo);
    }

    /**
     * Log error for debugging and monitoring
     * @param {Object} errorInfo - Error information
     */
    logError(errorInfo) {
        const logEntry = {
            timestamp: new Date(errorInfo.timestamp).toISOString(),
            context: errorInfo.context,
            type: errorInfo.type,
            message: errorInfo.message,
            status: errorInfo.status,
            isAuthError: errorInfo.isAuthError,
            isNetworkError: errorInfo.isNetworkError,
            userAgent: navigator.userAgent,
            url: window.location.href,
            stack: errorInfo.stack
        };

        // Log to console for debugging
        console.error('[ErrorHandler]', logEntry);

        // Send to server logs
        this.sendToServerLogs(logEntry);
    }

    /**
     * Send frontend error to server logs
     * @param {Object} logEntry - Log entry to send
     */
    async sendToServerLogs(logEntry) {
        try {
            // Prepare payload for server
            const payload = {
                level: 'error',
                message: logEntry.message,
                context: logEntry.context,
                type: logEntry.type,
                status: logEntry.status,
                url: logEntry.url,
                user_agent: logEntry.userAgent,
                stack: logEntry.stack,
                timestamp: logEntry.timestamp,
                is_auth_error: logEntry.isAuthError || false,
                is_network_error: logEntry.isNetworkError || false,
                additional_data: {
                    browser_console_log: true,
                    page_url: window.location.href,
                    page_title: document.title
                }
            };

            // Send to server endpoint
            const response = await fetch('/api/frontend-log', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                console.warn('Failed to send error to server logs:', response.status);
            }

        } catch (error) {
            // Silently fail to avoid infinite error loops
            console.warn('Error sending to server logs:', error.message);
        }
    }

    /**
     * Send console message to server logs
     * @param {string} level - Log level
     * @param {string} message - Console message
     * @param {Object} options - Additional options
     */
    async sendConsoleToServer(level, message, options = {}) {
        try {
            const payload = {
                level: level,
                message: message,
                context: 'Frontend Console',
                type: 'Console Message',
                url: window.location.href,
                user_agent: navigator.userAgent,
                timestamp: new Date().toISOString(),
                stack: options.stack,
                additional_data: {
                    console_intercept: true,
                    page_url: window.location.href,
                    page_title: document.title
                }
            };

            // Send to server endpoint (non-blocking)
            fetch('/api/frontend-log', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            }).catch(() => {
                // Silently fail to avoid infinite loops
            });

        } catch (error) {
            // Silently fail to avoid infinite error loops
        }
    }

    /**
     * Show error message to user (integrates with existing UI)
     * @param {string} message - Error message (can include HTML)
     * @param {Object} options - Display options
     */
    showError(message, options = {}) {
        const { type = 'error', autoHide = true, duration = appConfig.getTiming('notificationDuration') } = options;

        // Direct implementation - avoid recursion with window.showError
        this.fallbackShowError(message, type, autoHide, duration);
    }

    /**
     * Show success message to user
     * @param {string} message - Success message
     * @param {Object} options - Display options
     */
    showSuccess(message, options = {}) {
        const { autoHide = true, duration = 3000 } = options;

        // Try to use existing showSuccess function if available
        if (typeof window.showSuccess === 'function') {
            window.showSuccess(message);
            return;
        }

        // Fallback implementation
        this.fallbackShowSuccess(message, autoHide, duration);
    }

    /**
     * Fallback error display implementation
     * @param {string} message - Error message
     * @param {string} type - Error type
     * @param {boolean} autoHide - Whether to auto-hide
     * @param {number} duration - Display duration
     */
    fallbackShowError(message, type, autoHide, duration) {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-red-500 text-white p-4 rounded shadow-lg z-50 max-w-md';
        notification.innerHTML = message;

        document.body.appendChild(notification);

        if (autoHide) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, duration);
        }
    }

    /**
     * Fallback success display implementation
     * @param {string} message - Success message
     * @param {boolean} autoHide - Whether to auto-hide
     * @param {number} duration - Display duration
     */
    fallbackShowSuccess(message, autoHide, duration) {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-green-500 text-white p-4 rounded shadow-lg z-50 max-w-md';
        notification.innerHTML = message;

        document.body.appendChild(notification);

        if (autoHide) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, duration);
        }
    }

    /**
     * Clear error state (useful for recovery)
     */
    clearErrorState() {
        this.errorCount = 0;
        this.lastErrorTime = null;
    }

    /**
     * Create error boundary for functions
     * @param {Function} fn - Function to wrap
     * @param {string} context - Error context
     * @returns {Function} - Wrapped function
     */
    createErrorBoundary(fn, context) {
        return async (...args) => {
            try {
                return await fn.apply(this, args);
            } catch (error) {
                this.handleError(error, context);
                throw error;
            }
        };
    }

    /**
     * Retry function with exponential backoff
     * @param {Function} fn - Function to retry
     * @param {Object} options - Retry options
     * @returns {Promise<any>} - Function result
     */
    async withRetry(fn, options = {}) {
        const { 
            maxRetries = 3, 
            baseDelay = appConfig.getApiConfig('retryBaseDelay'), 
            context = 'Retry Operation',
            shouldRetry = null
        } = options;

        let lastError;
        
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                return await fn();
            } catch (error) {
                lastError = error;
                
                // Check if we should retry this error
                if (shouldRetry && !shouldRetry(error)) {
                    break;
                }
                
                // Don't retry on last attempt
                if (attempt === maxRetries) {
                    break;
                }

                // Calculate delay with exponential backoff
                const delay = baseDelay * Math.pow(2, attempt);
                console.log(`Retry attempt ${attempt + 1} after ${delay}ms delay`);
                
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }

        // All retries failed
        this.handleError(lastError, context + ' (All Retries Failed)');
        throw lastError;
    }
}

// Create global error handler instance
const errorHandler = new ErrorHandler();

// Export for use in other modules
window.errorHandler = errorHandler;

// Provide global error handling functions for backward compatibility
window.handleError = (error, context, options) => errorHandler.handleError(error, context, options);
window.showError = (message, options) => errorHandler.showError(message, options);
window.showSuccess = (message, options) => errorHandler.showSuccess(message, options);
