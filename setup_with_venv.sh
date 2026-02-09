#!/bin/bash

# drTranscribe MVP Setup Script with Virtual Environment

echo "🚀 Setting up drTranscribe MVP..."

# Check if virtual environment exists
VENV_PATH="../new_venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "⚠️  Virtual environment 'new_venv' not found at $VENV_PATH"
    echo "Creating new virtual environment..."
    python3 -m venv new_venv
    VENV_PATH="./new_venv"
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠️  OPENAI_API_KEY not set!"
    echo "Please set it with: export OPENAI_API_KEY=your_key_here"
    echo "Or create a .env file with: OPENAI_API_KEY=your_key_here"
    echo ""
    read -p "Do you want to enter your OpenAI API key now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your OpenAI API key: " api_key
        export OPENAI_API_KEY=$api_key
        echo "OPENAI_API_KEY=$api_key" > .env
        echo "✅ API key saved to .env"
    else
        echo "❌ Cannot start without API key. Exiting."
        exit 1
    fi
fi

# Create logs directory
mkdir -p logs

# Start the server
echo ""
echo "✅ Setup complete!"
echo ""
echo "🌟 Starting drTranscribe MVP..."
echo "📍 Server will be available at: http://localhost:8000"
echo "🛑 Press Ctrl+C to stop"
echo ""

python -m src.main
