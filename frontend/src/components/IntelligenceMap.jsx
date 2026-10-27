import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import "./IntelligenceMap.css";

function FitMarkers({ points }) {
  const map = useMap();
  if (points.length > 1) {
    map.fitBounds(points.map((point) => [point.latitude, point.longitude]), {
      padding: [24, 24],
      maxZoom: 13,
    });
  }
  return null;
}

function IntelligenceMap({ incident, hotspots = [] }) {
  const points = [
    ...(incident ? [{ ...incident, type: "Current incident" }] : []),
    ...hotspots.map((hotspot) => ({
      ...hotspot.center,
      type: `Hotspot · ${hotspot.incident_count} incidents`,
      hotspot,
    })),
  ].filter(
    (point) =>
      Number.isFinite(point.latitude) &&
      Number.isFinite(point.longitude) &&
      point.latitude >= -90 &&
      point.latitude <= 90 &&
      point.longitude >= -180 &&
      point.longitude <= 180,
  );
  if (!points.length) {
    return <p className="intelligence-map-empty">No GPS points are available for this map.</p>;
  }

  const center = [points[0].latitude, points[0].longitude];
  return (
    <div className="intelligence-map">
      <MapContainer center={center} zoom={12} scrollWheelZoom={false}>
        <FitMarkers points={points} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {points.map((point, index) => (
          <CircleMarker
            key={`${point.type}-${index}`}
            center={[point.latitude, point.longitude]}
            radius={point.hotspot ? 11 : 8}
            pathOptions={{
              color: point.hotspot ? "#b45309" : "#aa2f33",
              fillColor: point.hotspot ? "#f59e0b" : "#c83c3c",
              fillOpacity: 0.75,
              weight: 2,
            }}
          >
            <Popup>
              <strong>{point.type}</strong>
              {point.hotspot && (
                <div>
                  {point.hotspot.dominant_category} · {point.hotspot.incident_count} incidents
                </div>
              )}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="intelligence-map-legend">
        <span><i className="map-legend-current" /> Current incident</span>
        <span><i className="map-legend-hotspot" /> DBSCAN hotspot center</span>
      </div>
    </div>
  );
}

export default IntelligenceMap;
