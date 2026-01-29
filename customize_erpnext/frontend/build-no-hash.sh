#!/bin/bash
set -e

echo "🔨 Building React app..."
GENERATE_SOURCEMAP=false npm run build

echo "🔄 Removing hashes from filenames..."

# Xử lý CSS files
cd build/static/css
echo "  Processing CSS files..."
for f in main.*.css; do
    if [ -f "$f" ]; then
        cp "$f" main.css
        echo "    ✓ Copied $f → main.css"
    fi
done

# Xử lý JS files  
cd ../js
echo "  Processing JS files..."
for f in main.*.js; do
    if [ -f "$f" ]; then
        cp "$f" main.js
        echo "    ✓ Copied $f → main.js"
    fi
done

cd ../../..
echo " Build complete! Files ready: main.css & main.js"
