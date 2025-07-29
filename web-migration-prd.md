# FouteMuziekBingo Web Migration PRD
## Modern TypeScript/React Platform with Supabase & Stripe

---

## Executive Summary

**Project**: Migration of FouteMuziekBingo from Flask-based local application to modern web-based SaaS platform  
**Timeline**: 24 weeks (6-month development cycle)  
**Investment**: Transformation from desktop application to scalable web-based business  
**Goal**: Preserve 100% functionality while enabling monetization, cloud scalability, and modern user experience

### Migration Objectives
- **Complete Feature Parity**: Maintain all current functionality without any loss
- **Modern Architecture**: Transition from Flask/JSON to TypeScript/React/Supabase
- **Monetization**: Implement Stripe-based subscription model with tiered pricing
- **Scalability**: Cloud-native architecture supporting thousands of concurrent games
- **User Experience**: Enhanced responsive design with offline capabilities

### Key Success Metrics
- 100% feature preservation from current Flask application
- Sub-2 second page load times for dashboard
- Support for 1000+ concurrent games
- 95%+ payment success rate via Stripe
- Mobile-responsive experience across all devices

---

## Current Application Analysis

### Existing Flask Architecture

**Core Modules Identified:**
```
app/
├── auth_routes.py       # Spotify OAuth authentication
├── dashboard_routes.py  # Main game dashboard and statistics
├── playlist_routes.py   # Spotify playlist management
├── card_routes.py       # Bingo card generation and checking
├── playback_routes.py   # Spotify playback control
├── game_routes.py       # Game state management
├── sound_routes.py      # Sound effects system
├── pdf_generator.py     # Physical bingo card PDF generation
├── socket_handler.py    # Real-time WebSocket communication
└── state.py            # JSON-based game state management
```

### Current Data Architecture

**Game State Structure (JSON):**
```json
{
  "played_tracks": [{"id": "spotify_id", "name": "track_name", "artist": "artist_name"}],
  "unplayed_tracks": [{"id": "spotify_id", "name": "track_name", "artist": "artist_name"}],
  "cards": {
    "card_id": {
      "tracks": [25 track objects],
      "bingo_status": "Not checked|No bingo|BINGO!",
      "matches": [position_indices]
    }
  },
  "bingo_mode": "rowcoldiag",
  "current_playlist": "spotify_playlist_id",
  "num_tracks": 100
}
```

**Playlists Structure (JSON):**
```json
[
  {
    "id": "spotify:playlist:xxxxx",
    "name": "playlist_name",
    "owner": "spotify_username",
    "is_default": boolean
  }
]
```

### Current User Journey Flow

**Setup Phase:**
1. Navigate to http://localhost:1313/dashboard
2. Authenticate with Spotify OAuth
3. Select active Spotify device
4. Load/manage playlists
5. Generate bingo cards (PDF download)

**Game Phase:**
1. Real-time dashboard monitoring
2. Random track playback control
3. Live card status checking
4. Bingo detection and celebration
5. Sound effects and game progression

**Management Phase:**
1. Save/load game states
2. Statistics tracking
3. Round management
4. Playlist management

---

## Web Migration Specifications

### Technology Stack Rationale

**Why TypeScript + React:**
- **Type Safety**: Eliminates runtime errors common in dynamic Flask templates
- **Component Reusability**: Modular bingo card, playlist, and control components
- **Rich Ecosystem**: Excellent libraries for Stripe, Spotify, real-time features
- **Performance**: Virtual DOM optimizations for rapid UI updates
- **Developer Experience**: Superior debugging, IDE support, and maintainability

**Why Node.js Backend:**
- **Language Consistency**: Single language across frontend/backend
- **Real-time Native**: Built-in WebSocket support for live game updates
- **Integration Friendly**: Best-in-class SDKs for Stripe, Spotify, Supabase
- **Scalability**: Non-blocking I/O perfect for concurrent games
- **Type Sharing**: Shared interfaces between frontend and backend

**Why Supabase:**
- **Real-time Built-in**: Native WebSocket subscriptions for live updates
- **TypeScript Native**: Auto-generated types from database schema
- **Authentication**: Integrated OAuth with Spotify
- **Row-Level Security**: Multi-tenant game isolation
- **Global CDN**: Low-latency access worldwide

### Supabase Database Schema Design

