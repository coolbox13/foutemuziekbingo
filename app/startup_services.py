"""
Application Startup Services

This module handles initialization of background services and
system components that need to be started with the application.

Author: Claude Code Assistant
Date: 2025-01-18
Issue: CRIT-003 - Background service startup integration
"""

import asyncio
import logging
from typing import List, Dict, Any

from app.background_token_service import start_background_token_service, stop_background_token_service
from app.spotify_token_manager import spotify_token_manager

logger = logging.getLogger("music_bingo")


class StartupManager:
    """Manages application startup and shutdown procedures"""

    def __init__(self):
        self.services_started = []
        self.startup_errors = []

    async def startup_application(self) -> Dict[str, Any]:
        """
        Start all background services and initialize system components.
        
        Returns:
            Dictionary with startup results and any errors
        """
        startup_results = {
            "success": True,
            "services_started": [],
            "services_failed": [],
            "errors": []
        }

        logger.info("[STARTUP-001] Starting application services")

        # Start background token refresh service
        try:
            logger.info("[STARTUP-002] Starting background token refresh service")
            token_service_started = await start_background_token_service()
            
            if token_service_started:
                startup_results["services_started"].append("background_token_service")
                self.services_started.append("background_token_service")
                logger.info("[STARTUP-003] Background token service started successfully")
            else:
                startup_results["services_failed"].append("background_token_service")
                startup_results["errors"].append("Failed to start background token service")
                logger.error("[STARTUP-ERROR-001] Failed to start background token service")
                
        except Exception as e:
            startup_results["success"] = False
            startup_results["services_failed"].append("background_token_service")
            startup_results["errors"].append(f"Background token service error: {str(e)}")
            logger.error(
                "[STARTUP-ERROR-002] Exception starting background token service",
                extra={"error": str(e)},
                exc_info=True
            )

        # Initialize token manager health check
        try:
            logger.info("[STARTUP-004] Performing token manager health check")
            health = await spotify_token_manager.health_check()
            
            if health.get("healthy", False):
                startup_results["services_started"].append("token_manager")
                logger.info("[STARTUP-005] Token manager health check passed")
            else:
                startup_results["services_failed"].append("token_manager")
                startup_results["errors"].append("Token manager health check failed")
                logger.warning(
                    "[STARTUP-WARN-001] Token manager health check failed",
                    extra={"health_status": health}
                )
                
        except Exception as e:
            startup_results["services_failed"].append("token_manager")
            startup_results["errors"].append(f"Token manager health check error: {str(e)}")
            logger.error(
                "[STARTUP-ERROR-003] Exception in token manager health check",
                extra={"error": str(e)},
                exc_info=True
            )

        # Log startup summary
        if startup_results["success"] and not startup_results["services_failed"]:
            logger.info(
                "[STARTUP-006] Application startup completed successfully",
                extra={
                    "services_started": startup_results["services_started"],
                    "total_services": len(startup_results["services_started"])
                }
            )
        else:
            startup_results["success"] = False
            logger.warning(
                "[STARTUP-WARN-002] Application startup completed with issues",
                extra={
                    "services_started": startup_results["services_started"],
                    "services_failed": startup_results["services_failed"],
                    "errors": startup_results["errors"]
                }
            )

        return startup_results

    async def shutdown_application(self) -> Dict[str, Any]:
        """
        Gracefully shutdown all services.
        
        Returns:
            Dictionary with shutdown results
        """
        shutdown_results = {
            "success": True,
            "services_stopped": [],
            "services_failed": [],
            "errors": []
        }

        logger.info("[SHUTDOWN-001] Starting application shutdown")

        # Stop background token service
        if "background_token_service" in self.services_started:
            try:
                logger.info("[SHUTDOWN-002] Stopping background token service")
                token_service_stopped = await stop_background_token_service()
                
                if token_service_stopped:
                    shutdown_results["services_stopped"].append("background_token_service")
                    self.services_started.remove("background_token_service")
                    logger.info("[SHUTDOWN-003] Background token service stopped successfully")
                else:
                    shutdown_results["services_failed"].append("background_token_service")
                    shutdown_results["errors"].append("Failed to stop background token service")
                    logger.error("[SHUTDOWN-ERROR-001] Failed to stop background token service")
                    
            except Exception as e:
                shutdown_results["success"] = False
                shutdown_results["services_failed"].append("background_token_service")
                shutdown_results["errors"].append(f"Background token service shutdown error: {str(e)}")
                logger.error(
                    "[SHUTDOWN-ERROR-002] Exception stopping background token service",
                    extra={"error": str(e)},
                    exc_info=True
                )

        # Log shutdown summary
        if shutdown_results["success"] and not shutdown_results["services_failed"]:
            logger.info(
                "[SHUTDOWN-004] Application shutdown completed successfully",
                extra={
                    "services_stopped": shutdown_results["services_stopped"],
                    "total_services": len(shutdown_results["services_stopped"])
                }
            )
        else:
            logger.warning(
                "[SHUTDOWN-WARN-001] Application shutdown completed with issues",
                extra={
                    "services_stopped": shutdown_results["services_stopped"],
                    "services_failed": shutdown_results["services_failed"],
                    "errors": shutdown_results["errors"]
                }
            )

        return shutdown_results


# Global startup manager instance
startup_manager = StartupManager()


# Convenience functions for FastAPI integration
async def startup_handler():
    """FastAPI startup event handler"""
    return await startup_manager.startup_application()


async def shutdown_handler():
    """FastAPI shutdown event handler"""
    return await startup_manager.shutdown_application()
