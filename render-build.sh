#!/bin/bash
# Render build script to ensure successful installation

echo "Starting Render build process..."

# Set environment variable to prefer pre-built wheels
export PIP_PREFER_BINARY=1

# Upgrade pip
python -m pip install --upgrade pip

# Install requirements with pre-built wheels when possible
# The --no-cache-dir flag helps avoid issues with cached packages
cd Engine && python -m pip install -r requirements.txt --no-cache-dir

echo "Build completed successfully!"
