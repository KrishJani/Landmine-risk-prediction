// src/App.js
import React, { useState, useEffect, useRef } from 'react';
import Map, { Source, Layer, NavigationControl } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import './App.css'; // We will create this file for styling

// --- Mapbox Configuration ---
// Get token from environment variable or use fallback
// To set up: Create a .env file in reland-frontend/ with: REACT_APP_MAPBOX_TOKEN=your_token_here
// const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN || 'pk.eyJ1IjoicWl3YW5nYWFhIiwiYSI6ImNremtyNmxkNzR5aGwyb25mOWxocmxvOGoifQ.7ELp2wgswTdQZS_RsnW1PA';
const MAPBOX_TOKEN = 'pk.eyJ1Ijoia3JyaXNoMjUiLCJhIjoiY21oamRmbnptMWNhdjJrcHFqaXoybWo0cSJ9.-fbOe_Xt-AJvinYHStN0ew';


// This is the default center from your Dash app
const initialViewport = {
  latitude: 5.920689177,
  longitude: -75.10525796,
  zoom: 9,
  bearing: 25,
  pitch: 40
};

// --- Layer Styles (from your Dash app) ---
// We define the styles for our data layers here
const predictionLayerStyle = {
  id: 'prediction-heatmap',
  type: 'heatmap',
  paint: {
    // Colors from your 'scl' variable
    'heatmap-color': [
      'interpolate',
      ['linear'],
      ['heatmap-density'],
      0, 'rgba(28,238,238,0)', // Cyan (low) - transparent
      0.5, 'yellow',           // Yellow (mid)
      1, 'red'                  // Red (high)
    ],
    'heatmap-radius': [
      'interpolate',
      ['linear'],
      ['get', 'sonson_avg_normalized'],
      0, 5,
      1, 20
    ],
    'heatmap-intensity': 1.5,
    'heatmap-weight': [
      'interpolate',
      ['linear'],
      ['get', 'sonson_avg_normalized'],
      0, 0,
      0.1, 1,
      1, 5
    ],
    'heatmap-opacity': 0.7
  }
};

const historicalLayerStyle = {
  id: 'historical-points',
  type: 'circle',
  paint: {
    'circle-radius': 5,
    'circle-color': ['get', 'colorBasedLabel'] // Color from our backend
  }
};

const clusterLayerStyle = {
  id: 'cluster-points',
  type: 'circle',
  paint: {
    'circle-radius': 5,
    'circle-color': ['get', 'colorBasedCluster'] // Color from our backend
  }
};


