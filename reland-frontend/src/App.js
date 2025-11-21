// src/App.js
import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  bearing: 0,  // No rotation - north up
  pitch: 0     // Perfect top-down view - no tilt
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
  const [showConfirmedEvents, setShowConfirmedEvents] = useState(false); // Toggle for confirmed events visibility
  const [showMunicipalityBorders, setShowMunicipalityBorders] = useState(true); // Toggle for municipality borders
  
  // Data state
  const [predictionData, setPredictionData] = useState(null);
  const [historicalData, setHistoricalData] = useState(null);
  const [clusterData, setClusterData] = useState(null);
  const [municipalityBorders, setMunicipalityBorders] = useState(null);

  // Search state
  const [searchText, setSearchText] = useState('');
  
  // Hover state for tooltips
  const [hoveredPoint, setHoveredPoint] = useState(null);
  const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
  const mapRef = useRef(null);
  
  // Label and event management state
  const [userLabels, setUserLabels] = useState([]);
  const [confirmedEvents, setConfirmedEvents] = useState([]);
  const [selectedPoint, setSelectedPoint] = useState(null); // Point clicked for labeling
  const [showLabelDialog, setShowLabelDialog] = useState(false);
  const [showEventsPanel, setShowEventsPanel] = useState(false);
  const [labelForm, setLabelForm] = useState({ 
    label: null, 
    notes: '', 
    manualLat: '', 
    manualLon: '',
    useManualCoords: false 
  });

  // Loading state for map style changes
  const [isStyleLoading, setIsStyleLoading] = useState(false);
  const [mapReady, setMapReady] = useState(false);

  // Edit mode state: 'none', 'labels', or 'events'
  const [editMode, setEditMode] = useState('none');

  
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
      setMunicipalityBorders(null);
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
        console.log(`Confirmed events from map_data: ${data.confirmed_events?.length || 0}`);
        
        // Normalize risk scores to 0-1 range for better visualization
        const normalizeRiskScores = (points) => {
          if (!points || points.length === 0) return points;
          
          // Find min and max risk scores (use risk_score field from new backend)
          const scores = points.map(p => {
            const score = p.risk_score || p.sonson_avg || 0;
            return !isNaN(score) && isFinite(score) && score > 0 ? score : null;
          }).filter(s => s !== null);
          
          if (scores.length === 0) {
            // No valid scores, assign all as low risk (cyan)
            return points.map(p => ({
              ...p,
              risk_score_normalized: 0,
              sonson_avg_normalized: 0
            }));
          }
          
          const minScore = Math.min(...scores);
          const maxScore = Math.max(...scores);
          const range = maxScore - minScore;
          
          // Debug summary (only log once, not per point)
          const normalizedSamples = [];
          const sampleCount = Math.min(5, points.length);
          
          // Normalize to 0-1 range
          // If all scores are the same (range = 0), assign all as low risk (0)
          const normalizedPoints = points.map((p, idx) => {
            const score = p.risk_score || p.sonson_avg || 0;
            
            // Handle edge cases
            if (!isFinite(score) || score <= 0) {
              return {
                ...p,
                risk_score_normalized: 0,
                sonson_avg_normalized: 0
              };
            }
            
            let normalized;
            if (range <= 0 || Math.abs(range) < 1e-10) {
              // All scores are the same - treat as low risk
              normalized = 0;
            } else {
              // Normalize: (score - min) / range
              normalized = Math.max(0, Math.min(1, (score - minScore) / range));
            }
            
            // Collect samples for debugging
            if (idx < sampleCount) {
              normalizedSamples.push({ score, normalized });
            }
            
            return {
              ...p,
              risk_score_normalized: normalized,
              sonson_avg_normalized: normalized
            };
          });
          
          // Log summary once
          console.log(`Risk normalization:`, {
            minScore,
            maxScore,
            range,
            pointsCount: points.length,
            samples: normalizedSamples
          });
          
          return normalizedPoints;
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
        
        // Debug: Check normalized values in GeoJSON
        if (heatmapGeoJSON && heatmapGeoJSON.features.length > 0) {
          const sampleProps = heatmapGeoJSON.features.slice(0, 5).map(f => ({
            risk_score: f.properties.risk_score,
            sonson_avg_normalized: f.properties.sonson_avg_normalized,
            risk_score_normalized: f.properties.risk_score_normalized
          }));
          console.log("Sample normalized values in GeoJSON:", sampleProps);
        }
        
        setPredictionData(heatmapGeoJSON);
        setHistoricalData(toGeoJSON(data.historical_points || []));
        setClusterData(toGeoJSON(data.cluster_points || []));
        
        // Store confirmed events from map_data (only update if we don't have them yet)
        // This prevents overwriting the full list when areas change
        // We use a functional update to avoid dependency issues
        setConfirmedEvents(prevEvents => {
          if (data.confirmed_events) {
            // Only update if we don't have events yet, or if we get more events
            if (prevEvents.length === 0) {
              return data.confirmed_events;
            } else if (data.confirmed_events.length > prevEvents.length) {
              return data.confirmed_events;
            }
          }
          return prevEvents; // Keep existing events
        });
      })
      .catch(err => {
        console.error("Error fetching map data:", err);
        alert("Error fetching map data from backend.");
      });
    
    // Fetch municipality borders for selected areas
    // Only fetch if we have selected areas (don't fetch all borders at once)
    if (selectedAreas.length > 0) {
      const borderParams = new URLSearchParams();
      // Send names as-is (backend will handle normalization)
      selectedAreas.forEach(area => {
        if (area && area.toLowerCase() !== 'unknown') {
          borderParams.append('municipalities[]', area);
        }
      });
      
      // Only fetch if we have valid areas
      if (borderParams.toString()) {
        fetch(`http://localhost:5001/api/municipality_borders?${borderParams.toString()}`)
          .then(res => {
            if (!res.ok) {
              throw new Error(`HTTP error! status: ${res.status}`);
            }
            return res.json();
          })
          .then(data => {
            console.log("Municipality borders received:", data);
            if (data.type === 'FeatureCollection' && data.features && data.features.length > 0) {
              setMunicipalityBorders(data);
              console.log(`Loaded ${data.features.length} municipality borders`);
            } else {
              console.warn("No municipality borders found for selected areas");
              setMunicipalityBorders(null);
            }
          })
          .catch(err => {
            console.error("Error fetching municipality borders:", err);
            // Don't show alert for borders - it's not critical
            setMunicipalityBorders(null);
          });
      } else {
        setMunicipalityBorders(null);
      }
    } else {
      setMunicipalityBorders(null);
    }
      
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

  // Label management handlers
  const handlePointClick = (evt) => {
    if (!mapRef.current) return;

    // If edit mode is 'none', don't handle clicks
    if (editMode === 'none') return;

    const map = mapRef.current.getMap();
    const lngLat = evt.lngLat;

    // Check if clicked on confirmed events layer (for removal)
    if (editMode === 'events') {
      const eventFeatures = map.queryRenderedFeatures(evt.point, {
        layers: ['confirmed-events']
      });
      
      if (eventFeatures.length > 0) {
        // Clicked on an existing event - remove it
        const event = eventFeatures[0].properties;
        handleDeleteEvent(event.id);
        return;
      } else {
        // Clicked on empty space - add new event
        handleAddEventFromMap(lngLat.lat, lngLat.lng);
        return;
      }
    }

    // Labels mode: handle label editing
    if (editMode === 'labels') {
      const features = map.queryRenderedFeatures(evt.point, {
        layers: ['prediction-points']
      });
      
      if (features.length > 0) {
        // Clicked on a prediction point (centroid)
        const feature = features[0];
        const point = feature.properties;
        setSelectedPoint(point);
        // Check if label already exists
        const existingLabel = point.location_id ? userLabels.find(l => l.location_id === point.location_id) : null;
        if (existingLabel) {
          setLabelForm({ 
            label: existingLabel.label, 
            notes: existingLabel.notes || '',
            manualLat: '',
            manualLon: '',
            useManualCoords: false
          });
        } else {
          setLabelForm({ 
            label: null, 
            notes: '',
            manualLat: point.LATITUD_Y?.toFixed(6) || '',
            manualLon: point.LONGITUD_X?.toFixed(6) || '',
            useManualCoords: false
          });
        }
        setShowLabelDialog(true);
      } else {
        // Clicked on empty space - allow manual entry
        setSelectedPoint(null);
        setLabelForm({ 
          label: null, 
          notes: '',
          manualLat: lngLat.lat.toFixed(6),
          manualLon: lngLat.lng.toFixed(6),
          useManualCoords: true
        });
        setShowLabelDialog(true);
      }
    }
  };

  // Add confirmed event from map click
  const handleAddEventFromMap = async (lat, lon) => {
    // Try to find municipality from nearby prediction points
    let municipio = 'Unknown';
    
    if (predictionData && predictionData.features) {
      // Find the closest prediction point to get municipality
      let minDistance = Infinity;
      let closestPoint = null;
      
      predictionData.features.forEach(feature => {
        const pointLat = feature.properties.LATITUD_Y;
        const pointLon = feature.properties.LONGITUD_X;
        if (pointLat && pointLon) {
          // Simple distance calculation (Haversine would be better but this works for nearby points)
          const distance = Math.sqrt(
            Math.pow(lat - pointLat, 2) + Math.pow(lon - pointLon, 2)
          );
          if (distance < minDistance) {
            minDistance = distance;
            closestPoint = feature.properties;
          }
        }
      });
      
      if (closestPoint && closestPoint.Municipio) {
        municipio = closestPoint.Municipio;
      }
    }
    
    // Show confirmation dialog with event details
    const confirmMessage = `Add Confirmed Event?\n\n` +
      `Location: (${lat.toFixed(6)}, ${lon.toFixed(6)})\n` +
      `Municipio: ${municipio}\n` +
      `Source: Manual\n` +
      `Description: Added from map click`;
    
    if (!window.confirm(confirmMessage)) {
      return; // User cancelled
    }
    
    fetch('http://localhost:5001/api/confirmed_events', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        lat: lat,
        lon: lon,
        municipio: municipio,
        source: 'manual',
        description: 'Added from map click'
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          alert(`Error: ${data.error}`);
        } else {
          setConfirmedEvents([...confirmedEvents, data]);
          alert('Confirmed event added successfully!');
        }
      })
      .catch(err => {
        console.error('Error adding event:', err);
        alert('Error adding event. Please try again.');
      });
  };

  const handleSaveLabel = () => {
    if (labelForm.label === null) {
      alert('Please select a label (0 or 1)');
      return;
    }

    // Determine location_id or coordinates
    let location_id = null;
    let lat = null;
    let lon = null;

    if (labelForm.useManualCoords) {
      // Manual coordinate entry
      lat = parseFloat(labelForm.manualLat);
      lon = parseFloat(labelForm.manualLon);
      
      if (isNaN(lat) || isNaN(lon)) {
        alert('Please enter valid coordinates');
        return;
      }
    } else {
      // Clicked on map
      if (!selectedPoint || !selectedPoint.location_id) {
        alert('Please click on a point on the map or enter coordinates manually');
        return;
      }
      location_id = selectedPoint.location_id;
    }

    fetch('http://localhost:5001/api/labels', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        location_id: location_id,
        lat: lat,
        lon: lon,
        label: parseInt(labelForm.label),
        notes: labelForm.notes
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          alert(`Error: ${data.error}`);
        } else {
          // Update local state
          const existingIndex = userLabels.findIndex(l => l.location_id === data.location_id);
          if (existingIndex >= 0) {
            const updated = [...userLabels];
            updated[existingIndex] = data;
            setUserLabels(updated);
          } else {
            setUserLabels([...userLabels, data]);
          }
          
          // Refresh confirmed events if label changed (either to 1 or from 1 to 0)
          fetchConfirmedEvents();
          
          setShowLabelDialog(false);
          setSelectedPoint(null);
          setLabelForm({ label: null, notes: '', manualLat: '', manualLon: '', useManualCoords: false });
          alert('Label saved successfully!');
        }
      })
      .catch(err => {
        console.error('Error saving label:', err);
        alert('Error saving label. Please try again.');
      });
  };

  const handleDeleteLabel = () => {
    if (!selectedPoint) return;
    
    if (!window.confirm('Are you sure you want to delete this label?')) {
      return;
    }

    fetch(`http://localhost:5001/api/labels/${selectedPoint.location_id}`, {
      method: 'DELETE'
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          alert(`Error: ${data.error}`);
        } else {
          setUserLabels(userLabels.filter(l => l.location_id !== selectedPoint.location_id));
          fetchConfirmedEvents(); // Refresh confirmed events
          setShowLabelDialog(false);
          setSelectedPoint(null);
          alert('Label deleted successfully!');
        }
      })
      .catch(err => {
        console.error('Error deleting label:', err);
        alert('Error deleting label. Please try again.');
      });
  };

  // Confirmed events handlers
  const fetchConfirmedEvents = () => {
    fetch('http://localhost:5001/api/confirmed_events')
      .then(res => res.json())
      .then(data => {
        if (data.confirmed_events) {
          console.log(`Fetched ${data.confirmed_events.length} confirmed events from /api/confirmed_events`);
          setConfirmedEvents(data.confirmed_events);
        }
      })
      .catch(err => {
        console.error('Error fetching confirmed events:', err);
      });
  };

  const handleDeleteEvent = (eventId) => {
    if (!window.confirm('Are you sure you want to delete this confirmed event?')) {
      return;
    }

    fetch(`http://localhost:5001/api/confirmed_events/${eventId}`, {
      method: 'DELETE'
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          alert(`Error: ${data.error}`);
        } else {
          setConfirmedEvents(confirmedEvents.filter(e => e.id !== eventId));
          alert('Event deleted successfully!');
        }
      })
      .catch(err => {
        console.error('Error deleting event:', err);
        alert('Error deleting event. Please try again.');
      });
  };

  // Load labels and events on mount
  useEffect(() => {
    fetch('http://localhost:5001/api/labels')
      .then(res => res.json())
      .then(data => {
        if (data.labels) {
          setUserLabels(data.labels);
        }
      })
      .catch(err => console.error('Error fetching labels:', err));
    
    fetchConfirmedEvents();
  }, []);

  // Function to load custom icons - reusable for map load and style changes
  const loadCustomIcons = useCallback(() => {
    if (!mapRef.current) return;
    
    const map = mapRef.current.getMap();
    
    // Wait for style to be loaded before adding images
    if (!map.isStyleLoaded()) {
      // If style not loaded, wait for it
      map.once('style.load', loadCustomIcons);
      return;
    }
    
    // Ensure we have a valid map instance
    if (!map || typeof map.addImage !== 'function') {
      console.warn('Map instance not ready for adding images');
      return;
    }
    
    // Create square icon template (SVG)
    const squareSvgTemplate = (color) => `
      <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" fill="${color}" stroke="white" stroke-width="1"/>
      </svg>
    `;
    
    // Create triangle icon template (SVG)
    const triangleSvgTemplate = (color) => `
      <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg">
        <polygon points="10,2 18,18 2,18" fill="${color}" stroke="white" stroke-width="1"/>
      </svg>
    `;
    
    // Create red triangle for confirmed events
    const redTriangleSvg = triangleSvgTemplate('#ff0000');
    const triangleImg = new Image();
    triangleImg.onload = () => {
      if (map.hasImage('triangle-marker')) {
        map.removeImage('triangle-marker');
      }
      map.addImage('triangle-marker', triangleImg);
    };
    triangleImg.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(redTriangleSvg);
    
    // Create colored square icons for different risk levels
    const squareColors = {
      'low': 'rgb(28,238,238)',    // Cyan
      'medium': 'yellow',           // Yellow
      'high': 'red'                 // Red
    };
    
    Object.entries(squareColors).forEach(([level, color]) => {
      const squareSvg = squareSvgTemplate(color);
      const squareImg = new Image();
      squareImg.onload = () => {
        const iconName = `square-${level}`;
        if (map.hasImage(iconName)) {
          map.removeImage(iconName);
        }
        map.addImage(iconName, squareImg);
      };
      squareImg.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(squareSvg);
    });
    
    // Create a default square icon as fallback
    const defaultSquareSvg = squareSvgTemplate('#888888');
    const defaultSquareImg = new Image();
    defaultSquareImg.onload = () => {
      if (map.hasImage('square-marker')) {
        map.removeImage('square-marker');
      }
      map.addImage('square-marker', defaultSquareImg);
    };
    defaultSquareImg.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(defaultSquareSvg);
  }, []);

  // Handler to load custom icons when map loads
  const handleMapLoad = useCallback(() => {
    loadCustomIcons();
    setIsStyleLoading(false); // Ensure loading is off on initial load
    setMapReady(true); // Mark map as ready
  }, [loadCustomIcons]);

  // Handle style changes with useEffect to track mapStyle changes
  useEffect(() => {
    // Don't run until map is ready (skip initial mount)
    if (!mapReady || !mapRef.current) return;
    
    const map = mapRef.current.getMap();
    if (!map) return;
    
    // Set loading immediately when style changes
    setIsStyleLoading(true);
    
    const handleStyleLoad = () => {
      loadCustomIcons();
      setIsStyleLoading(false);
    };
    
    // Check if style is already loaded (might happen on fast changes)
    if (map.isStyleLoaded()) {
      // Small delay to ensure everything is ready
      const timeoutId = setTimeout(() => {
        loadCustomIcons();
        setIsStyleLoading(false);
      }, 100);
      return () => clearTimeout(timeoutId);
    }
    
    // Wait for style to load
    map.once('style.load', handleStyleLoad);
    
    // Fallback timeout in case event doesn't fire
    const timeoutId = setTimeout(() => {
      if (map.isStyleLoaded()) {
        loadCustomIcons();
        setIsStyleLoading(false);
      } else {
        // If still not loaded after 3 seconds, hide loading anyway
        console.warn('Style load timeout - hiding loading indicator');
        setIsStyleLoading(false);
      }
    }, 3000);
    
    return () => {
      clearTimeout(timeoutId);
      map.off('style.load', handleStyleLoad);
    };
  }, [mapStyle, mapReady, loadCustomIcons]);

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
          <select 
            value={mapStyle} 
            onChange={e => {
              setIsStyleLoading(true);
              setMapStyle(e.target.value);
            }}
          >
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

        <div className="control-group">
          <strong>Municipality Borders</strong>
          <input 
            type="checkbox" 
            id="show-municipality-borders" 
            checked={showMunicipalityBorders}
            onChange={e => setShowMunicipalityBorders(e.target.checked)}
          />
          <label htmlFor="show-municipality-borders">Show Municipality Borders</label>
        </div>

        <div className="control-group">
          <strong>Confirmed Events</strong>
          <input 
            type="checkbox" 
            id="show-confirmed-events" 
            checked={showConfirmedEvents}
            onChange={e => setShowConfirmedEvents(e.target.checked)}
          />
          <label htmlFor="show-confirmed-events">Show Confirmed Events on Map</label>
        </div>

        <div className="control-group">
          <strong>Edit Mode</strong>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'flex', alignItems: 'center', marginBottom: '8px', cursor: 'pointer' }}>
              <input
                type="radio"
                name="editMode"
                value="none"
                checked={editMode === 'none'}
                onChange={(e) => setEditMode(e.target.value)}
                style={{ marginRight: '8px' }}
              />
              <span>None (View Only)</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', marginBottom: '8px', cursor: 'pointer' }}>
              <input
                type="radio"
                name="editMode"
                value="labels"
                checked={editMode === 'labels'}
                onChange={(e) => setEditMode(e.target.value)}
                style={{ marginRight: '8px' }}
              />
              <span>Edit Labels</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
              <input
                type="radio"
                name="editMode"
                value="events"
                checked={editMode === 'events'}
                onChange={(e) => {
                  setEditMode(e.target.value);
                  // Auto-enable confirmed events visibility when entering events edit mode
                  if (e.target.value === 'events') {
                    setShowConfirmedEvents(true);
                  }
                }}
                style={{ marginRight: '8px' }}
              />
              <span>Edit Confirmed Events</span>
            </label>
          </div>
          {editMode === 'labels' && (
            <div style={{ 
              padding: '10px', 
              backgroundColor: '#e7f3ff', 
              borderRadius: '4px', 
              fontSize: '12px',
              marginTop: '5px'
            }}>
              Click on a prediction point (centroid) to add/edit labels
            </div>
          )}
          {editMode === 'events' && (
            <div style={{ 
              padding: '10px', 
              backgroundColor: '#fff3cd', 
              borderRadius: '4px', 
              fontSize: '12px',
              marginTop: '5px'
            }}>
              Click on map to add event, click on existing event to remove
            </div>
          )}
        </div>

        <div className="control-group">
          <strong>Data Management</strong>
          <button 
            onClick={() => {
              setSelectedPoint(null);
              setLabelForm({ 
                label: null, 
                notes: '', 
                manualLat: '', 
                manualLon: '',
                useManualCoords: true 
              });
              setShowLabelDialog(true);
            }}
            style={{
              width: '100%',
              padding: '8px',
              marginTop: '5px',
              backgroundColor: '#28a745',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              marginBottom: '5px'
            }}
          >
            Add Label Manually
          </button>
          <button 
            onClick={() => setShowEventsPanel(!showEventsPanel)}
            style={{
              width: '100%',
              padding: '8px',
              marginTop: '5px',
              backgroundColor: showEventsPanel ? '#007bff' : '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            {showEventsPanel ? 'Hide' : 'Show'} Confirmed Events Panel ({confirmedEvents.length})
          </button>
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
        
        {/* Loading indicator for map style changes */}
        {isStyleLoading && (
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'rgba(255, 255, 255, 0.95)',
            padding: '20px 30px',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            zIndex: 2000,
            fontSize: '16px',
            fontWeight: '500',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            <div className="spinner"></div>
            Loading map style...
          </div>
        )}
        
        <Map
          ref={mapRef}
          {...viewport} // Spread the viewport state
          onLoad={handleMapLoad}
          onMove={evt => setViewport(evt.viewState)} // Update state on move
          cursor={editMode !== 'none' ? 'crosshair' : 'default'}
          onMouseMove={(evt) => {
            // Query features at mouse position using the map instance
            if (mapRef.current) {
              const map = mapRef.current.getMap();
              
              // In events mode, check for events first
              if (editMode === 'events') {
                const eventFeatures = map.queryRenderedFeatures(evt.point, {
                  layers: ['confirmed-events']
                });
                if (eventFeatures.length > 0) {
                  // Change cursor to indicate clickable
                  map.getCanvas().style.cursor = 'pointer';
                  return;
                }
              }
              
              const features = map.queryRenderedFeatures(evt.point, {
                layers: ['prediction-points']
              });
              
              if (features.length > 0) {
                const feature = features[0];
                setHoveredPoint(feature.properties);
                setHoverPosition({ x: evt.point.x, y: evt.point.y });
                if (editMode === 'labels') {
                  map.getCanvas().style.cursor = 'pointer';
                }
              } else {
                setHoveredPoint(null);
                if (editMode !== 'none') {
                  map.getCanvas().style.cursor = 'crosshair';
                }
              }
            }
          }}
          onMouseLeave={() => {
            setHoveredPoint(null);
          }}
          onClick={handlePointClick}
          style={{ width: '100%', height: '100%' }}
          mapStyle={`mapbox://styles/mapbox/${mapStyle}`}
          mapboxAccessToken={MAPBOX_TOKEN}
        >
          <NavigationControl position="top-right" />
          
          {/* --- Map Data Layers --- */}
          {/* We only render the Source and Layer if the data exists */}
          
          {/* 1. Prediction Layer - Square Points */}
          {showPrediction && predictionData && (
            <Source 
              key={`prediction-${mapStyle}`}
              type="geojson" 
              data={predictionData}
            >
              <Layer
                id="prediction-points"
                type="symbol"
                layout={{
                  'icon-image': [
                    'case',
                    ['<', ['get', 'sonson_avg_normalized'], 0.33], 'square-low',
                    ['<', ['get', 'sonson_avg_normalized'], 0.67], 'square-medium',
                    'square-high'
                  ],
                  'icon-size': [
                    'interpolate',
                    ['linear'],
                    ['get', 'sonson_avg_normalized'],
                    0, 0.4,
                    1, 1.0
                  ],
                  'icon-allow-overlap': true,
                  'icon-ignore-placement': true
                }}
                paint={{
                  'icon-opacity': 0.8
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

          {/* 2.5. Municipality Borders Layer */}
          {showMunicipalityBorders && municipalityBorders && (
            <Source 
              key={`borders-${mapStyle}`}
              type="geojson" 
              data={municipalityBorders}
            >
              <Layer
                id="municipality-borders-fill"
                type="fill"
                paint={{
                  'fill-color': 'rgba(0, 123, 255, 0.1)', // Light blue fill
                  'fill-opacity': 0.3
                }}
              />
              <Layer
                id="municipality-borders-outline"
                type="line"
                paint={{
                  'line-color': '#007bff', // Blue outline
                  'line-width': 2,
                  'line-opacity': 0.8
                }}
              />
            </Source>
          )}

          {/* 3. Confirmed Events Layer - Only show if checkbox is checked */}
          {showConfirmedEvents && confirmedEvents.length > 0 && (
            <Source 
              key={`events-${mapStyle}`}
              type="geojson" 
              data={{
                type: 'FeatureCollection',
                features: confirmedEvents.map(event => ({
                  type: 'Feature',
                  geometry: { type: 'Point', coordinates: [event.lon, event.lat] },
                  properties: event
                }))
              }}>
              <Layer
                id="confirmed-events"
                type="symbol"
                layout={{
                  'icon-image': 'triangle-marker',
                  'icon-size': 1.0,
                  'icon-allow-overlap': true,
                  'icon-ignore-placement': true
                }}
                paint={{
                  'icon-opacity': editMode === 'events' ? 1.0 : 0.8
                }}
              />
            </Source>
          )}

          {/* 4. Cluster Layer */}
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
            {hoveredPoint.location_id && editMode !== 'none' && (
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #ddd' }}>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    const point = hoveredPoint;
                    setSelectedPoint(point);
                    const existingLabel = point.location_id ? userLabels.find(l => l.location_id === point.location_id) : null;
                    setLabelForm({ 
                      label: existingLabel ? existingLabel.label : null, 
                      notes: existingLabel ? (existingLabel.notes || '') : '',
                      manualLat: '',
                      manualLon: '',
                      useManualCoords: false
                    });
                    setShowLabelDialog(true);
                  }}
                  style={{
                    width: '100%',
                    padding: '5px',
                    backgroundColor: '#007bff',
                    color: 'white',
                    border: 'none',
                    borderRadius: '3px',
                    cursor: 'pointer',
                    fontSize: '12px'
                  }}
                >
                  {userLabels.find(l => l.location_id === hoveredPoint.location_id) 
                    ? 'Edit Label' 
                    : 'Add Label'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Label Dialog */}
        {showLabelDialog && (
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'white',
            padding: '20px',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            zIndex: 2000,
            minWidth: '350px',
            maxWidth: '550px'
          }}>
            <h3 style={{ marginTop: 0 }}>Add/Edit Label</h3>
            
            {/* Location Source Toggle */}
            <div style={{ marginBottom: '15px', padding: '10px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={labelForm.useManualCoords}
                  onChange={(e) => setLabelForm({ 
                    ...labelForm, 
                    useManualCoords: e.target.checked,
                    manualLat: e.target.checked ? (selectedPoint?.LATITUD_Y?.toFixed(6) || '') : '',
                    manualLon: e.target.checked ? (selectedPoint?.LONGITUD_X?.toFixed(6) || '') : ''
                  })}
                  style={{ marginRight: '8px' }}
                />
                <span>Enter coordinates manually</span>
              </label>
            </div>

            {/* Location Display/Input */}
            {labelForm.useManualCoords ? (
              <div style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px' }}>
                  <strong>Location (Latitude, Longitude):</strong>
                </label>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <input
                    type="number"
                    step="any"
                    placeholder="Latitude"
                    value={labelForm.manualLat}
                    onChange={(e) => setLabelForm({ ...labelForm, manualLat: e.target.value })}
                    style={{
                      flex: 1,
                      padding: '5px',
                      border: '1px solid #ddd',
                      borderRadius: '4px'
                    }}
                  />
                  <span>,</span>
                  <input
                    type="number"
                    step="any"
                    placeholder="Longitude"
                    value={labelForm.manualLon}
                    onChange={(e) => setLabelForm({ ...labelForm, manualLon: e.target.value })}
                    style={{
                      flex: 1,
                      padding: '5px',
                      border: '1px solid #ddd',
                      borderRadius: '4px'
                    }}
                  />
                </div>
                <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
                  Format: (10.576107, -75.427811)
                </div>
              </div>
            ) : (
              <div style={{ marginBottom: '15px' }}>
                <strong>Location:</strong> {selectedPoint ? 
                  `(${selectedPoint.LATITUD_Y?.toFixed(6)}, ${selectedPoint.LONGITUD_X?.toFixed(6)})` : 
                  'Click on map to select location'}
              </div>
            )}
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>
                <strong>Label:</strong>
              </label>
              <div>
                <label style={{ marginRight: '15px' }}>
                  <input
                    type="radio"
                    name="label"
                    value="0"
                    checked={labelForm.label === 0}
                    onChange={(e) => setLabelForm({ ...labelForm, label: parseInt(e.target.value) })}
                  />
                  {' '}0 (Mine-free)
                </label>
                <label>
                  <input
                    type="radio"
                    name="label"
                    value="1"
                    checked={labelForm.label === 1}
                    onChange={(e) => setLabelForm({ ...labelForm, label: parseInt(e.target.value) })}
                  />
                  {' '}1 (Confirmed Mine)
                </label>
              </div>
            </div>
            <div style={{ marginBottom: '15px' }}>
              <label style={{ display: 'block', marginBottom: '5px' }}>
                <strong>Notes (optional):</strong>
              </label>
              <textarea
                value={labelForm.notes}
                onChange={(e) => setLabelForm({ ...labelForm, notes: e.target.value })}
                style={{
                  width: '100%',
                  minHeight: '60px',
                  padding: '5px',
                  border: '1px solid #ddd',
                  borderRadius: '4px'
                }}
                placeholder="Add any notes about this location..."
              />
            </div>
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => {
                  setShowLabelDialog(false);
                  setSelectedPoint(null);
                  setLabelForm({ label: null, notes: '', manualLat: '', manualLon: '', useManualCoords: false });
                }}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              {selectedPoint && userLabels.find(l => l.location_id === selectedPoint.location_id) && (
                <button
                  onClick={handleDeleteLabel}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: '#dc3545',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Delete
                </button>
              )}
              <button
                onClick={handleSaveLabel}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                Save
              </button>
            </div>
          </div>
        )}

        {/* Confirmed Events Panel */}
        {showEventsPanel && (
          <div style={{
            position: 'absolute',
            top: '60px',
            right: '10px',
            width: '400px',
            maxHeight: '70vh',
            background: 'white',
            padding: '15px',
            borderRadius: '8px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            zIndex: 1500,
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h3 style={{ margin: 0 }}>Confirmed Events ({confirmedEvents.length})</h3>
              <button
                onClick={() => setShowEventsPanel(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: '#666'
                }}
              >
                ×
              </button>
            </div>
            {confirmedEvents.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#666', padding: '20px' }}>
                No confirmed events yet. Add labels with value "1" to create events.
              </div>
            ) : (
              <div>
                {confirmedEvents.map(event => (
                  <div
                    key={event.id}
                    style={{
                      border: '1px solid #ddd',
                      borderRadius: '4px',
                      padding: '10px',
                      marginBottom: '10px',
                      backgroundColor: '#f8f9fa'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                      <strong>{event.municipio}</strong>
                      <button
                        onClick={() => handleDeleteEvent(event.id)}
                        style={{
                          background: '#dc3545',
                          color: 'white',
                          border: 'none',
                          borderRadius: '3px',
                          padding: '3px 8px',
                          cursor: 'pointer',
                          fontSize: '11px'
                        }}
                      >
                        Delete
                      </button>
                    </div>
                    <div style={{ fontSize: '12px', color: '#666' }}>
                      <div>Location: ({event.lat?.toFixed(4)}, {event.lon?.toFixed(4)})</div>
                      {event.event_date && (
                        <div>Date: {new Date(event.event_date).toLocaleDateString()}</div>
                      )}
                      {event.source && (
                        <div>Source: {event.source}</div>
                      )}
                      {event.description && (
                        <div style={{ marginTop: '5px', fontStyle: 'italic' }}>{event.description}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;