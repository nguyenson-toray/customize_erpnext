#!/bin/bash
set -e

echo "================================"
echo "🚀 Deploying React to ERPNext"
echo "================================"

# Build React với filenames tĩnh
echo ""
echo "Step 1: Building React app..."
./build-no-hash.sh

# Copy vào public folder
echo ""
echo "Step 2: Copying to public folder..."
rm -rf ../public/static
cp -r build/static ../public/

# Kiểm tra và hiển thị thông tin
if [ -d "build/static/media" ]; then
    echo "  ✓ CSS: public/static/css/"
    echo "  ✓ JS: public/static/js/"
    echo "  ✓ Media: public/static/media/"
    echo "  ✓ Total media files: $(ls -1 build/static/media | wc -l)"
else
    echo "  ⚠ No media folder found"
fi

# Build Frappe assets
echo ""
echo "Step 3: Building Frappe assets..."
cd ~/frappe-bench
bench build --app customize_erpnext --force

# Clear cache
echo ""
echo "Step 4: Clearing cache..."
bench --site erp.tiqn.local clear-cache

echo ""
echo "================================"
echo "✅ Deployment complete!"
echo "================================"
echo "📱 Open: http://erp.tiqn.local/app/shoe-rack-dashboard"
echo ""