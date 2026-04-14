import type { AtsResumePreview as AtsResumePreviewType } from "../../types/pipeline";

export interface AtsResumeCodeViewProps {
  preview: AtsResumePreviewType;
}

export function AtsResumeCodeView({ preview }: AtsResumeCodeViewProps) {
  const header = preview.header;

  if (!preview || !header?.full_name) {
    return (
      <pre style={{ 
        fontFamily: "monospace", 
        fontSize: 12, 
        padding: 16, 
        background: "#f5f5f5",
        borderRadius: 8,
        overflow: "auto"
      }}>
        No ATS preview data available.
      </pre>
    );
  }

  const code = formatAtsCode(preview);

  return (
    <pre style={{
      fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
      fontSize: 11,
      lineHeight: 1.6,
      padding: 16,
      background: "#1a1a1a",
      color: "#e0e0e0",
      borderRadius: 8,
      overflow: "auto",
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
      margin: 0,
    }}>
      {code}
    </pre>
  );
}

function formatAtsCode(preview: AtsResumePreviewType): string {
  const lines: string[] = [];
  const h = preview.header;
  const pageLabel = preview.page_mode === "compact" ? "[1-PAGE CV]" : "[2-PAGE CV]";

  lines.push(`================================================================================`);
  lines.push(`ATS RESUME PREVIEW ${pageLabel}`);
  lines.push(`================================================================================`);
  lines.push(``);
  lines.push(`HEADER`);
  lines.push(`------`);
  lines.push(`Name: ${h.full_name}`);
  if (h.email) lines.push(`Email: ${h.email}`);
  if (h.phone) lines.push(`Phone: ${h.phone}`);
  if (h.location) lines.push(`Location: ${h.location}`);
  if (h.links?.length) {
    lines.push(`Links: ${h.links.join(", ")}`);
  }
  lines.push(``);

  if (preview.target_role) {
    lines.push(`TARGET ROLE`);
    lines.push(`------------`);
    lines.push(preview.target_role);
    lines.push(``);
  }

  if (preview.summary) {
    lines.push(`SUMMARY`);
    lines.push(`-------`);
    lines.push(preview.summary);
    lines.push(``);
  }

  if (preview.core_skills?.length) {
    lines.push(`CORE SKILLS`);
    lines.push(`-----------`);
    lines.push(preview.core_skills.map(s => s.name).join(", "));
    lines.push(``);
  }

  if (preview.experience?.length) {
    lines.push(`EXPERIENCE`);
    lines.push(`----------`);
    preview.experience.forEach((exp, i) => {
      const dateRange = exp.start_date && exp.end_date
        ? `${exp.start_date} – ${exp.end_date}`
        : exp.start_date && exp.current
          ? `${exp.start_date} – Present`
          : exp.start_date || "";
      
      lines.push(`${i + 1}. ${exp.title}`);
      lines.push(`   Company: ${exp.company}`);
      if (dateRange) lines.push(`   Period: ${dateRange}`);
      if (exp.location) lines.push(`   Location: ${exp.location}`);
      if (exp.bullets?.length) {
        lines.push(`   Highlights:`);
        exp.bullets.forEach(b => {
          lines.push(`     - ${b}`);
        });
      }
      lines.push(``);
    });
  }

  if (preview.projects?.length) {
    lines.push(`PROJECTS`);
    lines.push(`--------`);
    preview.projects.forEach((proj, i) => {
      const dateRange = proj.start_date && proj.end_date
        ? `${proj.start_date} – ${proj.end_date}`
        : proj.start_date || "";
      
      lines.push(`${i + 1}. ${proj.name}`);
      if (proj.role) lines.push(`   Role: ${proj.role}`);
      if (dateRange) lines.push(`   Period: ${dateRange}`);
      if (proj.technologies?.length) {
        lines.push(`   Tech: ${proj.technologies.join(", ")}`);
      }
      if (proj.bullets?.length) {
        lines.push(`   Details:`);
        proj.bullets.forEach(b => {
          lines.push(`     - ${b}`);
        });
      }
      lines.push(``);
    });
  }

  if (preview.education?.length) {
    lines.push(`EDUCATION`);
    lines.push(`---------`);
    preview.education.forEach((edu, i) => {
      const dateRange = edu.start_date && edu.end_date
        ? `${edu.start_date} – ${edu.end_date}`
        : edu.start_date || "";
      
      lines.push(`${i + 1}. ${edu.degree}${edu.field_of_study ? ` in ${edu.field_of_study}` : ""}`);
      lines.push(`   Institution: ${edu.institution}`);
      if (dateRange) lines.push(`   Period: ${dateRange}`);
      if (edu.details?.length) {
        lines.push(`   Details: ${edu.details.join(", ")}`);
      }
      lines.push(``);
    });
  }

  if (preview.certifications?.length) {
    lines.push(`CERTIFICATIONS`);
    lines.push(`--------------`);
    preview.certifications.forEach((cert, i) => {
      lines.push(`${i + 1}. ${cert.name}`);
      lines.push(`   Issuer: ${cert.issuer}`);
      if (cert.issue_date) lines.push(`   Date: ${cert.issue_date}`);
      lines.push(``);
    });
  }

  lines.push(`================================================================================`);
  lines.push(`END OF ATS RESUME PREVIEW`);
  lines.push(`================================================================================`);

  return lines.join("\n");
}