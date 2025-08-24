-- MED-002 Fix: Database Performance Optimization - Strategic Indexing
-- This migration adds strategic indexes for frequently queried fields to eliminate N+1 patterns
-- Created: 2025-08-24
-- Issue: MED-002 - Database Query Optimization

begin;

-- Games table optimization indexes
-- These indexes optimize the most frequently executed queries in game_service.py

-- Optimize user game queries (get_user_games)
CREATE INDEX IF NOT EXISTS idx_games_host_id ON public.games(host_id);

-- Optimize status-based filtering (active games, waiting games, etc.)
CREATE INDEX IF NOT EXISTS idx_games_status ON public.games(status);

-- Optimize room code lookups (join by room code)  
CREATE INDEX IF NOT EXISTS idx_games_room_code ON public.games(room_code);

-- Optimize playlist-based game queries
CREATE INDEX IF NOT EXISTS idx_games_playlist_id ON public.games(playlist_id);

-- Composite index for complex queries (status + host_id)
CREATE INDEX IF NOT EXISTS idx_games_status_host_id ON public.games(status, host_id);

-- Game players table (junction table) optimization
-- These eliminate N+1 patterns in player-game relationship queries

-- Optimize player game lookups (which games is user in)
CREATE INDEX IF NOT EXISTS idx_game_players_user_id ON public.game_players(user_id);

-- Optimize game player listings (who is in this game)
CREATE INDEX IF NOT EXISTS idx_game_players_game_id ON public.game_players(game_id);

-- Composite index for game-user relationship checks
CREATE INDEX IF NOT EXISTS idx_game_players_composite ON public.game_players(game_id, user_id);

-- Playlists table optimization
-- Optimize playlist ownership and Spotify ID lookups

-- Optimize user playlist queries
CREATE INDEX IF NOT EXISTS idx_playlists_owner_id ON public.playlists(owner_id);

-- Optimize Spotify ID lookups for playlist resolution
CREATE INDEX IF NOT EXISTS idx_playlists_spotify_id ON public.playlists(spotify_id);

-- Playlist tracks table optimization
-- Optimize track listing and counting queries

-- Optimize playlist track listings and counts
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist_id ON public.playlist_tracks(playlist_id);

-- Bingo cards table optimization
-- Optimize card retrieval and game-user card lookups

-- Optimize game card queries
CREATE INDEX IF NOT EXISTS idx_bingo_cards_game_id ON public.bingo_cards(game_id);

-- Optimize user card queries
CREATE INDEX IF NOT EXISTS idx_bingo_cards_user_id ON public.bingo_cards(user_id);

-- Composite index for game-user card lookups
CREATE INDEX IF NOT EXISTS idx_bingo_cards_composite ON public.bingo_cards(game_id, user_id);

-- Users table optimization
-- Optimize Spotify user lookups

-- Optimize Spotify user authentication lookups
CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON public.users(spotify_id);

commit;
