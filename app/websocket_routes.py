"""
WebSocket routes for real-time game synchronization
"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from fastapi.security import HTTPBearer
from typing import Optional
from app.websocket_service import ws_manager, handle_websocket_message
from app.auth_service import auth_service
from app.models import User
from app.game_service import game_service

router = APIRouter()
logger = logging.getLogger("music_bingo")
security = HTTPBearer()


async def get_websocket_user(token: str) -> User:
    """Get user from JWT token for WebSocket authentication"""
    try:
        payload = auth_service.verify_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
        from app.database import database
        user_data = await database.get_record("users", user_id)
        if not user_data:
            raise HTTPException(status_code=401, detail="User not found")
        
        return User(**user_data)
        
    except Exception as e:
        logger.error(f"[WS-AUTH-ERROR] WebSocket authentication failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.websocket("/ws/games/{game_id}")
async def websocket_game_endpoint(
    websocket: WebSocket,
    game_id: str,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time game synchronization
    
    Clients should connect with: ws://localhost:1313/ws/games/{game_id}?token={jwt_token}
    """
    user = None
    
    try:
        # Authenticate user from token
        user = await get_websocket_user(token)
        
        # Verify user has access to this game
        game = await game_service.get_game(game_id, include_players=True)
        if not game:
            await websocket.close(code=4004, reason="Game not found")
            return
        
        # Check if user is part of the game
        user_in_game = (
            game.host_id == user.id or
            any(player.id == user.id for player in game.players)
        )
        
        if not user_in_game:
            await websocket.close(code=4003, reason="Access denied to game")
            return
        
        # Connect user to game
        await ws_manager.connect(websocket, game_id, user)
        
        logger.info(f"[WS-GAME-001] WebSocket connection established", extra={
            "game_id": game_id,
            "user_id": user.id,
            "game_name": game.name
        })
        
        # Listen for messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                await handle_websocket_message(websocket, game_id, message)
                
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[WS-GAME-ERROR] Error in WebSocket loop", extra={
                    "game_id": game_id,
                    "user_id": user.id if user else None,
                    "error": str(e)
                })
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Internal server error"
                }))
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[WS-GAME-ERROR] WebSocket connection error", extra={
            "game_id": game_id,
            "user_id": user.id if user else None,
            "error": str(e)
        })
        try:
            await websocket.close(code=4000, reason="Internal server error")
        except:
            pass
    
    finally:
        # Handle disconnection
        if user:
            disconnect_message = ws_manager.disconnect(websocket)
            
            # Broadcast player left message if we have the info
            if disconnect_message:
                try:
                    await ws_manager.broadcast_to_game(game_id, disconnect_message)
                except Exception as e:
                    logger.warning(f"[WS-DISCONNECT-WARN] Failed to broadcast disconnect: {e}")


@router.get("/ws/games/{game_id}/stats")
async def get_game_websocket_stats(
    game_id: str,
    current_user: User = Depends(lambda: None)  # TODO: Add proper auth dependency
):
    """Get WebSocket connection statistics for a game"""
    try:
        connection_count = ws_manager.get_game_connection_count(game_id)
        total_connections = ws_manager.get_total_connections()
        
        return {
            "game_id": game_id,
            "active_connections": connection_count,
            "total_system_connections": total_connections
        }
    
    except Exception as e:
        logger.error(f"[WS-STATS-ERROR] Error getting WebSocket stats", extra={
            "game_id": game_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to get WebSocket stats")


@router.post("/ws/games/{game_id}/broadcast")
async def broadcast_to_game(
    game_id: str,
    message: dict,
    current_user: User = Depends(lambda: None)  # TODO: Add proper auth dependency
):
    """
    Broadcast a message to all connected clients in a game
    This is useful for triggering real-time updates from REST API endpoints
    """
    try:
        # Verify game exists and user has permission
        game = await game_service.get_game(game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        # TODO: Add proper authorization check
        # For now, allow any authenticated user to broadcast
        
        await ws_manager.broadcast_to_game(game_id, message)
        
        logger.info(f"[WS-BROADCAST-API-001] Broadcasted message via API", extra={
            "game_id": game_id,
            "message_type": message.get("type"),
            "connections": ws_manager.get_game_connection_count(game_id)
        })
        
        return {
            "success": True,
            "message": "Message broadcasted successfully",
            "connections_reached": ws_manager.get_game_connection_count(game_id)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WS-BROADCAST-API-ERROR] Error broadcasting message", extra={
            "game_id": game_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to broadcast message")