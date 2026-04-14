import type { AtsResumePreview as AtsResumePreviewType } from "../../types/pipeline";

export interface AtsResumePreviewProps {
  preview: AtsResumePreviewType;
  compact?: boolean;
}

export function AtsResumePreview({ preview, compact = false }: AtsResumePreviewProps) {
  const header = preview.header;
  const pageLabel = preview.page_mode === "compact" ? "1-page" : "2-page";

  if (!preview || !header?.full_name) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--rg-text-subtle)" }}>
        No ATS preview available for this run.
      </div>
    );
  }

  return (
    <div
      className="ats-resume-preview"
      style={{
        fontFamily: "system-ui, -apple-system, sans-serif",
        fontSize: compact ? "12px" : "14px",
        lineHeight: 1.5,
        color: "#1a1a1a",
        background: "#fff",
        padding: compact ? 16 : 24,
        borderRadius: 8,
        border: "1px solid var(--rg-border)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: compact ? 8 : 12,
          borderBottom: "2px solid #222",
          paddingBottom: compact ? 6 : 8,
        }}
      >
        <div>
          <h1
            style={{
              margin: 0,
              fontSize: compact ? "18px" : "22px",
              fontWeight: 700,
              letterSpacing: "-0.02em",
            }}
          >
            {header.full_name}
          </h1>
          {preview.target_role && (
            <p
              style={{
                margin: "2px 0 0",
                fontSize: compact ? "13px" : "15px",
                color: "#444",
                fontWeight: 500,
              }}
            >
              {preview.target_role}
            </p>
          )}
        </div>
        <span
          style={{
            fontSize: compact ? "10px" : "11px",
            background: preview.page_mode === "compact" ? "#e8f5e9" : "#fff3e0",
            color: preview.page_mode === "compact" ? "#2e7d32" : "#e65100",
            padding: "2px 8px",
            borderRadius: 4,
            fontWeight: 600,
          }}
        >
          {pageLabel}
        </span>
      </div>

      <ContactInfo header={header} compact={compact} />

      {preview.summary && (
        <Section title="Summary" compact={compact}>
          <p style={{ margin: 0 }}>{preview.summary}</p>
        </Section>
      )}

      {preview.core_skills && preview.core_skills.length > 0 && (
        <Section title="Core Skills" compact={compact}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {preview.core_skills.map((skill, i) => (
              <span
                key={i}
                style={{
                  background: "#f5f5f5",
                  padding: "2px 8px",
                  borderRadius: 4,
                  fontSize: compact ? "10px" : "11px",
                }}
              >
                {skill.name}
              </span>
            ))}
          </div>
        </Section>
      )}

      {preview.experience && preview.experience.length > 0 && (
        <Section title="Experience" compact={compact}>
          {preview.experience.map((exp, i) => (
            <ExperienceEntry key={i} entry={exp} compact={compact} />
          ))}
        </Section>
      )}

      {preview.projects && preview.projects.length > 0 && (
        <Section title="Projects" compact={compact}>
          {preview.projects.map((proj, i) => (
            <ProjectEntry key={i} entry={proj} compact={compact} />
          ))}
        </Section>
      )}

      {preview.education && preview.education.length > 0 && (
        <Section title="Education" compact={compact}>
          {preview.education.map((edu, i) => (
            <EducationEntry key={i} entry={edu} compact={compact} />
          ))}
        </Section>
      )}

      {preview.certifications && preview.certifications.length > 0 && (
        <Section title="Certifications" compact={compact}>
          {preview.certifications.map((cert, i) => (
            <CertificationEntry key={i} entry={cert} compact={compact} />
          ))}
        </Section>
      )}
    </div>
  );
}

function ContactInfo({ header, compact }: { header: AtsResumePreviewType["header"]; compact: boolean }) {
  const parts: string[] = [];
  if (header.email) parts.push(header.email);
  if (header.phone) parts.push(header.phone);
  if (header.location) parts.push(header.location);

  return (
    <div
      style={{
        fontSize: compact ? "11px" : "12px",
        color: "#444",
        marginBottom: compact ? 8 : 12,
      }}
    >
      {parts.join(" | ")}
      {header.links && header.links.length > 0 && (
        <>
          {parts.length > 0 && " | "}
          {header.links.join(" | ")}
        </>
      )}
    </div>
  );
}

function Section({
  title,
  children,
  compact,
}: {
  title: string;
  children: React.ReactNode;
  compact: boolean;
}) {
  return (
    <div style={{ marginBottom: compact ? 10 : 14 }}>
      <h3
        style={{
          margin: 0,
          fontSize: compact ? "12px" : "13px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "#222",
          borderBottom: "1px solid #ddd",
          paddingBottom: compact ? 2 : 3,
        }}
      >
        {title}
      </h3>
      <div style={{ marginTop: compact ? 4 : 6 }}>{children}</div>
    </div>
  );
}