```sql
-- Users table (integrated with Supabase Auth)
CREATE TABLE profiles (
  id UUID REFERENCES auth.users(id) PRIMARY KEY,
  spotify_id TEXT UNIQUE,
  display_name TEXT,
  email TEXT,
  avatar_url TEXT,
  subscription_tier TEXT DEFAULT 'free',
  subscription_status TEXT DEFAULT 'active',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Playlists management
CREATE TABLE playlists (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  spotify_playlist_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  owner_name TEXT,
  is_default BOOLEAN DEFAULT FALSE,
  track_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Game sessions
CREATE TABLE game_sessions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  playlist_id UUID REFERENCES playlists(id),
  bingo_mode TEXT DEFAULT 'rowcoldiag',
  status TEXT DEFAULT 'setup', -- setup, active, paused, completed
  total_tracks INTEGER DEFAULT 0,
  played_tracks_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tracks in game sessions
CREATE TABLE game_tracks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  game_session_id UUID REFERENCES game_sessions(id) ON DELETE CASCADE,
  spotify_track_id TEXT NOT NULL,
  track_name TEXT NOT NULL,
  artist_name TEXT NOT NULL,
  is_played BOOLEAN DEFAULT FALSE,
  play_order INTEGER,
  played_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Bingo cards
CREATE TABLE bingo_cards (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  game_session_id UUID REFERENCES game_sessions(id) ON DELETE CASCADE,
  card_number TEXT NOT NULL, -- User-friendly card identifier
  tracks JSONB NOT NULL, -- Array of 25 track objects
  matches INTEGER[] DEFAULT '{}', -- Array of matched positions
  bingo_status TEXT DEFAULT 'active', -- active, bingo, checked
  bingo_achieved_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sound effects and customization
CREATE TABLE user_sounds (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  file_url TEXT NOT NULL,
  sound_type TEXT, -- applause, game_over, bingo, etc.
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Subscription and billing (Stripe integration)
CREATE TABLE subscriptions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  stripe_customer_id TEXT UNIQUE,
  stripe_subscription_id TEXT UNIQUE,
  plan_name TEXT NOT NULL,
  status TEXT NOT NULL, -- active, canceled, past_due, etc.
  current_period_start TIMESTAMP WITH TIME ZONE,
  current_period_end TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Game statistics and analytics
CREATE TABLE game_analytics (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  game_session_id UUID REFERENCES game_sessions(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL, -- track_played, card_checked, bingo_achieved
  event_data JSONB,
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE playlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE bingo_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_analytics ENABLE ROW LEVEL SECURITY;

-- RLS Policies (user can only access their own data)
CREATE POLICY "Users can view own profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can manage own playlists" ON playlists FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can manage own game sessions" ON game_sessions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can access own game tracks" ON game_tracks FOR ALL USING (
  auth.uid() = (SELECT user_id FROM game_sessions WHERE id = game_session_id)
);
CREATE POLICY "Users can manage own bingo cards" ON bingo_cards FOR ALL USING (
  auth.uid() = (SELECT user_id FROM game_sessions WHERE id = game_session_id)
);
```

---

## Frontend Architecture: React + TypeScript

### Component Structure

```
src/
├── components/
│   ├── dashboard/
│   │   ├── GameDashboard.tsx          # Main dashboard layout
│   │   ├── GameStatistics.tsx         # Live game statistics
│   │   ├── PlaybackControls.tsx       # Spotify playback controls
│   │   └── PlayedTracksList.tsx       # List of played tracks
│   ├── cards/
│   │   ├── BingoCard.tsx              # Individual bingo card display
│   │   ├── BingoGrid.tsx              # 5x5 bingo grid component
│   │   ├── CardManager.tsx            # Card generation and management
│   │   └── CardStatusIndicator.tsx    # Visual bingo status
│   ├── playlists/
│   │   ├── PlaylistManager.tsx        # Playlist CRUD operations
│   │   ├── PlaylistSelector.tsx       # Playlist selection dropdown
│   │   └── SpotifyPlaylistImport.tsx  # Import from Spotify
│   ├── setup/
│   │   ├── GameSetup.tsx              # Game configuration modal
│   │   ├── DeviceSelector.tsx         # Spotify device selection
│   │   └── TabNavigation.tsx          # Setup modal tabs
│   ├── audio/
│   │   ├── SoundEffectsPanel.tsx      # Sound effects controls
│   │   └── AudioPlayer.tsx            # Web audio playback
│   ├── auth/
│   │   ├── SpotifyAuth.tsx            # Spotify OAuth flow
│   │   └── AuthGuard.tsx              # Route protection
│   ├── billing/
│   │   ├── SubscriptionManager.tsx    # Stripe subscription UI
│   │   ├── PricingTiers.tsx           # Pricing display
│   │   └── PaymentForm.tsx            # Stripe Elements integration
│   └── shared/
│       ├── LoadingSpinner.tsx         # Loading states
│       ├── ErrorBoundary.tsx          # Error handling
│       ├── Notification.tsx           # Toast notifications
│       └── Modal.tsx                  # Reusable modal component
├── hooks/
│   ├── useGameState.tsx               # Game state management
│   ├── useSpotifyAuth.tsx             # Spotify authentication
│   ├── useWebSocket.tsx               # Real-time connection
│   ├── useLocalStorage.tsx            # Browser storage
│   └── useSubscription.tsx            # Stripe subscription status
├── services/
│   ├── api.ts                         # API client configuration
│   ├── spotify.ts                     # Spotify Web API integration
│   ├── supabase.ts                    # Supabase client
│   ├── stripe.ts                      # Stripe client-side
│   └── websocket.ts                   # WebSocket service
├── types/
│   ├── game.ts                        # Game-related types
│   ├── spotify.ts                     # Spotify API types
│   ├── subscription.ts                # Billing types
│   └── database.ts                    # Supabase generated types
└── utils/
    ├── cardGenerator.ts               # Bingo card logic
    ├── bingoChecker.ts                # Bingo pattern detection
    ├── pdfGenerator.ts                # Client-side PDF generation
    └── formatters.ts                  # Data formatting utilities
```

### Key React Components Specifications

