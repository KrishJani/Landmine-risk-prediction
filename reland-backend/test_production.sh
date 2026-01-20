#!/bin/bash
# RELand Backend Production API Test Script
# Tests the production backend on AWS Elastic Beanstalk

PROD_BACKEND="http://reland-backend-prod.eba-2syxv3qs.us-east-1.elasticbeanstalk.com"
echo "Testing RELand Production Backend API"
echo "Backend URL: $PROD_BACKEND"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test 1: API Root
echo -e "${YELLOW}Test 1: GET / (API Root)${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

# Test 2: Get Initial Data
echo -e "${YELLOW}Test 2: GET /api/initial_data${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/api/initial_data")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  AREAS_COUNT=$(echo "$BODY" | jq -r '.areas | length' 2>/dev/null || echo "0")
  echo "Areas found: $AREAS_COUNT"
  if [ "$AREAS_COUNT" -gt 0 ]; then
    echo "$BODY" | jq '.areas[0:5]' 2>/dev/null || echo "$BODY"
  else
    echo -e "${RED}⚠ Warning: No areas found. Database might be empty or not connected.${NC}"
    echo "$BODY"
  fi
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

# Test 3: Get Map Data
echo -e "${YELLOW}Test 3: GET /api/map_data?areas[]=ABEJORRAL${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/api/map_data?areas[]=ABEJORRAL")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  LOCATIONS_COUNT=$(echo "$BODY" | jq 'length' 2>/dev/null || echo "0")
  echo "Locations found: $LOCATIONS_COUNT"
  if [ "$LOCATIONS_COUNT" -gt 0 ]; then
    echo "$BODY" | jq '.[0:2]' 2>/dev/null || echo "$BODY" | head -20
  else
    echo -e "${RED}⚠ Warning: No locations found for ABEJORRAL${NC}"
  fi
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

# Test 4: Get All Labels
echo -e "${YELLOW}Test 4: GET /api/labels${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/api/labels")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  LABELS_COUNT=$(echo "$BODY" | jq 'length' 2>/dev/null || echo "0")
  echo "Labels found: $LABELS_COUNT"
  echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

# Test 5: Get Confirmed Events
echo -e "${YELLOW}Test 5: GET /api/confirmed_events${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/api/confirmed_events")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  EVENTS_COUNT=$(echo "$BODY" | jq 'length' 2>/dev/null || echo "0")
  echo "Confirmed events found: $EVENTS_COUNT"
  if [ "$EVENTS_COUNT" -gt 0 ]; then
    echo "$BODY" | jq '.[0:2]' 2>/dev/null || echo "$BODY" | head -20
  else
    echo "No confirmed events found"
  fi
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

# Test 6: Get Municipality Borders
echo -e "${YELLOW}Test 6: GET /api/municipality_borders${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/api/municipality_borders")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  MUNICIPALITIES_COUNT=$(echo "$BODY" | jq 'length' 2>/dev/null || echo "0")
  echo "Municipalities found: $MUNICIPALITIES_COUNT"
  echo "$BODY" | jq 'keys[0:5]' 2>/dev/null || echo "$BODY" | head -10
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

# Test 7: Geocode
echo -e "${YELLOW}Test 7: GET /api/geocode?address=Bogota, Colombia${NC}"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$PROD_BACKEND/api/geocode?address=Bogota, Colombia")
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')
if [ "$HTTP_STATUS" = "200" ]; then
  echo -e "${GREEN}✓ Status: $HTTP_STATUS${NC}"
  echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
else
  echo -e "${RED}✗ Status: $HTTP_STATUS${NC}"
  echo "$BODY"
fi
echo ""
echo ""

echo -e "${GREEN}=========================================="
echo "Production API Testing Complete!"
echo "==========================================${NC}"
echo ""
echo -e "${BLUE}Frontend URL: http://reland-frontend-prod.s3-website-us-east-1.amazonaws.com${NC}"
echo -e "${BLUE}Backend URL: $PROD_BACKEND${NC}"