function ExperienceEntry({
  entry,
  compact,
}: {
  entry: AtsResumePreviewType["experience"][number];
  compact: boolean;
}) {
  const dateRange =
    entry.start_date && entry.end_date
      ? `${entry.start_date} – ${entry.end_date}`
      : entry.start_date
        ? entry.start_date
        : entry.current
          ? `${entry.start_date || ""} – Present`
          : "";

  return (
    <div style={{ marginBottom: compact ? 8 : 10 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div>
          <strong style={{ fontSize: compact ? "12px" : "13px" }}>
            {entry.title}
          </strong>
          <span style={{ color: "#666", marginLeft: 6 }}>{entry.company}</span>
        </div>
        {dateRange && (
          <span
            style={{
              fontSize: compact ? "10px" : "11px",
              color: "#666",
              whiteSpace: "nowrap",
            }}
          >
            {dateRange}
          </span>
        )}
      </div>
      {entry.location && (
        <div style={{ fontSize: compact ? "11px" : "12px", color: "#666" }}>
          {entry.location}
        </div>
      )}
      {entry.bullets && entry.bullets.length > 0 && (
        <ul
          style={{
            margin: compact ? "4px 0 0" : "6px 0 0",
            paddingLeft: compact ? 16 : 18,
            fontSize: compact ? "11px" : "12px",
          }}
        >
          {entry.bullets.slice(0, compact ? 3 : 5).map((bullet, i) => (
            <li key={i} style={{ marginBottom: 2 }}>
              {bullet}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProjectEntry({
  entry,
  compact,
}: {
  entry: AtsResumePreviewType["projects"][number];
  compact: boolean;
}) {
  const dateRange =
    entry.start_date && entry.end_date
      ? `${entry.start_date} – ${entry.end_date}`
      : entry.start_date
        ? entry.start_date
        : "";

  return (
    <div style={{ marginBottom: compact ? 8 : 10 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <strong style={{ fontSize: compact ? "12px" : "13px" }}>
          {entry.name}
        </strong>
        {dateRange && (
          <span
            style={{
              fontSize: compact ? "10px" : "11px",
              color: "#666",
              whiteSpace: "nowrap",
            }}
          >
            {dateRange}
          </span>
        )}
      </div>
      {entry.role && (
        <div style={{ fontSize: compact ? "11px" : "12px", color: "#666" }}>
          {entry.role}
        </div>
      )}
      {entry.technologies && entry.technologies.length > 0 && (
        <div
          style={{
            fontSize: compact ? "10px" : "11px",
            color: "#444",
            marginTop: 2,
          }}
        >
          {entry.technologies.join(", ")}
        </div>
      )}
      {entry.bullets && entry.bullets.length > 0 && (
        <ul
          style={{
            margin: compact ? "4px 0 0" : "6px 0 0",
            paddingLeft: compact ? 16 : 18,
            fontSize: compact ? "11px" : "12px",
          }}
        >
          {entry.bullets.slice(0, compact ? 2 : 3).map((bullet, i) => (
            <li key={i} style={{ marginBottom: 2 }}>
              {bullet}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EducationEntry({
  entry,
  compact,
}: {
  entry: AtsResumePreviewType["education"][number];
  compact: boolean;
}) {
  const dateRange =
    entry.start_date && entry.end_date
      ? `${entry.start_date} – ${entry.end_date}`
      : entry.start_date
        ? entry.start_date
        : "";

  return (
    <div style={{ marginBottom: compact ? 6 : 8 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div>
          <strong style={{ fontSize: compact ? "12px" : "13px" }}>
            {entry.degree}
          </strong>
          {entry.field_of_study && (
            <span style={{ color: "#666", marginLeft: 4 }}>
              {" "}in {entry.field_of_study}
            </span>
          )}
        </div>
        {dateRange && (
          <span
            style={{
              fontSize: compact ? "10px" : "11px",
              color: "#666",
            }}
          >
            {dateRange}
          </span>
        )}
      </div>
      <div style={{ fontSize: compact ? "11px" : "12px", color: "#444" }}>
        {entry.institution}
      </div>
    </div>
  );
}

function CertificationEntry({
  entry,
  compact,
}: {
  entry: AtsResumePreviewType["certifications"][number];
  compact: boolean;
}) {
  return (
    <div style={{ marginBottom: compact ? 4 : 6 }}>
      <strong style={{ fontSize: compact ? "11px" : "12px" }}>{entry.name}</strong>
      <span style={{ color: "#666", marginLeft: 4 }}>
        {entry.issuer}
        {entry.issue_date && ` (${entry.issue_date})`}
      </span>
    </div>
  );
}