**GameDashboard.tsx** - Main Dashboard Layout
```typescript
interface GameDashboardProps {
  gameSession: GameSession;
  onTrackPlay: (track: Track) => void;
  onCardCheck: (cardId: string) => void;
}

export const GameDashboard: React.FC<GameDashboardProps> = ({
  gameSession,
  onTrackPlay,
  onCardCheck
}) => {
  const { isConnected } = useWebSocket();
  const { playTrack, pausePlayback } = useSpotifyAuth();
  
  return (
    <div className="grid grid-cols-12 gap-4 h-screen">
      {/* Left sidebar - Controls */}
      <aside className="col-span-3">
        <PlaybackControls onPlay={playTrack} onPause={pausePlayback} />
        <SoundEffectsPanel />
        <PlayedTracksList tracks={gameSession.playedTracks} />
      </aside>
      
      {/* Main content - Cards */}
      <main className="col-span-9">
        <GameStatistics session={gameSession} />
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {gameSession.cards.map(card => (
            <BingoCard 
              key={card.id}
              card={card}
              onCheck={() => onCardCheck(card.id)}
            />
          ))}
        </div>
      </main>
    </div>
  );
};
```

**BingoCard.tsx** - Individual Bingo Card
```typescript
interface BingoCardProps {
  card: BingoCardData;
  onCheck: () => void;
  readOnly?: boolean;
}

export const BingoCard: React.FC<BingoCardProps> = ({ 
  card, 
  onCheck, 
  readOnly = false 
}) => {
  const [isChecking, setIsChecking] = useState(false);
  
  const handleCheck = async () => {
    setIsChecking(true);
    await onCheck();
    setIsChecking(false);
  };
  
  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-bold">Card {card.cardNumber}</h3>
        <BingoStatusIndicator status={card.bingoStatus} />
      </div>
      
      <BingoGrid 
        tracks={card.tracks}
        matches={card.matches}
        onCellClick={readOnly ? undefined : handleCheck}
      />
      
      {!readOnly && (
        <button 
          onClick={handleCheck}
          disabled={isChecking}
          className="w-full mt-2 bg-blue-500 text-white py-2 rounded"
        >
          {isChecking ? 'Checking...' : 'Check Card'}
        </button>
      )}
    </div>
  );
};
```

---

## Backend Architecture: Node.js + Express

### API Route Structure

```
src/
├── routes/
│   ├── auth.ts              # Spotify OAuth and user authentication
│   ├── playlists.ts         # Playlist management API
│   ├── games.ts             # Game session management
│   ├── cards.ts             # Bingo card operations
│   ├── playback.ts          # Spotify playback control
│   ├── billing.ts           # Stripe subscription management
│   └── webhooks.ts          # Stripe webhook handlers
├── middleware/
│   ├── auth.ts              # JWT/Supabase authentication
│   ├── subscription.ts      # Subscription tier validation
│   ├── rateLimit.ts         # API rate limiting
│   └── validation.ts        # Request validation
├── services/
│   ├── spotify.ts           # Spotify Web API service
│   ├── supabase.ts          # Database operations
│   ├── stripe.ts            # Payment processing
│   ├── pdf.ts               # Server-side PDF generation
│   └── websocket.ts         # Real-time communication
├── types/
│   ├── api.ts               # API request/response types
│   ├── database.ts          # Database entity types
│   └── shared.ts            # Shared types with frontend
└── utils/
    ├── bingoLogic.ts        # Bingo detection algorithms
    ├── cardGenerator.ts     # Card generation logic
    └── validators.ts        # Input validation
```

### Core API Endpoints

**Game Management API**
```typescript
// POST /api/games - Create new game session
interface CreateGameRequest {
  name: string;
  playlistId: string;
  bingoMode: 'rowcoldiag' | 'corners' | 'full';
  numCards: number;
}

// GET /api/games/:gameId - Get game session
// PUT /api/games/:gameId - Update game session
// DELETE /api/games/:gameId - Delete game session
// POST /api/games/:gameId/start - Start game session
// POST /api/games/:gameId/pause - Pause game session
// POST /api/games/:gameId/reset - Reset game session

// POST /api/games/:gameId/play-track - Play random track
interface PlayTrackResponse {
  track: Track;
  gameState: GameSession;
  cardsUpdated: BingoCard[];
}

// POST /api/games/:gameId/cards/:cardId/check - Check bingo card
interface CheckCardResponse {
  cardId: string;
  matches: number[];
  bingoStatus: 'active' | 'bingo';
  hasBingo: boolean;
}
```

**Playlist Management API**
```typescript
// GET /api/playlists - Get user playlists
// POST /api/playlists - Add playlist from Spotify
interface AddPlaylistRequest {
  spotifyPlaylistId: string;
  isDefault?: boolean;
}

// PUT /api/playlists/:playlistId - Update playlist
// DELETE /api/playlists/:playlistId - Remove playlist
// POST /api/playlists/:playlistId/load-tracks - Load tracks for game
```

**Billing and Subscription API**
```typescript
// GET /api/billing/plans - Get available subscription plans
// POST /api/billing/create-checkout - Create Stripe checkout session
// GET /api/billing/subscription - Get current subscription
// POST /api/billing/cancel - Cancel subscription
// POST /api/billing/update-payment - Update payment method

// Webhook endpoint for Stripe events
// POST /api/webhooks/stripe - Handle Stripe webhook events
```

---

## Integration Specifications

### Spotify Integration Enhancement

**Current vs. Enhanced Integration:**

| Current Flask | Enhanced Web Platform |
|---------------|----------------------|
| Server-side OAuth only | Client + Server OAuth |
| Device polling | Real-time device detection |
| Basic playback control | Advanced playback features |
| Manual token refresh | Automatic token management |

