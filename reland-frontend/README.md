# RELand Frontend

React frontend for the RELand landmine risk prediction system.

## Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Set up Mapbox Token:**
   - Sign up for a free Mapbox account at: https://account.mapbox.com/auth/signup/
   - Get your access token from: https://account.mapbox.com/access-tokens/
   - Create a `.env` file in this directory:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and add your token:
     ```
     REACT_APP_MAPBOX_TOKEN=pk.your_token_here
     ```

3. **Start the development server:**
   ```bash
   npm start
   ```

The app will open at `http://localhost:3000`

## Requirements

- Node.js and npm installed
- Valid Mapbox access token (free tier available)
- Backend server running on `http://localhost:5001` (see Backend/README.md)
