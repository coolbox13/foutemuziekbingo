#!/bin/bash
# Foute Muziek Bingo - Application Startup Script

echo "🎵 Starting Foute Muziek Bingo..."
echo "================================="

# Activate virtual environment
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: .env file not found!"
    echo "   Create .env with your Spotify and Supabase credentials"
    echo "   See README for required environment variables"
fi

# Start the application
echo "✅ Virtual environment activated"
echo "🚀 Starting FastAPI server on http://localhost:1313"
echo "   Press Ctrl+C to stop"
echo ""

python app.py