**Enhanced Spotify Features:**
```typescript
interface SpotifyService {
  // Authentication
  authenticateUser(): Promise<SpotifyAuthResult>;
  refreshToken(): Promise<void>;
  
  // Device Management
  getAvailableDevices(): Promise<SpotifyDevice[]>;
  setActiveDevice(deviceId: string): Promise<void>;
  
  // Playback Control
  playTrack(trackId: string, deviceId?: string): Promise<void>;
  pausePlayback(): Promise<void>;
  setVolume(volume: number): Promise<void>;
  seekToPosition(positionMs: number): Promise<void>;
  
  // Playlist Management
  getUserPlaylists(): Promise<SpotifyPlaylist[]>;
  getPlaylistTracks(playlistId: string): Promise<SpotifyTrack[]>;
  
  // Real-time Features
  getCurrentPlayback(): Promise<SpotifyPlaybackState>;
  subscribeToPlaybackUpdates(callback: (state: SpotifyPlaybackState) => void): void;
}
```

### Stripe Monetization Integration

**Subscription Tier Structure:**

**Free Tier:**
- 1 concurrent game session
- Up to 5 bingo cards per game
- Basic sound effects
- Standard playlists only
- Community support

**Pro Tier ($9.99/month):**
- Unlimited concurrent games
- Up to 50 bingo cards per game
- Custom sound effects upload
- Private playlist support
- Advanced analytics dashboard
- Email support

**Enterprise Tier ($29.99/month):**
- Everything in Pro
- Branded PDF cards
- API access for integrations
- Priority support
- Custom domain hosting
- Advanced user management

**Stripe Implementation:**
```typescript
interface StripeService {
  // Subscription Management
  createCheckoutSession(planId: string): Promise<string>;
  createCustomerPortal(): Promise<string>;
  getCurrentSubscription(): Promise<Subscription>;
  
  // Payment Processing
  createPaymentIntent(amount: number): Promise<string>;
  confirmPayment(paymentIntentId: string): Promise<PaymentResult>;
  
  // Webhook Handling
  handleWebhookEvent(event: StripeEvent): Promise<void>;
  
  // Usage Tracking
  recordUsage(customerId: string, feature: string): Promise<void>;
  getUsageMetrics(customerId: string): Promise<UsageMetrics>;
}
```

### Real-time WebSocket Architecture

**Enhanced Real-time Features:**
```typescript
interface WebSocketEvents {
  // Game Events
  'game:track-played': { track: Track; gameState: GameSession };
  'game:card-checked': { cardId: string; matches: number[]; hasBingo: boolean };
  'game:bingo-achieved': { cardId: string; playerName?: string };
  'game:state-changed': { gameState: GameSession };
  
  // System Events
  'system:connection-status': { isConnected: boolean };
  'system:error': { message: string; code?: string };
  'system:notification': { type: 'info' | 'success' | 'warning' | 'error'; message: string };
  
  // User Events
  'user:joined-game': { userId: string; displayName: string };
  'user:left-game': { userId: string };
}

class WebSocketService {
  private socket: Socket;
  
  connect(gameSessionId: string): void;
  disconnect(): void;
  
  // Event Emitters
  playTrack(trackId: string): void;
  checkCard(cardId: string): void;
  
  // Event Listeners
  onTrackPlayed(callback: (data: TrackPlayedEvent) => void): void;
  onCardChecked(callback: (data: CardCheckedEvent) => void): void;
  onBingoAchieved(callback: (data: BingoAchievedEvent) => void): void;
}
```

---

## Feature Specifications

### Core Features (MVP) - 100% Feature Parity

#### 1. User Authentication & Authorization
**Current**: Basic Spotify OAuth with session storage  
**Enhanced**: Full user management with persistent sessions

**User Stories:**
- As a user, I want to sign in with my Spotify account so I can access my playlists and control playback
- As a user, I want my session to persist across browser restarts so I don't need to re-authenticate constantly
- As a user, I want to see my subscription status and upgrade options in my profile

**Technical Implementation:**
- Supabase Auth integration with Spotify OAuth
- JWT token management with automatic refresh
- User profile management with subscription status
- Role-based access control for different subscription tiers

**Acceptance Criteria:**
- ✅ User can authenticate via Spotify OAuth
- ✅ User session persists for 30 days
- ✅ User profile displays subscription tier and status
- ✅ Automatic token refresh without user intervention

#### 2. Playlist Management System
**Current**: JSON file storage with basic CRUD operations  
**Enhanced**: Cloud-based playlist management with sharing capabilities

**User Stories:**
- As a user, I want to import playlists from my Spotify account so I can use them in bingo games
- As a user, I want to set a default playlist so games start quickly
- As a user, I want to see playlist statistics (track count, duration) to help me choose the best playlist for my game

**Technical Implementation:**
```typescript
interface PlaylistManager {
  importFromSpotify(playlistId: string): Promise<Playlist>;
  setDefaultPlaylist(playlistId: string): Promise<void>;
  getPlaylistStats(playlistId: string): Promise<PlaylistStats>;
  sharePlaylist(playlistId: string): Promise<string>; // Share URL
}

interface PlaylistStats {
  trackCount: number;
  totalDurationMs: number;
  genres: string[];
  averagePopularity: number;
}
```

**Acceptance Criteria:**
- ✅ User can import any public Spotify playlist
- ✅ User can set one playlist as default
- ✅ Playlist statistics are displayed before game creation
- ✅ Error handling for invalid or private playlists

#### 3. Bingo Card Generation & Management
**Current**: Random sampling with PDF generation  
**Enhanced**: Advanced card generation with customization options

