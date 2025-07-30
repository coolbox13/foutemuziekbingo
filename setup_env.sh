#!/bin/bash

# Environment Setup Script for Foute Muziek Bingo
# This script helps configure the required environment variables

echo "🎵 Foute Muziek Bingo - Environment Setup"
echo "=========================================="

# Generate secure secrets
echo "Generating secure JWT secrets..."
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
JWT_REFRESH_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")

echo ""
echo "🔐 Required Environment Variables"
echo "Add these to your shell profile (~/.zshrc, ~/.bashrc, etc.) or use them directly:"
echo ""

# Spotify OAuth Configuration
echo "# Spotify OAuth Configuration"
echo "# Get these from https://developer.spotify.com/dashboard"
echo "export SPOTIFY_CLIENT_ID=\"your_spotify_client_id_here\""
echo "export SPOTIFY_CLIENT_SECRET=\"your_spotify_client_secret_here\""
echo "export SPOTIFY_REDIRECT_URI=\"http://localhost:1313/auth/spotify/callback\""
echo ""

# JWT Configuration
echo "# JWT Authentication Configuration"
echo "export JWT_SECRET=\"$JWT_SECRET\""
echo "export JWT_REFRESH_SECRET=\"$JWT_REFRESH_SECRET\""
echo "export JWT_EXPIRES_IN=\"15m\""
echo "export JWT_REFRESH_EXPIRES_IN=\"7d\""
echo ""

# General Secret Key
echo "# General Application Secret"
echo "export SECRET_KEY=\"$SECRET_KEY\""
echo ""

# Supabase Configuration
echo "# Supabase Database Configuration"
echo "# Get these from your Supabase project settings"
echo "export SUPABASE_URL=\"your_supabase_project_url_here\""
echo "export SUPABASE_SERVICE_KEY=\"your_supabase_service_role_key_here\""
echo ""

echo "📋 Setup Instructions:"
echo "1. Create a Spotify app at https://developer.spotify.com/dashboard"
echo "2. Set redirect URI to: http://localhost:1313/auth/spotify/callback"
echo "3. Copy Client ID and Client Secret from Spotify"
echo "4. Set up a Supabase project at https://supabase.com"
echo "5. Copy the project URL and service role key from Supabase settings"
echo "6. Replace the placeholder values above with your actual credentials"
echo ""

# Create a .env.example file
cat > .env.example << EOF
# Spotify OAuth Configuration
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIFY_REDIRECT_URI=http://localhost:1313/auth/spotify/callback

# JWT Authentication Configuration
JWT_SECRET=$JWT_SECRET
JWT_REFRESH_SECRET=$JWT_REFRESH_SECRET
JWT_EXPIRES_IN=15m
JWT_REFRESH_EXPIRES_IN=7d

# General Application Secret
SECRET_KEY=$SECRET_KEY

# Supabase Database Configuration
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_SERVICE_KEY=your_supabase_service_role_key_here
EOF

echo "✅ Created .env.example file with generated secrets"
echo ""
echo "🚀 Quick Test:"
echo "After setting up environment variables, test with:"
echo "python3 -c \"from app.auth_service import JWTService; print('✅ JWT service initialized successfully')\""