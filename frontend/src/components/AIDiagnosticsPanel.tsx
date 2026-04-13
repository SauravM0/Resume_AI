import { useEffect, useState } from "react";
import { fetchAIDiagnostics, type AIDiagnostics } from "../services/systemHealth";

export function AIDiagnosticsPanel() {
  const [diagnostics, setDiagnostics] = useState<AIDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAIDiagnostics()
      .then(setDiagnostics)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div style={{ padding: 12 }}>Loading AI diagnostics...</div>;
  }

  if (!diagnostics) {
    return <div style={{ padding: 12 }}>Failed to load AI diagnostics</div>;
  }

  const statusColor = diagnostics.configured ? "#28a745" : "#dc3545";

  return (
    <div style={{
      border: "1px solid #ddd",
      borderRadius: 4,
      padding: 16,
      marginBottom: 16,
      backgroundColor: "#f8f9fa",
    }}>
      <h3 style={{ marginTop: 0, marginBottom: 12 }}>AI Provider Status</h3>
      
      <div style={{ display: "grid", gap: 8 }}>
        <div>
          <strong>Provider:</strong> {diagnostics.provider}
        </div>
        <div>
          <strong>Model:</strong> {diagnostics.model}
        </div>
        <div>
          <strong>Status:</strong>{" "}
          <span style={{ color: statusColor, fontWeight: "bold" }}>
            {diagnostics.configured ? "Ready" : "Not Configured"}
          </span>
        </div>
        
        <div>
          <strong>API Key:</strong>{" "}
          {diagnostics.gemini_api_key_configured ? "Configured" : "Not Set"}
        </div>
        
        {diagnostics.errors.length > 0 && (
          <div style={{ color: "#dc3545" }}>
            <strong>Errors:</strong>
            <ul style={{ margin: "4px 0 0 0", paddingLeft: 20 }}>
              {diagnostics.errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}