**User Stories:**
- As a user, I want to generate bingo cards with random track selections so each game is unique
- As a user, I want to download printable PDF versions of the cards so players can use physical cards
- As a user, I want to see live updates of card status during the game so I can track progress

**Technical Implementation:**
```typescript
interface CardGenerator {
  generateCards(config: CardGenerationConfig): Promise<BingoCard[]>;
  generatePDF(cards: BingoCard[]): Promise<Blob>;
  checkCardForMatches(cardId: string, playedTracks: Track[]): Promise<CardCheckResult>;
}

interface CardGenerationConfig {
  numCards: number;
  playlistId: string;
  avoidDuplicates: boolean;
  bingoMode: 'rowcoldiag' | 'corners' | 'full';
}
```

**Acceptance Criteria:**
- ✅ Generate 1-100 unique bingo cards per game
- ✅ PDF generation matches current Flask output exactly
- ✅ Real-time card status updates via WebSocket
- ✅ Bingo detection for rows, columns, and diagonals

#### 4. Game Session Management
**Current**: Single JSON file state management  
**Enhanced**: Multi-tenant game sessions with persistence

**User Stories:**
- As a user, I want to start a new game session with my chosen playlist and card count
- As a user, I want to pause and resume games so I can take breaks during long sessions
- As a user, I want to save game progress so I can continue later or review past games

**Technical Implementation:**
```typescript
interface GameSession {
  id: string;
  name: string;
  status: 'setup' | 'active' | 'paused' | 'completed';
  playlist: Playlist;
  cards: BingoCard[];
  playedTracks: Track[];
  unplayedTracks: Track[];
  statistics: GameStatistics;
  createdAt: Date;
  updatedAt: Date;
}

interface GameManager {
  createSession(config: GameConfig): Promise<GameSession>;
  startSession(sessionId: string): Promise<void>;
  pauseSession(sessionId: string): Promise<void>;
  resumeSession(sessionId: string): Promise<void>;
  completeSession(sessionId: string): Promise<GameStatistics>;
}
```

**Acceptance Criteria:**
- ✅ Create unlimited game sessions (subscription dependent)
- ✅ Pause/resume functionality preserves exact state
- ✅ Game history accessible for 30 days (free) / unlimited (paid)
- ✅ Automatic save every 30 seconds during active games

#### 5. Spotify Playback Control
**Current**: Basic play/pause with device selection  
**Enhanced**: Advanced playback control with queue management

**User Stories:**
- As a user, I want to play random tracks from my playlist so the game progresses
- As a user, I want to control playback volume and seek position for better game management
- As a user, I want to see which device is active and switch devices if needed

**Technical Implementation:**
```typescript
interface PlaybackController {
  playRandomTrack(): Promise<Track>;
  pausePlayback(): Promise<void>;
  setVolume(volume: number): Promise<void>;
  seekToPosition(positionMs: number): Promise<void>;
  getActiveDevice(): Promise<SpotifyDevice>;
  setActiveDevice(deviceId: string): Promise<void>;
  getPlaybackState(): Promise<PlaybackState>;
}
```

**Acceptance Criteria:**
- ✅ Random track selection from unplayed tracks
- ✅ Volume control (0-100%)
- ✅ Seek position control
- ✅ Active device display and switching
- ✅ Playback state synchronization across all connected clients

#### 6. Real-time Dashboard Updates
**Current**: WebSocket with Flask-SocketIO  
**Enhanced**: Scalable real-time updates with presence indicators

**User Stories:**
- As a user, I want to see live updates when tracks are played so all participants stay synchronized
- As a user, I want to see when bingo cards are checked and when someone achieves bingo
- As a user, I want connection status indicators so I know if I'm receiving live updates

**Technical Implementation:**
```typescript
interface RealtimeUpdates {
  subscribeToGameUpdates(gameId: string): void;
  broadcastTrackPlayed(track: Track): void;
  broadcastCardChecked(cardId: string, result: CardCheckResult): void;
  broadcastBingoAchieved(cardId: string): void;
  getConnectedUsers(): Promise<ConnectedUser[]>;
}
```

**Acceptance Criteria:**
- ✅ Sub-500ms update latency for all connected clients
- ✅ Connection status indicator (connected/disconnected/reconnecting)
- ✅ Automatic reconnection with state synchronization
- ✅ Offline queue for actions taken while disconnected

#### 7. Sound Effects System
**Current**: Local sound file playback  
**Enhanced**: Web-based audio with custom sound support

**User Stories:**
- As a user, I want to play sound effects during game events to enhance the experience
- As a user, I want to upload custom sound effects so I can personalize my games
- As a user, I want volume control for sound effects independent of music playback

**Technical Implementation:**
```typescript
interface SoundEffectsManager {
  playSound(soundType: SoundType): Promise<void>;
  uploadCustomSound(file: File, soundType: SoundType): Promise<void>;
  setSoundVolume(volume: number): Promise<void>;
  preloadSounds(): Promise<void>;
}

type SoundType = 'applause' | 'bingo' | 'game_over' | 'track_start' | 'custom';
```

**Acceptance Criteria:**
- ✅ All current sound effects work identically
- ✅ Custom sound upload (Pro tier feature)
- ✅ Independent volume control
- ✅ Sound preloading for instant playback

### Premium Features (Post-MVP)

#### 8. Advanced Analytics Dashboard
**User Stories:**
- As a Pro user, I want detailed game analytics so I can optimize my bingo events
- As a Pro user, I want to export game data so I can create custom reports

