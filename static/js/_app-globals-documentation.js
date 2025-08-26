/**
 * Musical Bingo App - Global Variables Documentation
 * 
 * This file documents the intentional global variables used throughout the app
 * for inter-module communication and backward compatibility. These are NOT pollution
 * but deliberate architectural choices for a web application.
 * 
 * MAIN MODULE INSTANCES:
 * - window.errorHandler      - Centralized error handling and user notifications
 * - window.stateManager      - Frontend state management and caching  
 * - window.webSocketHandler  - Real-time WebSocket communication
 * - window.uiComponents      - UI utilities and component management
 * - window.gameManager       - Game logic and state management
 * - window.apiClient         - HTTP API communication wrapper
 * - window.dashboardApp      - Main dashboard application controller
 * 
 * BACKWARD COMPATIBILITY FUNCTIONS:
 * - window.showError()       - Error notification (via errorHandler)
 * - window.showSuccess()     - Success notification (via errorHandler)  
 * - window.showWarning()     - Warning notification (via uiComponents)
 * - window.showInfo()        - Info notification (via uiComponents)
 * - window.updateElement()   - Safe DOM update (via uiComponents)
 * - window.toggleSetupModal()- Modal control (via uiComponents)
 * - window.switchSetupTab()  - Tab switching (via dashboardApp)
 * 
 * INTER-MODULE COMMUNICATION:
 * - window.activeGameId      - Current active game ID (via stateManager)
 * - window.forceUpdateAll()  - Force UI refresh (via dashboardApp)
 * - window.validateAllCards()- Card validation (via gameManager)
 * 
 * TEMPLATE INTEGRATION:
 * - Functions called directly from HTML onclick handlers
 * - WebSocket callback hooks for real-time updates
 * - Legacy API compatibility for existing template code
 * 
 * This architecture enables:
 * 1. Clean separation between modules
 * 2. Backward compatibility with existing templates
 * 3. Easy debugging from browser console
 * 4. Reliable inter-module communication
 * 5. Plugin/extension capability
 */

// This file is for documentation only and does not contain executable code.
// It explains why the global variables exist and are intentional, not pollution.
