#!/bin/bash
# Test health endpoint locally before deploying
# Usage: ./test_health_local.sh

echo "======================================================================"
echo "🧪 Testing Health Endpoint Locally"
echo "======================================================================"

# Check if app can start and health endpoint works
cd "$(dirname "$0")"

echo "1. Testing app import..."
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from app import app
    print('✅ App imported successfully')
    
    # Test health endpoint
    with app.test_client() as client:
        response = client.get('/health')
        print(f'✅ Health endpoint status: {response.status_code}')
        print(f'   Response: {response.get_json()}')
        
        if response.status_code == 200:
            print('✅ Health check PASSED')
            sys.exit(0)
        else:
            print('❌ Health check FAILED')
            sys.exit(1)
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Local health check test PASSED"
    echo "   The app should work in production"
else
    echo ""
    echo "❌ Local health check test FAILED"
    echo "   Fix the issue before deploying"
    exit 1
fi
