#!/bin/bash
# RELand Backend API Test Script
# Usage: ./test_api.sh [base_url]
# Default base_url: http://127.0.0.1:5001

BASE_URL="${1:-http://127.0.0.1:5001}"
echo "Testing RELand Backend API at: $BASE_URL"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: API Root
echo -e "${YELLOW}Test 1: GET / (API Root)${NC}"
curl -s -X GET "$BASE_URL/" | jq '.' || echo "Response received"
echo ""
echo ""

# Test 2: Get Initial Data
echo -e "${YELLOW}Test 2: GET /api/initial_data${NC}"
curl -s -X GET "$BASE_URL/api/initial_data" | jq '.' || echo "Response received"
echo ""
echo ""

# Test 3: Get Map Data (single area)
echo -e "${YELLOW}Test 3: GET /api/map_data?areas[]=ABEJORRAL${NC}"
curl -s -X GET "$BASE_URL/api/map_data?areas[]=ABEJORRAL" | jq '. | {total_locations: (. | length), sample: .[0:2]}' || echo "Response received"
echo ""
echo ""

# Test 4: Get Map Data (multiple areas)
echo -e "${YELLOW}Test 4: GET /api/map_data?areas[]=ABEJORRAL&areas[]=SONSÓN${NC}"
curl -s -X GET "$BASE_URL/api/map_data?areas[]=ABEJORRAL&areas[]=SONSÓN" | jq '. | {total_locations: (. | length), sample: .[0:2]}' || echo "Response received"
echo ""
echo ""

# Test 5: Get All Labels
echo -e "${YELLOW}Test 5: GET /api/labels${NC}"
curl -s -X GET "$BASE_URL/api/labels" | jq '.' || echo "Response received"
echo ""
echo ""

# Test 6: Add/Update Label
echo -e "${YELLOW}Test 6: POST /api/labels (Add/Update Label)${NC}"
LABEL_RESPONSE=$(curl -s -X POST "$BASE_URL/api/labels" \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": 1,
    "label": 1
  }')
echo "$LABEL_RESPONSE" | jq '.' || echo "$LABEL_RESPONSE"
LOCATION_ID=$(echo "$LABEL_RESPONSE" | jq -r '.location_id // 1')
echo ""
echo ""

# Test 7: Get Confirmed Events
echo -e "${YELLOW}Test 7: GET /api/confirmed_events${NC}"
curl -s -X GET "$BASE_URL/api/confirmed_events" | jq '. | {total_events: (. | length), sample: .[0:2]}' || echo "Response received"
echo ""
echo ""

# Test 8: Add Confirmed Event
echo -e "${YELLOW}Test 8: POST /api/confirmed_events (Add Event)${NC}"
EVENT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/confirmed_events" \
  -H "Content-Type: application/json" \
  -d '{
    "location_id": 1,
    "event_type": "landmine",
    "date": "2024-01-15",
    "notes": "Test event from API"
  }')
echo "$EVENT_RESPONSE" | jq '.' || echo "$EVENT_RESPONSE"
EVENT_ID=$(echo "$EVENT_RESPONSE" | jq -r '.id // empty')
echo ""
echo ""

# Test 9: Update Confirmed Event (if event was created)
if [ ! -z "$EVENT_ID" ] && [ "$EVENT_ID" != "null" ]; then
  echo -e "${YELLOW}Test 9: PUT /api/confirmed_events/$EVENT_ID (Update Event)${NC}"
  curl -s -X PUT "$BASE_URL/api/confirmed_events/$EVENT_ID" \
    -H "Content-Type: application/json" \
    -d '{
      "event_type": "landmine",
      "date": "2024-01-16",
      "notes": "Updated test event"
    }' | jq '.' || echo "Response received"
  echo ""
  echo ""
fi

# Test 10: Get Municipality Borders
echo -e "${YELLOW}Test 10: GET /api/municipality_borders${NC}"
curl -s -X GET "$BASE_URL/api/municipality_borders" | jq '. | {municipalities: (. | length), sample: .[0:1] | keys}' || echo "Response received"
echo ""
echo ""

# Test 11: Geocode Address
echo -e "${YELLOW}Test 11: GET /api/geocode?address=Bogota, Colombia${NC}"
curl -s -X GET "$BASE_URL/api/geocode?address=Bogota, Colombia" | jq '.' || echo "Response received"
echo ""
echo ""

# Test 12: Get Job Status (if Redis is available)
echo -e "${YELLOW}Test 12: GET /api/jobs${NC}"
curl -s -X GET "$BASE_URL/api/jobs" | jq '.' || echo "Response received"
echo ""
echo ""

# Test 13: Delete Label (cleanup)
echo -e "${YELLOW}Test 13: DELETE /api/labels/$LOCATION_ID (Cleanup)${NC}"
curl -s -X DELETE "$BASE_URL/api/labels/$LOCATION_ID" | jq '.' || echo "Response received"
echo ""
echo ""

# Test 14: Delete Confirmed Event (cleanup)
if [ ! -z "$EVENT_ID" ] && [ "$EVENT_ID" != "null" ]; then
  echo -e "${YELLOW}Test 14: DELETE /api/confirmed_events/$EVENT_ID (Cleanup)${NC}"
  curl -s -X DELETE "$BASE_URL/api/confirmed_events/$EVENT_ID" | jq '.' || echo "Response received"
  echo ""
  echo ""
fi

echo -e "${GREEN}=========================================="
echo "API Testing Complete!"
echo "==========================================${NC}"