**Features:**
- Game duration statistics
- Most popular tracks analysis
- Bingo achievement patterns
- Player engagement metrics
- Custom reporting and data export

#### 9. Multi-Player Collaboration
**User Stories:**
- As a Pro user, I want to invite other users to co-host games
- As a Pro user, I want to see who's connected to my game session

**Features:**
- Multi-host game sessions
- Real-time participant list
- Role-based permissions (host, co-host, participant)
- Chat functionality during games

#### 10. Custom Branding & White Label
**User Stories:**
- As an Enterprise user, I want to customize the interface with my branding
- As an Enterprise user, I want custom domain hosting for my bingo platform

**Features:**
- Custom logo and color schemes
- Branded PDF card generation
- Custom domain setup
- White-label solution options

---

## User Experience Design

### Responsive Design Requirements

**Mobile-First Approach:**
- **Mobile (320px-768px)**: Single-column layout with collapsible sections
- **Tablet (768px-1024px)**: Two-column layout with side navigation
- **Desktop (1024px+)**: Multi-column dashboard with full feature set

**Component Responsiveness:**
```typescript
// Example responsive bingo card component
const BingoCard: React.FC<BingoCardProps> = ({ card }) => {
  return (
    <div className="
      w-full max-w-sm mx-auto          // Mobile: full width, max small size
      md:max-w-md                      // Tablet: medium max width  
      lg:max-w-lg                      // Desktop: large max width
      bg-white rounded-lg shadow-md p-4
    ">
      <BingoGrid 
        className="
          grid grid-cols-5 gap-1         // Mobile: small gaps
          md:gap-2                       // Tablet: medium gaps  
          lg:gap-3                       // Desktop: large gaps
        "
        tracks={card.tracks}
      />
    </div>
  );
};
```

### Progressive Web App (PWA) Specifications

**Service Worker Implementation:**
```typescript
// sw.ts - Service Worker for offline functionality
class BingoServiceWorker {
  // Cache strategies for different resource types
  cacheStrategies = {
    'static-assets': 'cache-first',      // CSS, JS, images
    'api-calls': 'network-first',        // Dynamic data
    'spotify-api': 'network-only',       // Always fresh
    'audio-files': 'cache-first'         // Sound effects
  };
  
  // Offline fallbacks
  offlinePages = {
    '/dashboard': '/offline-dashboard.html',
    '/games': '/offline-games.html'
  };
  
  // Background sync for offline actions
  backgroundSync = {
    'card-checks': this.syncCardChecks,
    'game-updates': this.syncGameUpdates
  };
}
```

**PWA Features:**
- ✅ Installable on mobile devices and desktop
- ✅ Offline dashboard with cached game data
- ✅ Background sync for actions taken offline
- ✅ Push notifications for game events
- ✅ App-like navigation and UX

### Accessibility Compliance (WCAG 2.1 AA)

**Accessibility Features:**
```typescript
// Example accessible bingo card component
const AccessibleBingoCard: React.FC<BingoCardProps> = ({ card }) => {
  return (
    <div 
      role="region"
      aria-labelledby={`card-title-${card.id}`}
      className="focus-visible:outline-2 focus-visible:outline-blue-500"
    >
      <h3 id={`card-title-${card.id}`} className="sr-only">
        Bingo Card {card.cardNumber}
      </h3>
      
      <div 
        role="grid" 
        aria-label={`Bingo card ${card.cardNumber} with 25 cells`}
        className="grid grid-cols-5"
      >
        {card.tracks.map((track, index) => (
          <div
            key={track.id}
            role="gridcell"
            aria-selected={card.matches.includes(index)}
            tabIndex={0}
            className={`
              p-2 border cursor-pointer
              focus:outline-2 focus:outline-blue-500
              ${card.matches.includes(index) ? 'bg-green-200' : 'bg-white'}
            `}
            onClick={() => handleCellClick(index)}
            onKeyDown={(e) => e.key === 'Enter' && handleCellClick(index)}
          >
            <span className="sr-only">
              {card.matches.includes(index) ? 'Matched: ' : 'Not matched: '}
            </span>
            {track.name} by {track.artist}
          </div>
        ))}
      </div>
    </div>
  );
};
```

**Accessibility Checklist:**
- ✅ Keyboard navigation for all interactive elements
- ✅ Screen reader compatibility with proper ARIA labels
- ✅ High contrast mode support
- ✅ Focus indicators for all focusable elements
- ✅ Alternative text for all images and icons
- ✅ Semantic HTML structure throughout

---

## Development Roadmap

### Phase 1: Foundation & Core Migration (Weeks 1-8)

**Week 1-2: Project Setup & Infrastructure**
- ✅ Set up TypeScript/React project with Vite
- ✅ Configure Supabase project and database schema
- ✅ Set up Node.js/Express backend with TypeScript
- ✅ Configure CI/CD pipeline (GitHub Actions)
- ✅ Set up monitoring (Sentry, analytics)

**Week 3-4: Authentication & User Management**
- ✅ Implement Spotify OAuth with Supabase Auth
- ✅ Create user profile management
- ✅ Set up session persistence and token refresh
- ✅ Implement basic subscription tier detection

**Week 5-6: Core Game Functionality**
- ✅ Migrate playlist management from JSON to Supabase
- ✅ Implement game session creation and management
- ✅ Create bingo card generation system
- ✅ Set up real-time WebSocket infrastructure

**Week 7-8: Spotify Integration & Playback**
- ✅ Implement Spotify Web API integration
- ✅ Create playback control system
- ✅ Set up device detection and selection
- ✅ Implement track playing and game state updates

