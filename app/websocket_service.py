"""
WebSocket Service for Foute Muziek Bingo
Handles real-time game synchronization between players
"""
import json
import logging
from typing import Dict, List, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from app.models import User, Game, GameStatus
from app.auth_service import auth_service
from app.game_service import game_service
from app.database import database

logger = logging.getLogger("music_bingo")


class WebSocketConnectionManager:
    """
    Manages WebSocket connections for real-time game synchronization
    """
    
    def __init__(self):
        # game_id -> set of websocket connections
        self.game_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> user_id mapping
        self.connection_users: Dict[WebSocket, str] = {}
        # websocket -> game_id mapping  
        self.connection_games: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, game_id: str, user: User):
        """Accept a new WebSocket connection for a game"""
        await websocket.accept()
        
        # Initialize game connections if not exists
        if game_id not in self.game_connections:
            self.game_connections[game_id] = set()
        
        # Add connection to game
        self.game_connections[game_id].add(websocket)
        self.connection_users[websocket] = user.id
        self.connection_games[websocket] = game_id
        
        logger.info(f"[WS-CONNECT-001] User connected to game", extra={
            "user_id": user.id,
            "game_id": game_id,
            "user_name": user.display_name,
            "total_connections": len(self.game_connections[game_id])
        })
        
        # Send initial game state
        await self._send_game_state(websocket, game_id)
        
        # Notify other players about new connection
        await self.broadcast_to_game(game_id, {
            "type": "player_joined",
            "user": {
                "id": user.id,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, exclude_websocket=websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        user_id = self.connection_users.get(websocket)
        game_id = self.connection_games.get(websocket)
        
        if game_id and websocket in self.game_connections.get(game_id, set()):
            self.game_connections[game_id].remove(websocket)
            
            # Clean up empty game connections
            if not self.game_connections[game_id]:
                del self.game_connections[game_id]
        
        # Clean up mappings
        self.connection_users.pop(websocket, None)
        self.connection_games.pop(websocket, None)
        
        logger.info(f"[WS-DISCONNECT-001] User disconnected from game", extra={
            "user_id": user_id,
            "game_id": game_id,
            "remaining_connections": len(self.game_connections.get(game_id, []))
        })
        
        # Notify other players about disconnection (if we have user info)
        if game_id and user_id:
            # Note: We can't await here since this might be called in a non-async context
            # The broadcast will be handled by the calling code
            return {
                "type": "player_left",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def broadcast_to_game(self, game_id: str, message: dict, exclude_websocket: WebSocket = None):
        """Broadcast a message to all connections in a game"""
        if game_id not in self.game_connections:
            return
        
        connections = self.game_connections[game_id].copy()
        disconnected = []
        
        for websocket in connections:
            if websocket == exclude_websocket:
                continue
                
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"[WS-BROADCAST-WARN] Failed to send to connection", extra={
                    "game_id": game_id,
                    "error": str(e)
                })
                disconnected.append(websocket)
        
        # Clean up failed connections
        for websocket in disconnected:
            self.disconnect(websocket)
        
        logger.debug(f"[WS-BROADCAST-001] Broadcasted message to game", extra={
            "game_id": game_id,
            "message_type": message.get("type"),
            "sent_to": len(connections) - len(disconnected) - (1 if exclude_websocket else 0),
            "failed": len(disconnected)
        })
    
    async def send_to_user(self, game_id: str, user_id: str, message: dict):
        """Send a message to a specific user in a game"""
        if game_id not in self.game_connections:
            return False
        
        for websocket in self.game_connections[game_id]:
            if self.connection_users.get(websocket) == user_id:
                try:
                    await websocket.send_text(json.dumps(message))
                    logger.debug(f"[WS-SEND-USER-001] Sent message to user", extra={
                        "game_id": game_id,
                        "user_id": user_id,
                        "message_type": message.get("type")
                    })
                    return True
                except Exception as e:
                    logger.warning(f"[WS-SEND-USER-WARN] Failed to send to user", extra={
                        "game_id": game_id,
                        "user_id": user_id,
                        "error": str(e)
                    })
                    self.disconnect(websocket)
                    return False
        
        return False
    
    async def _send_game_state(self, websocket: WebSocket, game_id: str):
        """Send current game state to a WebSocket connection"""
        try:
            game = await game_service.get_game(game_id, include_playlist=True, include_players=True)
            if not game:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Game not found"
                }))
                return
            
            # Send game state
            await websocket.send_text(json.dumps({
                "type": "game_state",
                "game": {
                    "id": game.id,
                    "name": game.name,
                    "description": game.description,
                    "status": game.status.value,
                    "room_code": game.room_code,
                    "max_players": game.max_players,
                    "current_players": len(game.players),
                    "is_private": game.is_private,
                    "host_id": game.host_id,
                    "current_track_index": game.current_track_index,
                    "players": [
                        {
                            "id": player.id,
                            "display_name": player.display_name,
                            "avatar_url": player.avatar_url
                        }
                        for player in game.players
                    ],
                    "playlist": {
                        "id": game.playlist.id,
                        "name": game.playlist.name,
                        "total_tracks": game.playlist.total_tracks
                    } if game.playlist else None
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
        except Exception as e:
            logger.error(f"[WS-STATE-ERROR] Error sending game state", extra={
                "game_id": game_id,
                "error": str(e)
            })
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to load game state"
            }))
    
    def get_game_connection_count(self, game_id: str) -> int:
        """Get number of active connections for a game"""
        return len(self.game_connections.get(game_id, []))
    
    def get_total_connections(self) -> int:
        """Get total number of active connections"""
        return sum(len(connections) for connections in self.game_connections.values())


# Global WebSocket manager instance
ws_manager = WebSocketConnectionManager()


async def handle_websocket_message(websocket: WebSocket, game_id: str, message: dict):
    """Handle incoming WebSocket messages"""
    message_type = message.get("type")
    user_id = ws_manager.connection_users.get(websocket)
    
    if not user_id:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "User not authenticated"
        }))
        return
    
    logger.debug(f"[WS-MESSAGE-001] Received WebSocket message", extra={
        "game_id": game_id,
        "user_id": user_id,
        "message_type": message_type
    })
    
    try:
        if message_type == "ping":
            await websocket.send_text(json.dumps({
                "type": "pong",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
        
        elif message_type == "track_marked":
            # Handle track marking with real-time updates
            track_id = message.get("track_id")
            if track_id:
                # Update game state through service
                result = await game_service.mark_track(game_id, user_id, track_id)
                
                # Broadcast track marking to all players
                await ws_manager.broadcast_to_game(game_id, {
                    "type": "track_marked",
                    "user_id": user_id,
                    "track_id": track_id,
                    "position": result.get("position"),
                    "bingo": result.get("bingo", False),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                # If bingo was achieved, send special notification
                if result.get("bingo"):
                    await ws_manager.broadcast_to_game(game_id, {
                        "type": "bingo_achieved",
                        "user_id": user_id,
                        "patterns": result.get("patterns", []),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
        
        elif message_type == "game_status_update":
            # Handle game status changes (start, pause, etc.)
            new_status = message.get("status")
            if new_status:
                # This would typically be handled through REST API
                # WebSocket just broadcasts the update
                await ws_manager.broadcast_to_game(game_id, {
                    "type": "game_status_changed",
                    "status": new_status,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, exclude_websocket=websocket)
        
        else:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            }))
    
    except Exception as e:
        logger.error(f"[WS-MESSAGE-ERROR] Error handling WebSocket message", extra={
            "game_id": game_id,
            "user_id": user_id,
            "message_type": message_type,
            "error": str(e)
        })
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Failed to process message"
        }))