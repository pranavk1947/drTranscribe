#!/bin/bash

# Create logs directory if it doesn't exist
mkdir -p logs

# Optional: Check if API keys are set (not required if they're in settings.yaml)
if [ -n "$GROQ_API_KEY" ]; then
    echo "✓ Using GROQ_API_KEY from environment"
fi

if [ -n "$AZURE_OPENAI_API_KEY" ]; then
    echo "✓ Using AZURE_OPENAI_API_KEY from environment"
fi

# Run the application
echo ""
echo "Starting drTranscribe MVP..."
echo "Server will be available at: http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""
python -m src.main