function App() {
  // --- React State ---
  // This is how React stores data, replacing Dash's 'value' properties.
  
  // Viewport state (where the map is looking)
  const [viewport, setViewport] = useState(initialViewport);
  
  // UI Controls state
  const [mapStyle, setMapStyle] = useState('streets-v11'); // 'streets'
  const [allAreas, setAllAreas] = useState([]); // For the dropdown options
  const [selectedAreas, setSelectedAreas] = useState([]); // The selected dropdown values
  
  // Layer visibility state
  const [showPrediction, setShowPrediction] = useState(true);
  const [showHistorical, setShowHistorical] = useState([]); // Stores [-1, 0, 1]
  const [showClusters, setShowClusters] = useState([]); // Stores [0, 1, 2]
  
  // Data state
  const [predictionData, setPredictionData] = useState(null);
  const [historicalData, setHistoricalData] = useState(null);
  const [clusterData, setClusterData] = useState(null);

  // Search state
  const [searchText, setSearchText] = useState('');
  
  // Hover state for tooltips
  const [hoveredPoint, setHoveredPoint] = useState(null);
  const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
  const mapRef = useRef(null);

  
  // --- Data Fetching (Side Effects) ---
  
  // 1. Fetch the list of areas for the dropdown ONCE when the app loads
  useEffect(() => {
    // This 'useEffect' with an empty array [] runs only once.
    fetch('http://localhost:5001/api/initial_data')
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then(data => {
        console.log("Initial data received:", data);
        setAllAreas(data.areas || []);
        setSelectedAreas(data.areas || []); // Select all by default
      })
      .catch(err => {
        console.error("Error fetching initial data:", err);
        alert("Error connecting to backend. Make sure the backend server is running on http://localhost:5001");
      });
  }, []);

  // 2. Fetch map data WHENEVER the 'selectedAreas' state changes
  useEffect(() => {
    // This 'useEffect' runs every time 'selectedAreas' is updated.
    
    // Don't fetch if no areas are selected
    if (selectedAreas.length === 0) {
      setPredictionData(null);
      setHistoricalData(null);
      setClusterData(null);
      return;
    }
    
    // Create the query string (e.g., "?areas[]=Sonsón&areas[]=Argelia")
    const params = new URLSearchParams();
    selectedAreas.forEach(area => params.append('areas[]', area));
    
    // Fetch data from our Python backend!
    fetch(`http://localhost:5001/api/map_data?${params.toString()}`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then(data => {
        console.log("Map data received:", data);
        console.log(`Risk heatmap points: ${data.risk_heatmap_points?.length || 0}`);
        console.log(`Historical points: ${data.historical_points?.length || 0}`);
        
        // Normalize risk scores to 0-1 range for better visualization
        const normalizeRiskScores = (points) => {
          if (!points || points.length === 0) return points;
          
          // Find min and max risk scores (use risk_score field from new backend)
          const scores = points.map(p => p.risk_score || p.sonson_avg || 0).filter(s => !isNaN(s) && isFinite(s));
          if (scores.length === 0) return points;
          
          const minScore = Math.min(...scores);
          const maxScore = Math.max(...scores);
          const range = maxScore - minScore;
          
          console.log(`Risk score range: ${minScore} to ${maxScore}`);
          
          // Normalize to 0-1 range
          return points.map(p => ({
            ...p,
            risk_score_normalized: range > 0 
              ? ((p.risk_score || p.sonson_avg || 0) - minScore) / range 
              : (p.risk_score || p.sonson_avg || 0),
            // Keep sonson_avg_normalized for backward compatibility with layer styles
            sonson_avg_normalized: range > 0 
              ? ((p.risk_score || p.sonson_avg || 0) - minScore) / range 
              : (p.risk_score || p.sonson_avg || 0)
          }));
        };
        
        // We need to format this data into GeoJSON, the standard for maps
        const toGeoJSON = (points) => {
          if (!points || points.length === 0) return null;
          return {
            type: 'FeatureCollection',
            features: points.map(p => ({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: [p.LONGITUD_X, p.LATITUD_Y] },
              properties: p // Attach all other data (risk, color, etc.)
            }))
          };
        };
        
        // Use risk_heatmap_points from new backend structure
        const heatmapPoints = data.risk_heatmap_points || data.prediction_points || [];
        const normalizedHeatmapPoints = normalizeRiskScores(heatmapPoints);
        const heatmapGeoJSON = toGeoJSON(normalizedHeatmapPoints);
        console.log("Heatmap GeoJSON created:", heatmapGeoJSON ? `${heatmapGeoJSON.features.length} features` : "null");
        
        setPredictionData(heatmapGeoJSON);
        setHistoricalData(toGeoJSON(data.historical_points || []));
        setClusterData(toGeoJSON(data.cluster_points || []));
      })
      .catch(err => {
        console.error("Error fetching map data:", err);
        alert("Error fetching map data from backend.");
      });
      
  }, [selectedAreas]); // The "dependency array" - this re-runs the effect

  
  // --- Event Handlers ---
  
  const handleAreaChange = (e) => {
    // Get all selected options from the <select> element
    const options = [...e.target.selectedOptions];
    const values = options.map(opt => opt.value);
    setSelectedAreas(values);
  };
  
  const handleSelectAllAreas = (e) => {
    if (e.target.checked) {
      setSelectedAreas(allAreas);
    } else {
      setSelectedAreas([]);
    }
  };

  const handleHistoricalChange = (e) => {
    const value = parseInt(e.target.value);
    let newSelection;
    if (e.target.checked) {
      newSelection = [...showHistorical, value];
    } else {
      newSelection = showHistorical.filter(item => item !== value);
    }
    setShowHistorical(newSelection);
  };
  
  // (Similar handlers for 'Select All Historical', 'Cluster Change', etc.
  // can be added here)
  
  const handleSearch = () => {
    if (!searchText.trim()) {
      alert("Please enter a search term.");
      return;
    }
    
    // Call our NEW backend geocoding endpoint
    fetch(`http://localhost:5001/api/geocode?address=${encodeURIComponent(searchText)}`)
      .then(res => {
        if (!res.ok) {
          return res.json().then(data => {
            throw new Error(data.error || `HTTP error! status: ${res.status}`);
          });
        }
        return res.json();
      })
      .then(data => {
        if (data.lat && data.lon) {
          // Fly to the new location
          setViewport({
            ...viewport,
            latitude: data.lat,
            longitude: data.lon,
            zoom: 15,
            transitionDuration: 1000 // Smooth animation
          });
        } else {
          alert(`Could not find address: ${data.error || 'Unknown error'}`);
        }
      })
      .catch(err => {
        console.error("Geocoding error:", err);
        alert(`Geocoding error: ${err.message || 'Could not connect to geocoding service. Make sure the backend is running.'}`);
      });
  };
  

  // --- JSX (The UI Rendering) ---
  // This is the React equivalent of your 'app.layout'
  return (
    <div className="app-container">
      
      {/* --- Left Control Panel (Future Feature #4) --- */}
      <div className="control-panel">
        <h2>RELand: Risk Estimator</h2>
        <hr />
        
        <div className="control-group">
          <strong>Map Style</strong>
          <select value={mapStyle} onChange={e => setMapStyle(e.target.value)}>
            <option value="streets-v11">Street</option>
            <option value="satellite-streets-v11">Satellite Streets</option>
            <option value="outdoors-v11">Outdoors</option>
          </select>
        </div>
        
        <div className="control-group">
          <strong>Choose Areas</strong>
          <div>
            <input 
              type="checkbox" 
              id="select-all-areas"
              checked={selectedAreas.length === allAreas.length}
              onChange={handleSelectAllAreas} 
            />
            <label htmlFor="select-all-areas">Show All Regions</label>
          </div>
          <select 
            multiple={true} 
            value={selectedAreas} 
            onChange={handleAreaChange}
            className="area-select"
          >
            {allAreas.map(area => (
              <option key={area} value={area}>{area}</option>
            ))}
          </select>
        </div>
        
        <div className="control-group">
          <strong>Risk Prediction</strong>
          <input 
            type="checkbox" 
            id="show-prediction" 
            checked={showPrediction}
            onChange={e => setShowPrediction(e.target.checked)}
          />
          <label htmlFor="show-prediction">Show RELand Risk Prediction</label>
        </div>

        {/* Historical Events section - commented out for now */}
        {/* 
        <div className="control-group">
          <strong>Historical Events</strong>
          <div className="checkbox-group">
            <input type="checkbox" id="hist-neg" value={0} onChange={handleHistoricalChange} />
            <label htmlFor="hist-neg">Areas declared mine-free</label>
          </div>
          <div className="checkbox-group">
            <input type="checkbox" id="hist-pos" value={1} onChange={handleHistoricalChange} />
            <label htmlFor="hist-pos">Areas affected by landmines</label>
          </div>
          <div className="checkbox-group">
            <input type="checkbox" id="hist-unk" value={-1} onChange={handleHistoricalChange} />
            <label htmlFor="hist-unk">Areas with no historical data</label>
          </div>
        </div>
        */}
        
        {/* Add "Danger Zones" (Clusters) controls here... */}
        
      </div>
      
      {/* --- Main Map Area --- */}
      <div className="map-container">
        <div className="search-bar">
          <input 
            type="text" 
            placeholder="Search for street or area..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSearch()}
          />
          <button onClick={handleSearch}>Find</button>
        </div>
        
        <Map
          ref={mapRef}
          {...viewport} // Spread the viewport state
          onMove={evt => setViewport(evt.viewState)} // Update state on move
          onMouseMove={(evt) => {
            // Query features at mouse position using the map instance
            if (mapRef.current) {
              const map = mapRef.current.getMap();
              const features = map.queryRenderedFeatures(evt.point, {
                layers: ['prediction-points']
              });
              
              if (features.length > 0) {
                const feature = features[0];
                setHoveredPoint(feature.properties);
                setHoverPosition({ x: evt.point.x, y: evt.point.y });
              } else {
                setHoveredPoint(null);
              }
            }
          }}
          onMouseLeave={() => {
            setHoveredPoint(null);
          }}
          style={{ width: '100%', height: '100%' }}
          mapStyle={`mapbox://styles/mapbox/${mapStyle}`}
          mapboxAccessToken={MAPBOX_TOKEN}
        >
          <NavigationControl position="top-right" />
          
          {/* --- Map Data Layers --- */}
          {/* We only render the Source and Layer if the data exists */}
          
          {/* 1. Prediction Layer - Heatmap */}
          {showPrediction && predictionData && (
            <Source type="geojson" data={predictionData}>
              <Layer {...predictionLayerStyle} />
            </Source>
          )}
          
          {/* 1b. Prediction Layer - Circle Points (for hover interaction) */}
          {showPrediction && predictionData && (
            <Source type="geojson" data={predictionData}>
              <Layer
                id="prediction-points"
                type="circle"
                paint={{
                  'circle-radius': [
                    'interpolate',
                    ['linear'],
                    ['get', 'sonson_avg_normalized'],
                    0, 3,
                    1, 8
                  ],
                  'circle-color': [
                    'interpolate',
                    ['linear'],
                    ['get', 'sonson_avg_normalized'],
                    0, 'rgb(28,238,238)', // Cyan (low risk)
                    0.5, 'yellow',        // Yellow (mid risk)
                    1, 'red'               // Red (high risk)
                  ],
                  'circle-opacity': 0.6,
                  'circle-stroke-width': 1,
                  'circle-stroke-color': '#fff'
                }}
              />
            </Source>
          )}
          
          {/* Debug: Show prediction data count */}
          {showPrediction && predictionData && (
            <div style={{
              position: 'absolute',
              bottom: 10,
              left: 10,
              background: 'rgba(255,255,255,0.8)',
              padding: '5px 10px',
              borderRadius: '5px',
              fontSize: '12px',
              zIndex: 1000
            }}>
              Showing {predictionData.features.length} prediction points
            </div>
          )}

          {/* 2. Historical Layer - commented out for now */}
          {/* {historicalData && (
            <Source type="geojson" data={historicalData}>
              <Layer 
                {...historicalLayerStyle} 
                // Filter based on the checkboxes
                filter={['in', 'mines_outcome', ...showHistorical]}
              />
            </Source>
          )} */}

          {/* 3. Cluster Layer */}
          {/* Add this layer similar to the historical one... */}
          
        </Map>
        
        {/* Hover Tooltip - positioned relative to map container */}
        {hoveredPoint && (
          <div style={{
            position: 'absolute',
            left: hoverPosition.x,
            top: hoverPosition.y,
            background: 'rgba(255, 255, 255, 0.95)',
            padding: '10px',
            borderRadius: '5px',
            boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            pointerEvents: 'none',
            zIndex: 1000,
            transform: 'translate(-50%, -100%)',
            marginTop: '-10px',
            fontSize: '13px',
            lineHeight: '1.5',
            minWidth: '200px'
          }}>
            <div style={{ fontWeight: 'bold', marginBottom: '5px', color: '#007bff' }}>
              Location Details
            </div>
            <div>
              <strong>Location:</strong> ({hoveredPoint.LATITUD_Y?.toFixed(6)}, {hoveredPoint.LONGITUD_X?.toFixed(6)})
            </div>
            <div>
              <strong>Prediction Risk:</strong> {(hoveredPoint.risk_score || hoveredPoint.sonson_avg)?.toFixed(6) || 'N/A'}
            </div>
            {hoveredPoint.risk_level && (
              <div>
                <strong>Risk Level:</strong> {hoveredPoint.risk_level}
              </div>
            )}
            {hoveredPoint.Municipio && (
              <div>
                <strong>Municipio:</strong> {hoveredPoint.Municipio}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;