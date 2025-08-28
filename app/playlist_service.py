"""
Playlist Service for Foute Muziek Bingo
Manages Spotify playlists with Supabase storage and caching
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from spotipy import Spotify
from app.models import Playlist, Track, User
from app.database import database, DatabaseError
import uuid

logger = logging.getLogger("music_bingo")


class PlaylistError(Exception):
    """Playlist-related errors"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PlaylistService:
    """
    Playlist management service with Supabase integration
    Handles Spotify playlist fetching, caching, and storage
    """

    async def get_user_playlists(
        self, user: User, spotify_client: Spotify
    ) -> List[Playlist]:
        """Get user's playlists with intelligent caching"""
        logger.info(
            "[PLAYLIST-GET-001] Getting playlists for user",
            extra={"user_id": user.id, "spotify_id": user.spotify_id},
        )

        try:
            # First, try to get cached playlists from database
            cached_playlists = await database.query_records(
                "playlists",
                filters={"owner_id": user.id},
                order_by={"column": "updated_at", "ascending": False},
            )

            logger.debug(
                "[PLAYLIST-GET-002] Found cached playlists",
                extra={"user_id": user.id, "cached_count": len(cached_playlists)},
            )

            # Get fresh playlists from Spotify
            spotify_playlists = await self._fetch_spotify_playlists(
                spotify_client, user
            )

            # Compare and update cache as needed
            updated_playlists = await self._sync_playlists_cache(
                user, spotify_playlists, cached_playlists
            )

            logger.info(
                "[PLAYLIST-GET-003] Playlists retrieved successfully",
                extra={"user_id": user.id, "total_playlists": len(updated_playlists)},
            )

            return updated_playlists

        except Exception as e:
            # Fallback: if database/cache fails, return playlists directly from Spotify
            logger.error(
                "[PLAYLIST-GET-ERROR] Error getting user playlists",
                extra={"user_id": user.id, "error": str(e), "error_type": type(e).__name__},
                exc_info=True  # Include full traceback
            )
            try:
                logger.warning(
                    "[PLAYLIST-GET-FALLBACK] Falling back to direct Spotify playlists without caching",
                    extra={"user_id": user.id},
                )
                spotify_playlists = await self._fetch_spotify_playlists(
                    spotify_client, user
                )
                ephemeral: List[Playlist] = []
                for sp_pl in spotify_playlists:
                    total_tracks = sp_pl.get("tracks", {}).get("total", 0)
                    p = Playlist(
                        id=str(uuid.uuid4()),
                        spotify_id=sp_pl["id"],
                        name=sp_pl.get("name", "Unnamed playlist"),
                        description=sp_pl.get("description", ""),
                        owner_id=user.id,
                        tracks=[],
                        total_tracks=total_tracks,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    ephemeral.append(p)
                return ephemeral
            except Exception as inner:
                raise PlaylistError(f"Failed to get playlists: {str(inner)}")

    async def get_playlist_by_id(
        self, playlist_id: str, include_tracks: bool = True
    ) -> Optional[Playlist]:
        """Get specific playlist by ID"""
        try:
            logger.debug(
                "[PLAYLIST-SINGLE-001] Getting playlist by ID",
                extra={"playlist_id": playlist_id, "include_tracks": include_tracks},
            )

            playlist_data = await database.get_record("playlists", playlist_id)
            if not playlist_data:
                return None

            playlist = Playlist(**playlist_data)

            # Include tracks if requested
            if include_tracks:
                tracks_data = await database.query_records(
                    "playlist_tracks",
                    filters={"playlist_id": playlist_id},
                    order_by={"column": "track_order", "ascending": True},
                )

                tracks = []
                for track_data in tracks_data:
                    track = Track(
                        id=track_data["spotify_track_id"],
                        name=track_data["name"],
                        artist=track_data["artist"],
                        album=track_data.get("album"),
                        duration_ms=track_data.get("duration_ms"),
                        preview_url=track_data.get("preview_url"),
                        external_urls=track_data.get("external_urls"),
                        played=False,
                    )
                    tracks.append(track)

                playlist.tracks = tracks
                playlist.total_tracks = len(tracks)

            logger.debug(
                "[PLAYLIST-SINGLE-002] Playlist retrieved successfully",
                extra={
                    "playlist_id": playlist_id,
                    "playlist_name": playlist.name,
                    "track_count": len(playlist.tracks) if include_tracks else 0,
                },
            )

            return playlist

        except Exception as e:
            logger.error(
                "[PLAYLIST-SINGLE-ERROR] Error getting playlist",
                extra={"playlist_id": playlist_id, "error": str(e)},
            )
            return None

    async def get_playlist_by_spotify_id(
        self, spotify_id: str, owner_id: str
    ) -> Optional[Playlist]:
        """Get playlist by Spotify ID and owner"""
        try:
            playlists = await database.query_records(
                "playlists", filters={"spotify_id": spotify_id, "owner_id": owner_id}
            )

            if playlists:
                return await self.get_playlist_by_id(playlists[0]["id"])
            return None

        except Exception as e:
            logger.error(
                "[PLAYLIST-SPOTIFY-ERROR] Error getting playlist by Spotify ID",
                extra={"spotify_id": spotify_id, "owner_id": owner_id, "error": str(e)},
            )
            return None

    async def _fetch_spotify_playlists(
        self, spotify_client: Spotify, user: User
    ) -> List[Dict[str, Any]]:
        """Fetch playlists from Spotify API"""
        logger.debug(
            "[SPOTIFY-FETCH-001] Fetching playlists from Spotify API",
            extra={"user_id": user.id},
        )

        try:
            spotify_playlists = []
            results = spotify_client.current_user_playlists(limit=50)

            while results:
                for playlist in results["items"]:
                    if playlist and playlist.get("id"):
                        # Only include playlists owned by the user or collaborative
                        if playlist["owner"]["id"] == user.spotify_id or playlist.get(
                            "collaborative", False
                        ):
                            spotify_playlists.append(playlist)

                # Handle pagination
                if results["next"]:
                    results = spotify_client.next(results)
                else:
                    break

            logger.debug(
                "[SPOTIFY-FETCH-002] Fetched playlists from Spotify",
                extra={"user_id": user.id, "playlist_count": len(spotify_playlists)},
            )

            return spotify_playlists

        except Exception as e:
            logger.error(
                "[SPOTIFY-FETCH-ERROR] Error fetching from Spotify API",
                extra={"user_id": user.id, "error": str(e)},
            )
            raise PlaylistError(f"Failed to fetch playlists from Spotify: {str(e)}")

    async def _sync_playlists_cache(
        self,
        user: User,
        spotify_playlists: List[Dict[str, Any]],
        cached_playlists: List[Dict[str, Any]],
    ) -> List[Playlist]:
        """Sync Spotify playlists with database cache"""
        logger.debug(
            "[PLAYLIST-SYNC-001] Syncing playlist cache",
            extra={
                "user_id": user.id,
                "spotify_count": len(spotify_playlists),
                "cached_count": len(cached_playlists),
            },
        )

        try:
            # Create lookup for cached playlists
            cached_lookup = {p["spotify_id"]: p for p in cached_playlists}
            synced_playlists = []

            for spotify_playlist in spotify_playlists:
                spotify_id = spotify_playlist["id"]

                # Check if playlist exists in cache
                if spotify_id in cached_lookup:
                    # Update existing playlist if needed
                    cached = cached_lookup[spotify_id]

                    # Check if update is needed (name change, track count change, etc.)
                    spotify_total_tracks = spotify_playlist.get("tracks", {}).get(
                        "total", 0
                    )
                    needs_update = (
                        cached["name"] != spotify_playlist["name"]
                        or cached.get("description")
                        != spotify_playlist.get("description", "")
                        or cached.get("total_tracks", 0) != spotify_total_tracks
                    )

                    if needs_update:
                        logger.debug(
                            "[PLAYLIST-SYNC-002] Updating cached playlist",
                            extra={
                                "playlist_id": cached["id"],
                                "spotify_id": spotify_id,
                                "name": spotify_playlist["name"],
                            },
                        )

                        # Update playlist metadata
                        update_data = {
                            "name": spotify_playlist["name"],
                            "description": spotify_playlist.get("description", ""),
                            "total_tracks": spotify_total_tracks,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }

                        updated_playlist = await database.update_record(
                            "playlists", cached["id"], update_data
                        )

                        # Refresh tracks if track count changed
                        if cached.get("total_tracks", 0) != spotify_total_tracks:
                            await self._refresh_playlist_tracks(
                                updated_playlist["id"], spotify_playlist
                            )

                        synced_playlists.append(Playlist(**updated_playlist))
                    else:
                        # Use cached version
                        synced_playlists.append(Playlist(**cached))
                else:
                    # Create new playlist in cache
                    logger.debug(
                        "[PLAYLIST-SYNC-003] Creating new cached playlist",
                        extra={
                            "spotify_id": spotify_id,
                            "name": spotify_playlist["name"],
                            "user_id": user.id,
                        },
                    )

                    new_playlist = await self._create_cached_playlist(
                        user, spotify_playlist
                    )
                    synced_playlists.append(new_playlist)

            logger.debug(
                "[PLAYLIST-SYNC-004] Playlist sync completed",
                extra={"user_id": user.id, "synced_count": len(synced_playlists)},
            )

            return synced_playlists

        except Exception as e:
            logger.error(
                "[PLAYLIST-SYNC-ERROR] Error syncing playlist cache",
                extra={"user_id": user.id, "error": str(e), "error_type": type(e).__name__},
                exc_info=True  # Include full traceback
            )
            raise PlaylistError(f"Failed to sync playlist cache: {str(e)}")

    async def _create_cached_playlist(
        self, user: User, spotify_playlist: Dict[str, Any]
    ) -> Playlist:
        """Create a new cached playlist from Spotify data"""
        try:
            playlist_data = {
                "spotify_id": spotify_playlist["id"],
                "name": spotify_playlist["name"],
                "description": spotify_playlist.get("description", ""),
                "owner_id": user.id,
                "total_tracks": spotify_playlist.get("tracks", {}).get("total", 0),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            created_playlist = await database.create_record("playlists", playlist_data)

            # Fetch and cache tracks
            await self._refresh_playlist_tracks(
                created_playlist["id"], spotify_playlist
            )

            return Playlist(**created_playlist)

        except Exception as e:
            logger.error(
                "[PLAYLIST-CREATE-ERROR] Error creating cached playlist",
                extra={
                    "spotify_id": spotify_playlist["id"],
                    "user_id": user.id,
                    "error": str(e),
                },
            )
            raise PlaylistError(f"Failed to create cached playlist: {str(e)}")

    async def _refresh_playlist_tracks(
        self, playlist_id: str, spotify_playlist: Dict[str, Any]
    ):
        """Refresh tracks for a playlist"""
        logger.debug(
            "[PLAYLIST-TRACKS-001] Refreshing playlist tracks",
            extra={"playlist_id": playlist_id, "spotify_id": spotify_playlist["id"]},
        )

        try:
            # Clear existing tracks
            await database.query_records(
                "playlist_tracks", filters={"playlist_id": playlist_id}
            )
            # TODO: Implement track deletion - need delete functionality in database service

            # This would typically fetch tracks from Spotify and store them
            # For now, we'll create a placeholder implementation
            tracks_data = []

            # Store placeholder tracks (in production, fetch from Spotify)
            total_tracks = spotify_playlist.get("tracks", {}).get("total", 0)
            for i in range(min(25, total_tracks)):
                track_data = {
                    "playlist_id": playlist_id,
                    "spotify_track_id": f"track_{i}",
                    "name": f"Track {i+1}",
                    "artist": "Artist Name",
                    "album": "Album Name",
                    "track_order": i,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                tracks_data.append(track_data)

            # Store tracks in database
            for track_data in tracks_data:
                await database.create_record("playlist_tracks", track_data)

            logger.debug(
                "[PLAYLIST-TRACKS-002] Playlist tracks refreshed",
                extra={"playlist_id": playlist_id, "track_count": len(tracks_data)},
            )

        except Exception as e:
            logger.error(
                "[PLAYLIST-TRACKS-ERROR] Error refreshing playlist tracks",
                extra={"playlist_id": playlist_id, "error": str(e)},
            )
            # Don't raise error here - playlist can exist without tracks temporarily

    async def load_playlist_tracks_from_spotify(
        self, spotify_client: Spotify, playlist_id: str
    ) -> List[Track]:
        """Load fresh tracks from Spotify API"""
        logger.debug(
            "[SPOTIFY-TRACKS-001] Loading tracks from Spotify",
            extra={"playlist_id": playlist_id},
        )

        try:
            tracks = []
            results = spotify_client.playlist_items(playlist_id, limit=50)

            while results:
                for item in results.get("items", []):
                    if item and item.get("track"):
                        track_data = item["track"]
                        if track_data and track_data.get("id"):
                            track = Track(
                                id=track_data["id"],
                                name=track_data["name"],
                                artist=", ".join(
                                    [artist["name"] for artist in track_data["artists"]]
                                ),
                                album=track_data["album"]["name"]
                                if track_data.get("album")
                                else None,
                                duration_ms=track_data.get("duration_ms"),
                                preview_url=track_data.get("preview_url"),
                                external_urls=track_data.get("external_urls"),
                                played=False,
                            )
                            tracks.append(track)

                # Handle pagination
                if results["next"]:
                    results = spotify_client.next(results)
                else:
                    break

            logger.debug(
                "[SPOTIFY-TRACKS-002] Loaded tracks from Spotify",
                extra={"playlist_id": playlist_id, "track_count": len(tracks)},
            )

            return tracks

        except Exception as e:
            logger.error(
                "[SPOTIFY-TRACKS-ERROR] Error loading tracks from Spotify",
                extra={"playlist_id": playlist_id, "error": str(e)},
            )
            raise PlaylistError(f"Failed to load tracks from Spotify: {str(e)}")

    async def get_available_playlists_for_game(self, user: User) -> List[Playlist]:
        """Get playlists suitable for game creation (with enough tracks)"""
        try:
            all_playlists = await database.query_records(
                "playlists",
                filters={"owner_id": user.id},
                order_by={"column": "name", "ascending": True},
            )

            suitable_playlists = []
            for playlist_data in all_playlists:
                # Only include playlists with enough tracks for bingo
                if playlist_data.get("total_tracks", 0) >= 25:
                    playlist = await self.get_playlist_by_id(
                        playlist_data["id"], include_tracks=False
                    )
                    if playlist:
                        suitable_playlists.append(playlist)

            logger.debug(
                "[PLAYLIST-GAME-001] Found suitable playlists for game",
                extra={
                    "user_id": user.id,
                    "total_playlists": len(all_playlists),
                    "suitable_playlists": len(suitable_playlists),
                },
            )

            return suitable_playlists

        except Exception as e:
            logger.error(
                "[PLAYLIST-GAME-ERROR] Error getting game playlists",
                extra={"user_id": user.id, "error": str(e)},
            )
            return []


# Global playlist service instance
playlist_service = PlaylistService()
