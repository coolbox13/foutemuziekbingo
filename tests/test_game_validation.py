"""
Test suite for game validation functionality (CRIT-001 fix)

This module tests the new bulk validation system that replaces
the frontend validation loops that caused API storms.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.models import (
    GameValidationResult, 
    GameValidationStatus,
    BulkGameValidationRequest,
    BulkGameValidationResponse,
    GameExistenceCheck,
    GameStatus,
    User
)
from app.game_service import game_service
from fastapi.testclient import TestClient
from fastapi import HTTPException


@pytest.fixture
def mock_user():
    """Create a mock user for testing"""
    return User(
        id="test-user-123",
        spotify_id="spotify123",
        display_name="Test User",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_games_data():
    """Sample games data for testing"""
    return [
        {
            "id": "game-1",
            "name": "Test Game 1",
            "host_id": "test-user-123",
            "playlist_id": "playlist-1",
            "status": "waiting",
            "is_private": False,
            "created_at": "2025-01-01T10:00:00Z",
            "updated_at": "2025-01-01T10:00:00Z"
        },
        {
            "id": "game-2", 
            "name": "Test Game 2",
            "host_id": "other-user",
            "playlist_id": "playlist-2",
            "status": "in_progress",
            "is_private": True,
            "created_at": "2025-01-01T11:00:00Z",
            "updated_at": "2025-01-01T11:00:00Z"
        },
        {
            "id": "game-3",
            "name": "Test Game 3", 
            "host_id": "test-user-123",
            "playlist_id": None,  # No playlist
            "status": "waiting",
            "is_private": False,
            "created_at": "2025-01-01T12:00:00Z",
            "updated_at": "2025-01-01T12:00:00Z"
        }
    ]


@pytest.fixture
def sample_playlists_data():
    """Sample playlists data for testing"""
    return [
        {
            "id": "playlist-1",
            "name": "Good Playlist",
            "total_tracks": 30
        },
        {
            "id": "playlist-2", 
            "name": "Small Playlist",
            "total_tracks": 10  # Insufficient for bingo
        }
    ]


class TestGameValidationService:
    """Test the game validation service methods"""
    
    @pytest.mark.asyncio
    async def test_validate_game_valid(self, mock_user, sample_games_data, sample_playlists_data):
        """Test validating a valid game"""
        with patch('app.game_service.database') as mock_db:
            # Mock database responses
            mock_db.get_record.side_effect = [
                sample_games_data[0],  # Game exists
                sample_playlists_data[0]  # Playlist exists with enough tracks
            ]
            mock_db.query_records.side_effect = [
                [{"playlist_id": "playlist-1", "id": "track1"}] * 30  # 30 tracks
            ]
            
            result = await game_service.validate_game(
                game_id="game-1",
                user_id=mock_user.id,
                include_track_count=True
            )
            
            assert result.game_id == "game-1"
            assert result.status == GameValidationStatus.VALID
            assert result.exists is True
            assert result.has_playlist is True
            assert result.track_count == 30
            assert result.can_generate_cards is True
            assert result.error_message is None
    
    @pytest.mark.asyncio
    async def test_validate_game_not_found(self, mock_user):
        """Test validating a non-existent game"""
        with patch('app.game_service.database') as mock_db:
            mock_db.get_record.return_value = None
            
            result = await game_service.validate_game(
                game_id="nonexistent-game",
                user_id=mock_user.id,
                include_track_count=True
            )
            
            assert result.game_id == "nonexistent-game"
            assert result.status == GameValidationStatus.NOT_FOUND
            assert result.exists is False
            assert result.has_playlist is False
            assert result.track_count == 0
            assert result.can_generate_cards is False
            assert result.error_message == "Game not found in database"
    
    @pytest.mark.asyncio
    async def test_validate_game_no_playlist(self, mock_user, sample_games_data):
        """Test validating a game without a playlist"""
        with patch('app.game_service.database') as mock_db:
            mock_db.get_record.side_effect = [
                sample_games_data[2],  # Game without playlist
                None  # No playlist found
            ]
            
            result = await game_service.validate_game(
                game_id="game-3",
                user_id=mock_user.id,
                include_track_count=True
            )
            
            assert result.game_id == "game-3"
            assert result.status == GameValidationStatus.NO_PLAYLIST
            assert result.exists is True
            assert result.has_playlist is False
            assert result.track_count == 0
            assert result.can_generate_cards is False
            assert result.error_message == "Game has no valid playlist"
    
    @pytest.mark.asyncio
    async def test_validate_game_insufficient_tracks(self, mock_user, sample_games_data, sample_playlists_data):
        """Test validating a game with insufficient tracks"""
        with patch('app.game_service.database') as mock_db:
            mock_db.get_record.side_effect = [
                sample_games_data[1],  # Game exists
                sample_playlists_data[1]  # Playlist with only 10 tracks
            ]
            mock_db.query_records.return_value = [{"id": "track1"}] * 10  # Only 10 tracks
            
            result = await game_service.validate_game(
                game_id="game-2",
                user_id=mock_user.id,
                include_track_count=True
            )
            
            assert result.game_id == "game-2"
            assert result.status == GameValidationStatus.INSUFFICIENT_TRACKS
            assert result.exists is True
            assert result.has_playlist is True
            assert result.track_count == 10
            assert result.can_generate_cards is False
            assert "only 10 tracks" in result.error_message
    
    @pytest.mark.asyncio
    async def test_validate_game_access_denied(self, sample_games_data):
        """Test validating a private game without access"""
        with patch('app.game_service.database') as mock_db:
            mock_db.get_record.return_value = sample_games_data[1]  # Private game
            mock_db.query_records.return_value = []  # User is not a player
            
            result = await game_service.validate_game(
                game_id="game-2",
                user_id="different-user",
                include_track_count=True
            )
            
            assert result.game_id == "game-2"
            assert result.status == GameValidationStatus.INVALID
            assert result.exists is True
            assert result.has_playlist is False
            assert result.can_generate_cards is False
            assert result.error_message == "Access denied to private game"

    @pytest.mark.asyncio
    async def test_validate_games_bulk_success(self, mock_user, sample_games_data, sample_playlists_data):
        """Test bulk validation with mixed results"""
        game_ids = ["game-1", "game-2", "nonexistent"]
        
        with patch('app.game_service.database') as mock_db:
            # Mock bulk query responses
            mock_db.execute_query.side_effect = [
                sample_games_data[:2],  # Games query - only first 2 exist
                [],  # Player games query - no participation
                sample_playlists_data,  # Playlists query
                [{"playlist_id": "playlist-1", "track_count": 30}]  # Track counts
            ]
            
            response = await game_service.validate_games_bulk(
                game_ids=game_ids,
                user_id=mock_user.id,
                include_track_count=True
            )
            
            assert response.success is True
            assert response.total_requested == 3
            assert response.total_processed == 3
            assert len(response.validation_results) == 3
            
            # Check summary counts
            assert response.summary["valid"] >= 1
            assert response.summary["not_found"] >= 1
            assert response.processing_time_ms is not None
    
    @pytest.mark.asyncio
    async def test_validate_games_bulk_empty_list(self, mock_user):
        """Test bulk validation with empty game list"""
        response = await game_service.validate_games_bulk(
            game_ids=[],
            user_id=mock_user.id,
            include_track_count=True
        )
        
        assert response.success is True
        assert response.total_requested == 0
        assert response.total_processed == 0
        assert len(response.validation_results) == 0

    @pytest.mark.asyncio
    async def test_validate_games_bulk_limit(self, mock_user):
        """Test bulk validation respects 100 game limit"""
        large_game_list = [f"game-{i}" for i in range(150)]
        
        with patch('app.game_service.database') as mock_db:
            mock_db.execute_query.return_value = []
            
            response = await game_service.validate_games_bulk(
                game_ids=large_game_list,
                user_id=mock_user.id,
                include_track_count=True
            )
            
            # Should be truncated to 100
            assert response.total_requested == 100
    
    @pytest.mark.asyncio 
    async def test_check_game_existence_exists(self, mock_user, sample_games_data):
        """Test game existence check for existing game"""
        with patch('app.game_service.database') as mock_db:
            mock_db.get_record.return_value = sample_games_data[0]
            mock_db.query_records.return_value = []  # Not a player
            
            result = await game_service.check_game_existence(
                game_id="game-1",
                user_id=mock_user.id
            )
            
            assert result.game_id == "game-1"
            assert result.exists is True
            assert result.accessible is True  # Owner
            assert result.status == GameStatus.WAITING
    
    @pytest.mark.asyncio
    async def test_check_game_existence_not_found(self, mock_user):
        """Test game existence check for non-existent game"""
        with patch('app.game_service.database') as mock_db:
            mock_db.get_record.return_value = None
            
            result = await game_service.check_game_existence(
                game_id="nonexistent",
                user_id=mock_user.id
            )
            
            assert result.game_id == "nonexistent"
            assert result.exists is False
            assert result.accessible is False
            assert result.status is None


class TestGameValidationAPI:
    """Test the game validation API endpoints"""
    
    def test_validate_games_endpoint_success(self, mock_user):
        """Test the GET /api/games/validate endpoint"""
        from app.fastapi_app import create_app
        app = create_app()
        client = TestClient(app)
        
        with patch('app.auth_service.get_current_user', return_value=mock_user):
            with patch('app.game_service.game_service.validate_game') as mock_validate:
                mock_validate.return_value = GameValidationResult(
                    game_id="game-1",
                    status=GameValidationStatus.VALID,
                    exists=True,
                    has_playlist=True,
                    track_count=30,
                    can_generate_cards=True
                )
                
                response = client.get(
                    "/game/api/games/validate?game_ids=game-1,game-2&include_track_count=true"
                )
                
                assert response.status_code == 200
                data = response.json()
                assert len(data) >= 1
                assert data[0]["game_id"] == "game-1"
                assert data[0]["status"] == "valid"
    
    def test_validate_games_endpoint_no_games(self, mock_user):
        """Test validation endpoint with no game IDs"""
        from app.fastapi_app import create_app
        app = create_app()
        client = TestClient(app)
        
        with patch('app.auth_service.get_current_user', return_value=mock_user):
            response = client.get("/game/api/games/validate?game_ids=")
            
            assert response.status_code == 400
            assert "No game IDs provided" in response.json()["detail"]
    
    def test_validate_games_batch_endpoint_success(self, mock_user):
        """Test the POST /api/games/validate-batch endpoint"""
        from app.fastapi_app import create_app
        app = create_app()
        client = TestClient(app)
        
        request_data = {
            "game_ids": ["game-1", "game-2"],
            "include_track_count": True,
            "filter_status": None
        }
        
        mock_response = BulkGameValidationResponse(
            success=True,
            total_requested=2,
            total_processed=2,
            validation_results=[],
            summary={"valid": 1, "invalid": 1},
            timestamp=datetime.now(timezone.utc),
            processing_time_ms=50.0
        )
        
        with patch('app.auth_service.get_current_user', return_value=mock_user):
            with patch('app.game_service.game_service.validate_games_bulk', return_value=mock_response):
                response = client.post(
                    "/game/api/games/validate-batch",
                    json=request_data
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["total_requested"] == 2
                assert data["total_processed"] == 2
    
    def test_validate_games_batch_endpoint_too_many(self, mock_user):
        """Test batch endpoint with too many games"""
        from app.fastapi_app import create_app
        app = create_app()
        client = TestClient(app)
        
        request_data = {
            "game_ids": [f"game-{i}" for i in range(150)],  # Too many
            "include_track_count": True
        }
        
        with patch('app.auth_service.get_current_user', return_value=mock_user):
            response = client.post(
                "/game/api/games/validate-batch",
                json=request_data
            )
            
            assert response.status_code == 400
            assert "Too many game IDs" in response.json()["detail"]
    
    def test_check_game_existence_endpoint(self, mock_user):
        """Test the GET /api/games/{game_id}/exists endpoint"""
        from app.fastapi_app import create_app
        app = create_app()
        client = TestClient(app)
        
        mock_result = GameExistenceCheck(
            game_id="game-1",
            exists=True,
            accessible=True,
            status=GameStatus.WAITING
        )
        
        with patch('app.auth_service.get_current_user', return_value=mock_user):
            with patch('app.game_service.game_service.check_game_existence', return_value=mock_result):
                response = client.get("/game/api/games/game-1/exists")
                
                assert response.status_code == 200
                data = response.json()
                assert data["game_id"] == "game-1"
                assert data["exists"] is True
                assert data["accessible"] is True


class TestPerformanceImprovements:
    """Test that the new system performs better than the old one"""
    
    @pytest.mark.asyncio
    async def test_bulk_validation_performance(self, mock_user, sample_games_data):
        """Test that bulk validation is faster than individual calls"""
        game_ids = ["game-1", "game-2", "game-3"] * 10  # 30 games
        
        with patch('app.game_service.database') as mock_db:
            mock_db.execute_query.return_value = sample_games_data
            
            import time
            start_time = time.time()
            
            response = await game_service.validate_games_bulk(
                game_ids=game_ids,
                user_id=mock_user.id,
                include_track_count=True
            )
            
            end_time = time.time()
            
            # Should complete quickly with bulk queries
            assert (end_time - start_time) < 1.0  # Less than 1 second
            assert response.processing_time_ms < 1000  # Less than 1000ms
            assert response.total_requested == 30
    
    def test_no_circuit_breaker_code(self):
        """Verify that circuit breaker code has been removed from frontend"""
        import os
        dashboard_path = "/Users/hermanhello/Documents/FouteMuziekBingo/static/js/dashboard.js"
        
        if os.path.exists(dashboard_path):
            with open(dashboard_path, 'r') as f:
                content = f.read()
                
                # Ensure no circuit breaker patterns exist
                assert "MAX_VALIDATION_ATTEMPTS" not in content
                assert "slice(0, 3)" not in content
                assert "EMERGENCY CIRCUIT BREAKER" not in content
                assert "prevent API storm" not in content
                
                # Ensure new functions exist
                assert "validateGamesBatch" in content
                assert "findValidGameFromList" in content
                assert "checkGameExists" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
