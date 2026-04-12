export interface JsonViewerProps {
  title: string;
  payload: unknown;
  open?: boolean;
}

export function JsonViewer({ title, payload, open = false }: JsonViewerProps) {
  return (
    <details open={open}>
      <summary>{title}</summary>
      <pre
        style={{
          marginTop: 12,
          padding: 12,
          borderRadius: 8,
          background: "#f5f7fa",
          overflowX: "auto",
        }}
      >
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
