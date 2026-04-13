import { useCallback, useEffect, useState } from "react";
import { AIDiagnosticsPanel } from "../components/AIDiagnosticsPanel";

export interface MasterProfileData {
  id: string;
  personal_profile: {
    id: string;
    item_type: string;
    full_name: string;
    headline?: string;
    summary?: string;
    email?: string;
    phone?: string;
    location?: string;
    linkedin_url?: string;
    github_url?: string;
    website_url?: string;
  };
  experience: Array<{
    id: string;
    organization: string;
    title: string;
    start_date: { raw_value: string };
    end_date?: { raw_value: string };
    current: boolean;
    bullets: Array<{ id: string; text: string }>;
  }>;
  projects: Array<{
    id: string;
    name: string;
    summary?: string;
    bullets: Array<{ id: string; text: string }>;
  }>;
  education: Array<{
    id: string;
    institution: string;
    degree: string;
  }>;
  certifications: Array<{
    id: string;
    name: string;
    issuer: string;
  }>;
  skills: Array<{
    id: string;
    name: string;
    category: string;
  }>;
}

interface ProfileStatus {
  profile_path: string;
  is_valid: boolean;
  validation_errors: string[];
}

export function MasterProfilePage() {
  const [profile, setProfile] = useState<MasterProfileData | null>(null);
  const [status, setStatus] = useState<ProfileStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [profileRes, statusRes] = await Promise.all([
        fetch("/api/master-profile/raw"),
        fetch("/api/master-profile"),
      ]);
      
      if (!profileRes.ok) {
        throw new Error(`Failed to load profile: ${profileRes.status}`);
      }
      
      const profileData = await profileRes.json();
      const statusData = await statusRes.json();
      
      setProfile(profileData);
      setStatus(statusData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleSave = async () => {
    if (!profile) return;
    
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      
      const response = await fetch("/api/master-profile/raw", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail?.message || "Failed to save profile");
      }
      
      setSuccess("Profile saved successfully!");
      await loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    try {
      setError(null);
      setSuccess(null);
      
      const response = await fetch("/api/master-profile/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      
      const result = await response.json();
      
      if (result.is_valid) {
        setSuccess("Profile is valid!");
      } else {
        setError(`Validation errors: ${result.errors.join(", ")}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to validate profile");
    }
  };

  const updatePersonalField = (field: string, value: string) => {
    if (!profile) return;
    setProfile({
      ...profile,
      personal_profile: {
        ...profile.personal_profile,
        [field]: value || undefined,
      },
    });
  };

  if (loading) {
    return (
      <div style={{ padding: 20 }}>
        <h1>Master Profile</h1>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 20, maxWidth: 800, margin: "0 auto" }}>
      <h1>Master Profile</h1>
      <AIDiagnosticsPanel />
      
      {status && (
        <div style={{ 
          marginBottom: 16, 
          padding: 12, 
          backgroundColor: status.is_valid ? "#d4edda" : "#f8d7da",
          border: `1px solid ${status.is_valid ? "#c3e6cb" : "#f5c6cb"}`,
          borderRadius: 4,
        }}>
          <strong>Status:</strong> {status.is_valid ? "Valid" : "Invalid"}
          <br />
          <small>Profile path: {status.profile_path}</small>
          {status.validation_errors.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <strong>Errors:</strong>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: 20 }}>
                {status.validation_errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      
      {error && (
        <div style={{ 
          marginBottom: 16, 
          padding: 12, 
          backgroundColor: "#f8d7da",
          border: "1px solid #f5c6cb",
          borderRadius: 4,
          color: "#721c24",
        }}>
          {error}
        </div>
      )}
      
      {success && (
        <div style={{ 
          marginBottom: 16, 
          padding: 12, 
          backgroundColor: "#d4edda",
          border: "1px solid #c3e6cb",
          borderRadius: 4,
          color: "#155724",
        }}>
          {success}
        </div>
      )}
      
      {profile && (
        <>
          <section style={{ marginBottom: 24 }}>
            <h2>Personal Information</h2>
            <div style={{ display: "grid", gap: 12 }}>
              <label>
                Full Name:
                <input
                  type="text"
                  value={profile.personal_profile.full_name || ""}
                  onChange={(e) => updatePersonalField("full_name", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                Headline:
                <input
                  type="text"
                  value={profile.personal_profile.headline || ""}
                  onChange={(e) => updatePersonalField("headline", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                Email:
                <input
                  type="email"
                  value={profile.personal_profile.email || ""}
                  onChange={(e) => updatePersonalField("email", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                Phone:
                <input
                  type="tel"
                  value={profile.personal_profile.phone || ""}
                  onChange={(e) => updatePersonalField("phone", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                Location:
                <input
                  type="text"
                  value={profile.personal_profile.location || ""}
                  onChange={(e) => updatePersonalField("location", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                LinkedIn URL:
                <input
                  type="url"
                  value={profile.personal_profile.linkedin_url || ""}
                  onChange={(e) => updatePersonalField("linkedin_url", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                GitHub URL:
                <input
                  type="url"
                  value={profile.personal_profile.github_url || ""}
                  onChange={(e) => updatePersonalField("github_url", e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
              <label>
                Summary:
                <textarea
                  value={profile.personal_profile.summary || ""}
                  onChange={(e) => updatePersonalField("summary", e.target.value)}
                  rows={4}
                  style={{ display: "block", width: "100%", marginTop: 4 }}
                />
              </label>
            </div>
          </section>

          <section style={{ marginBottom: 24 }}>
            <h2>Experience</h2>
            {profile.experience.length === 0 ? (
              <p>No experiences added.</p>
            ) : (
              profile.experience.map((exp, idx) => (
                <div key={exp.id} style={{ border: "1px solid #ddd", padding: 12, marginBottom: 8 }}>
                  <strong>{exp.title}</strong> at {exp.organization}
                  <br />
                  <small>
                    {exp.start_date?.raw_value} - {exp.current ? "Present" : exp.end_date?.raw_value}
                  </small>
                </div>
              ))
            )}
          </section>

          <section style={{ marginBottom: 24 }}>
            <h2>Skills</h2>
            {profile.skills.length === 0 ? (
              <p>No skills added.</p>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {profile.skills.map((skill) => (
                  <span key={skill.id} style={{ 
                    backgroundColor: "#e9ecef", 
                    padding: "4px 8px", 
                    borderRadius: 4,
                  }}>
                    {skill.name} ({skill.category})
                  </span>
                ))}
              </div>
            )}
          </section>

          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: "10px 20px",
                backgroundColor: "#007bff",
                color: "white",
                border: "none",
                borderRadius: 4,
                cursor: saving ? "not-allowed" : "pointer",
              }}
            >
              {saving ? "Saving..." : "Save Profile"}
            </button>
            <button
              onClick={handleValidate}
              disabled={saving}
              style={{
                padding: "10px 20px",
                backgroundColor: "#28a745",
                color: "white",
                border: "none",
                borderRadius: 4,
                cursor: saving ? "not-allowed" : "pointer",
              }}
            >
              Validate Profile
            </button>
            <button
              onClick={loadProfile}
              style={{
                padding: "10px 20px",
                backgroundColor: "#6c757d",
                color: "white",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              Reload
            </button>
          </div>
        </>
      )}
    </div>
  );
}