**Phase 1 Deliverables:**
- Functional web application with core bingo functionality
- User authentication and basic subscription detection
- Real-time game updates via WebSocket
- Spotify playlist import and playback control

### Phase 2: Enhanced Features & Monetization (Weeks 9-16)

**Week 9-10: Advanced Dashboard Features**
- ✅ Implement game statistics and analytics
- ✅ Create saved game management
- ✅ Add sound effects system with web audio
- ✅ Implement PDF generation for printable cards

**Week 11-12: Stripe Payment Integration**
- ✅ Set up Stripe accounts and webhook endpoints
- ✅ Implement subscription creation and management
- ✅ Create pricing tiers and feature gating
- ✅ Build billing dashboard and payment forms

**Week 13-14: Premium Features Development**
- ✅ Implement advanced analytics dashboard
- ✅ Add custom sound effect upload functionality
- ✅ Create multi-game session management
- ✅ Build user collaboration features

**Week 15-16: Mobile Optimization & PWA**
- ✅ Implement responsive design across all components
- ✅ Create service worker for offline functionality
- ✅ Add push notification system
- ✅ Optimize performance for mobile devices

**Phase 2 Deliverables:**
- Complete subscription system with Stripe integration
- Mobile-responsive design with PWA capabilities
- Premium features for paid subscribers
- Advanced analytics and reporting tools

### Phase 3: Polish, Testing & Launch (Weeks 17-24)

**Week 17-18: Testing & Quality Assurance**
- ✅ Comprehensive unit and integration testing
- ✅ Cross-browser compatibility testing
- ✅ Mobile device testing on iOS and Android
- ✅ Load testing for concurrent users
- ✅ Security audit and penetration testing

**Week 19-20: Performance Optimization**
- ✅ Database query optimization and indexing
- ✅ Frontend bundle optimization and code splitting
- ✅ CDN setup for static assets
- ✅ Caching strategy implementation
- ✅ Performance monitoring setup

**Week 21-22: User Experience Refinement**
- ✅ User testing sessions with current Flask users
- ✅ Accessibility audit and WCAG compliance
- ✅ Error handling and user feedback improvements
- ✅ Onboarding flow optimization

**Week 23-24: Production Deployment & Launch**
- ✅ Production environment setup (Vercel/Railway)
- ✅ Domain configuration and SSL setup
- ✅ Data migration from existing Flask instances
- ✅ User communication and migration support
- ✅ Launch and post-launch monitoring

**Phase 3 Deliverables:**
- Production-ready web application
- Comprehensive testing coverage
- Performance optimized for scale
- User migration completed successfully

### Post-Launch Roadmap (Weeks 25+)

**Immediate Post-Launch (Weeks 25-28):**
- Bug fixes and stability improvements
- User feedback collection and prioritization
- Performance monitoring and optimization
- Customer support system implementation

**Future Feature Development:**
- Advanced tournament modes and brackets
- Integration with other music services (Apple Music, YouTube Music)
- Social sharing and community features
- Mobile app development (React Native)
- API for third-party integrations

---

## Risk Assessment & Mitigation

### Technical Migration Risks

**Risk: Data Loss During Migration**
- **Probability**: Medium
- **Impact**: High
- **Mitigation**: 
  - Comprehensive backup strategy before migration
  - Incremental migration with rollback procedures
  - Data validation at every migration step
  - Parallel running of old and new systems during transition

**Risk: Spotify API Rate Limiting**
- **Probability**: High
- **Impact**: Medium
- **Mitigation**:
  - Implement intelligent caching for playlist and track data
  - Request queuing and throttling mechanisms
  - Fallback to cached data when rate limited
  - Premium Spotify developer tier consideration

**Risk: Real-time Performance Issues**
- **Probability**: Medium
- **Impact**: High
- **Mitigation**:
  - Comprehensive load testing with WebSocket connections
  - Horizontal scaling architecture with Redis for session storage
  - Connection pooling and efficient event handling
  - Graceful degradation to polling when WebSockets fail

### Business Model Risks

**Risk: Low Subscription Conversion**
- **Probability**: Medium
- **Impact**: High
- **Mitigation**:
  - Generous free tier to demonstrate value
  - Clear value proposition for premium features
  - Gradual feature introduction and user education
  - A/B testing for pricing and feature combinations

**Risk: Payment Processing Issues**
- **Probability**: Low
- **Impact**: High
- **Mitigation**:
  - Stripe's robust payment infrastructure
  - Multiple payment method support
  - Comprehensive webhook handling for all scenarios
  - Clear billing communication and support

### User Experience Risks

**Risk: Feature Parity Gaps**
- **Probability**: Medium
- **Impact**: High
- **Mitigation**:
  - Detailed feature mapping from Flask to web platform
  - User acceptance testing with current Flask users
  - Phased rollout with feedback collection
  - Clear migration communication and support

**Risk: Performance Degradation**
- **Probability**: Medium
- **Impact**: Medium
- **Mitigation**:
  - Performance budgets and monitoring
  - Progressive loading and code splitting
  - CDN optimization for global users
  - Continuous performance testing and optimization

---

## Success Metrics & KPIs

### Technical Performance Metrics

**Page Load Performance:**
- First Contentful Paint: < 1.5 seconds
- Largest Contentful Paint: < 2.5 seconds
- First Input Delay: < 100 milliseconds
- Cumulative Layout Shift: < 0.1

