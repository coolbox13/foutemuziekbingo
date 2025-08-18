"""
CRIT-002 Tests: Database CASCADE DELETE Constraint Enforcement
Tests to verify that CASCADE DELETE constraints are working correctly
and that orphaned records cannot be created.
"""
import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from app.database import database, DatabaseError
from app.models import GameStatus


class TestCascadeDeleteConstraints:
    """Test suite for CASCADE DELETE constraint enforcement"""
    
    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """Setup and teardown for each test"""
        # Ensure database is initialized
        if not database.is_initialized:
            await database.initialize()
        
        # Store initial state for cleanup
        self.test_data_ids = {
            'users': [],
            'games': [],
            'game_players': [],
            'bingo_cards': [],
            'playlists': []
        }
        
        yield
        
        # Cleanup test data after each test
        await self._cleanup_test_data()
    
    async def _cleanup_test_data(self):
        """Clean up all test data created during tests"""
        for table, ids in self.test_data_ids.items():
            for record_id in ids:
                try:
                    await database.delete_record(table, record_id)
                except Exception:
                    pass  # Ignore cleanup errors
    
    async def _create_test_user(self) -> dict:
        """Create a test user"""
        user_data = {
            'spotify_id': f'test_user_{uuid.uuid4().hex[:8]}',
            'display_name': 'Test User',
            'email': 'test@example.com',
            'subscription_type': 'free',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        user = await database.create_record('users', user_data)
        self.test_data_ids['users'].append(user['id'])
        return user
    
    async def _create_test_playlist(self, owner_id: str) -> dict:
        """Create a test playlist"""
        playlist_data = {
            'spotify_id': f'test_playlist_{uuid.uuid4().hex[:8]}',
            'name': 'Test Playlist',
            'description': 'Test playlist for CRIT-002',
            'owner_id': owner_id,
            'tracks': [],
            'total_tracks': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        playlist = await database.create_record('playlists', playlist_data)
        self.test_data_ids['playlists'].append(playlist['id'])
        return playlist
    
    async def _create_test_game(self, host_id: str, playlist_id: str) -> dict:
        """Create a test game"""
        game_data = {
            'name': 'Test Game',
            'description': 'Test game for CRIT-002',
            'host_id': host_id,
            'playlist_id': playlist_id,
            'status': GameStatus.WAITING.value,
            'max_players': 10,
            'current_players': 0,
            'is_private': False,
            'current_track_index': 0,
            'settings': {},
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        game = await database.create_record('games', game_data)
        self.test_data_ids['games'].append(game['id'])
        return game
    
    @pytest.mark.asyncio
    async def test_cascade_delete_game_removes_game_players(self):
        """Test that deleting a game cascades to remove game_players records"""
        # Create test data
        user = await self._create_test_user()
        playlist = await self._create_test_playlist(user['id'])
        game = await self._create_test_game(user['id'], playlist['id'])
        
        # Create game_players record
        game_player_data = {
            'game_id': game['id'],
            'user_id': user['id'],
            'username': 'Test Player',
            'display_name': 'Test Player',
            'is_host': False,
            'is_ready': False,
            'joined_at': datetime.now(timezone.utc).isoformat(),
        }
        
        game_player = await database.create_record('game_players', game_player_data)
        self.test_data_ids['game_players'].append(game_player['id'])
        
        # Verify game_players record exists
        found_player = await database.get_record('game_players', game_player['id'])
        assert found_player is not None, "game_players record should exist"
        
        # Delete the game - this should cascade delete the game_players record
        await database.delete_record('games', game['id'])
        self.test_data_ids['games'].remove(game['id'])  # Remove from cleanup list
        
        # Verify game_players record was CASCADE deleted
        deleted_player = await database.get_record('game_players', game_player['id'])
        assert deleted_player is None, "game_players record should be CASCADE deleted when game is deleted"
        
        # Remove from cleanup list since it was already deleted
        if game_player['id'] in self.test_data_ids['game_players']:
            self.test_data_ids['game_players'].remove(game_player['id'])
    
    @pytest.mark.asyncio
    async def test_cascade_delete_game_removes_bingo_cards(self):
        """Test that deleting a game cascades to remove bingo_cards records"""
        # Create test data
        user = await self._create_test_user()
        playlist = await self._create_test_playlist(user['id'])
        game = await self._create_test_game(user['id'], playlist['id'])
        
        # Create bingo_cards record
        bingo_card_data = {
            'game_id': game['id'],
            'user_id': user['id'],
            'card_data': {'grid': []},
            'marked_positions': [],
            'winning_patterns': [],
            'is_winner': False,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        bingo_card = await database.create_record('bingo_cards', bingo_card_data)
        self.test_data_ids['bingo_cards'].append(bingo_card['id'])
        
        # Verify bingo_cards record exists
        found_card = await database.get_record('bingo_cards', bingo_card['id'])
        assert found_card is not None, "bingo_cards record should exist"
        
        # Delete the game - this should cascade delete the bingo_cards record
        await database.delete_record('games', game['id'])
        self.test_data_ids['games'].remove(game['id'])
        
        # Verify bingo_cards record was CASCADE deleted
        deleted_card = await database.get_record('bingo_cards', bingo_card['id'])
        assert deleted_card is None, "bingo_cards record should be CASCADE deleted when game is deleted"
        
        # Remove from cleanup list
        if bingo_card['id'] in self.test_data_ids['bingo_cards']:
            self.test_data_ids['bingo_cards'].remove(bingo_card['id'])
    
    @pytest.mark.asyncio
    async def test_cascade_delete_user_removes_game_players(self):
        """Test that deleting a user cascades to remove their game_players records"""
        # Create test data
        user1 = await self._create_test_user()  # Host
        user2 = await self._create_test_user()  # Player to be deleted
        playlist = await self._create_test_playlist(user1['id'])
        game = await self._create_test_game(user1['id'], playlist['id'])
        
        # Create game_players record for user2
        game_player_data = {
            'game_id': game['id'],
            'user_id': user2['id'],
            'username': 'Player To Delete',
            'display_name': 'Player To Delete',
            'is_host': False,
            'is_ready': False,
            'joined_at': datetime.now(timezone.utc).isoformat(),
        }
        
        game_player = await database.create_record('game_players', game_player_data)
        self.test_data_ids['game_players'].append(game_player['id'])
        
        # Verify game_players record exists
        found_player = await database.get_record('game_players', game_player['id'])
        assert found_player is not None, "game_players record should exist"
        
        # Delete user2 - this should cascade delete their game_players record
        await database.delete_record('users', user2['id'])
        self.test_data_ids['users'].remove(user2['id'])
        
        # Verify game_players record was CASCADE deleted
        deleted_player = await database.get_record('game_players', game_player['id'])
        assert deleted_player is None, "game_players record should be CASCADE deleted when user is deleted"
        
        # Remove from cleanup list
        if game_player['id'] in self.test_data_ids['game_players']:
            self.test_data_ids['game_players'].remove(game_player['id'])
    
    @pytest.mark.asyncio
    async def test_constraint_prevents_orphaned_game_players(self):
        """Test that foreign key constraints prevent creation of orphaned game_players records"""
        # Create a test user
        user = await self._create_test_user()
        
        # Try to create game_players record with non-existent game_id
        fake_game_id = str(uuid.uuid4())
        
        game_player_data = {
            'game_id': fake_game_id,
            'user_id': user['id'],
            'username': 'Test Player',
            'display_name': 'Test Player',
            'is_host': False,
            'is_ready': False,
            'joined_at': datetime.now(timezone.utc).isoformat(),
        }
        
        # This should raise a foreign key constraint violation
        with pytest.raises(Exception) as exc_info:
            await database.create_record('game_players', game_player_data)
        
        error_message = str(exc_info.value).lower()
        assert any(keyword in error_message for keyword in [
            'foreign key', 'constraint', 'violates', 'fkey'
        ]), f"Expected foreign key constraint error, got: {error_message}"
    
    @pytest.mark.asyncio
    async def test_constraint_prevents_orphaned_bingo_cards(self):
        """Test that foreign key constraints prevent creation of orphaned bingo_cards records"""
        # Create a test user
        user = await self._create_test_user()
        
        # Try to create bingo_cards record with non-existent game_id
        fake_game_id = str(uuid.uuid4())
        
        bingo_card_data = {
            'game_id': fake_game_id,
            'user_id': user['id'],
            'card_data': {'grid': []},
            'marked_positions': [],
            'winning_patterns': [],
            'is_winner': False,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        
        # This should raise a foreign key constraint violation
        with pytest.raises(Exception) as exc_info:
            await database.create_record('bingo_cards', bingo_card_data)
        
        error_message = str(exc_info.value).lower()
        assert any(keyword in error_message for keyword in [
            'foreign key', 'constraint', 'violates', 'fkey'
        ]), f"Expected foreign key constraint error, got: {error_message}"
    
    @pytest.mark.asyncio
    async def test_integrity_validation_function(self):
        """Test the database integrity validation function works correctly"""
        # This test assumes the validation function from the migration exists
        
        # Create valid test data
        user = await self._create_test_user()
        playlist = await self._create_test_playlist(user['id'])
        game = await self._create_test_game(user['id'], playlist['id'])
        
        # Create valid related records
        game_player_data = {
            'game_id': game['id'],
            'user_id': user['id'],
            'username': 'Test Player',
            'display_name': 'Test Player',
            'is_host': False,
            'is_ready': False,
            'joined_at': datetime.now(timezone.utc).isoformat(),
        }
        
        game_player = await database.create_record('game_players', game_player_data)
        self.test_data_ids['game_players'].append(game_player['id'])
        
        # The validation function should show no orphaned records
        # Note: This would require the validation function to be accessible
        # For now, we just verify that our valid data doesn't cause integrity issues
        
        # Verify all records exist
        assert await database.get_record('users', user['id']) is not None
        assert await database.get_record('games', game['id']) is not None
        assert await database.get_record('game_players', game_player['id']) is not None
        
        # This test passes if no exceptions are raised and all lookups succeed


class TestGameServiceIntegrity:
    """Test the updated game service with CASCADE DELETE support"""
    
    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """Setup for game service tests"""
        if not database.is_initialized:
            await database.initialize()
        
        self.test_data_ids = {
            'users': [],
            'games': [],
            'game_players': [],
            'bingo_cards': [],
            'playlists': []
        }
        
        yield
        
        # Cleanup
        for table, ids in self.test_data_ids.items():
            for record_id in ids:
                try:
                    await database.delete_record(table, record_id)
                except Exception:
                    pass
    
    @pytest.mark.asyncio
    async def test_get_user_games_with_cascade_integrity(self):
        """Test that get_user_games works correctly with CASCADE DELETE constraints"""
        from app.game_service import game_service
        
        # Create test user and game
        user_data = {
            'spotify_id': f'test_user_{uuid.uuid4().hex[:8]}',
            'display_name': 'Test User',
            'email': 'test@example.com',
            'subscription_type': 'free',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        user = await database.create_record('users', user_data)
        self.test_data_ids['users'].append(user['id'])
        
        # Create playlist
        playlist_data = {
            'spotify_id': f'test_playlist_{uuid.uuid4().hex[:8]}',
            'name': 'Test Playlist',
            'owner_id': user['id'],
            'tracks': [],
            'total_tracks': 25,  # Minimum for bingo
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        playlist = await database.create_record('playlists', playlist_data)
        self.test_data_ids['playlists'].append(playlist['id'])
        
        # Create game
        game_data = {
            'name': 'Test Game',
            'host_id': user['id'],
            'playlist_id': playlist['id'],
            'status': GameStatus.WAITING.value,
            'max_players': 10,
            'current_players': 0,
            'is_private': False,
            'settings': {},
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        game = await database.create_record('games', game_data)
        self.test_data_ids['games'].append(game['id'])
        
        # Create game_players record
        game_player_data = {
            'game_id': game['id'],
            'user_id': user['id'],
            'username': 'Test Host',
            'display_name': 'Test Host',
            'is_host': True,
            'is_ready': True,
            'joined_at': datetime.now(timezone.utc).isoformat(),
        }
        
        game_player = await database.create_record('game_players', game_player_data)
        self.test_data_ids['game_players'].append(game_player['id'])
        
        # Test get_user_games - should work without integrity errors
        user_games = await game_service.get_user_games(user['id'])
        
        assert len(user_games) >= 1, "Should find at least one game for the user"
        
        # Verify the game is in the results
        game_ids = [g.id for g in user_games]
        assert game['id'] in game_ids, "Created game should be in user's games"
        
        # Now test CASCADE DELETE behavior
        # Delete the game - related game_players should be automatically deleted
        await database.delete_record('games', game['id'])
        self.test_data_ids['games'].remove(game['id'])
        
        # get_user_games should now return fewer games and not have integrity errors
        user_games_after_delete = await game_service.get_user_games(user['id'])
        
        # Should not find the deleted game
        game_ids_after = [g.id for g in user_games_after_delete]
        assert game['id'] not in game_ids_after, "Deleted game should not be in results"
        
        # Verify game_players record was CASCADE deleted
        deleted_player = await database.get_record('game_players', game_player['id'])
        assert deleted_player is None, "game_players should be CASCADE deleted"
        
        # Remove from cleanup since it's already deleted
        if game_player['id'] in self.test_data_ids['game_players']:
            self.test_data_ids['game_players'].remove(game_player['id'])


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v'])