**Real-time Performance:**
- WebSocket connection success rate: > 99%
- Message delivery latency: < 500ms
- Reconnection time: < 3 seconds
- Concurrent connections supported: 10,000+

**Reliability Metrics:**
- Uptime: > 99.9%
- Error rate: < 0.1%
- API response time: < 200ms (95th percentile)
- Database query performance: < 100ms average

### User Experience Metrics

**Engagement Metrics:**
- Daily Active Users (DAU)
- Session duration and frequency
- Game completion rate
- Feature adoption rate (cards generated, games played)

**Conversion Metrics:**
- Free to paid conversion rate: Target 5-10%
- Subscription retention rate: Target 85%+ monthly
- Customer lifetime value (CLV)
- Churn rate by subscription tier

**User Satisfaction:**
- Net Promoter Score (NPS): Target > 50
- Customer satisfaction score: Target > 4.5/5
- Support ticket resolution time: < 24 hours
- User onboarding completion rate: Target > 80%

### Business Metrics

**Revenue Metrics:**
- Monthly Recurring Revenue (MRR) growth
- Average Revenue Per User (ARPU)
- Customer Acquisition Cost (CAC)
- Revenue per game session

**Growth Metrics:**
- User acquisition rate
- Organic vs. paid user acquisition
- Referral rate and viral coefficient
- Market penetration in target segments

---

## Budget & Resource Requirements

### Development Team Structure

**Core Team (6 months):**
- **1x Full-Stack Developer** (Lead) - $120,000/year
- **1x Frontend Developer** (React/TypeScript) - $100,000/year  
- **1x Backend Developer** (Node.js/Database) - $100,000/year
- **1x DevOps/Infrastructure** (Part-time) - $80,000/year
- **1x UI/UX Designer** (Part-time) - $75,000/year

**Total Development Cost: ~$95,000** (6-month project)

### Infrastructure & Service Costs

**Monthly Operating Costs:**
- **Supabase Pro Plan**: $25/month (includes auth, database, real-time)
- **Vercel Pro Plan**: $20/month (frontend hosting, edge functions)
- **Railway Pro Plan**: $20/month (backend API hosting)
- **Stripe Processing**: 2.9% + $0.30 per transaction
- **Monitoring & Analytics**: $50/month (Sentry, analytics tools)
- **CDN & Storage**: $30/month (media assets, user uploads)

**Annual Infrastructure: ~$2,000** (excluding transaction fees)

### Third-Party Integration Costs

**Required Services:**
- **Spotify Web API**: Free (with rate limits)
- **Stripe Connect**: Standard processing fees
- **SSL Certificates**: Included with hosting
- **Domain Registration**: $15/year

**Optional Premium Services:**
- **Spotify Premium API**: $10,000+/year (higher rate limits)
- **Advanced Analytics**: $200/month
- **Premium Support Plans**: $500/month

### Total Investment Summary

**Initial Development Investment: $95,000**
- Complete web platform development
- All core and premium features
- Testing, deployment, and launch support

**Annual Operating Costs: $12,000-15,000**
- Infrastructure, services, and maintenance
- Excludes payment processing fees (revenue-based)

**Break-even Analysis:**
- At $9.99 Pro tier average: 100 subscribers = $1,000/month
- Target: 500+ subscribers for sustainable growth
- ROI timeline: 12-18 months post-launch

---

## Conclusion

This comprehensive PRD outlines the complete transformation of FouteMuziekBingo from a Flask-based local application to a modern, scalable, web-based SaaS platform. The migration preserves 100% of current functionality while enabling significant enhancements through modern web technologies, cloud infrastructure, and monetization capabilities.

### Key Migration Benefits

**For Users:**
- ✅ **Zero Learning Curve**: Identical functionality with enhanced UX
- ✅ **Cross-Platform Access**: Works on any device with a web browser
- ✅ **Cloud Persistence**: Games and settings saved automatically
- ✅ **Real-time Collaboration**: Multiple hosts and participants
- ✅ **Mobile Optimization**: Responsive design for all screen sizes

**For Business:**
- ✅ **Scalable Revenue Model**: Subscription-based with clear tier differentiation
- ✅ **Global Reach**: Cloud-hosted with worldwide accessibility
- ✅ **Automated Operations**: Reduced manual maintenance and support
- ✅ **Data-Driven Decisions**: Comprehensive analytics and user insights
- ✅ **Competitive Advantage**: Modern tech stack enabling rapid iteration

**For Technology:**
- ✅ **Future-Proof Architecture**: Modern TypeScript/React/Supabase stack
- ✅ **Developer Experience**: Superior tooling, testing, and deployment
- ✅ **Performance**: Optimized for speed and scalability
- ✅ **Security**: Enterprise-grade authentication and data protection
- ✅ **Maintainability**: Clean code architecture with comprehensive documentation

### Next Steps

1. **Stakeholder Review**: Present this PRD to decision makers for approval and feedback
2. **Technical Validation**: Conduct proof-of-concept development for critical integrations
3. **Team Assembly**: Recruit development team with required expertise
4. **Project Kickoff**: Initialize development with Phase 1 infrastructure setup
5. **User Communication**: Prepare existing Flask users for migration timeline and benefits

The outlined 24-week development timeline provides a realistic path to market while ensuring quality, performance, and user satisfaction. With proper execution, this migration will transform FouteMuziekBingo from a local utility into a competitive web-based platform with significant growth potential.

---

*Document Version: 1.0*  
*Last Updated: 2025-07-29*  
*Total Pages: 47*