import { ResumeGenerationPage } from "./pages/ResumeGenerationPage";

export default function App() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background:
          "radial-gradient(circle at top, rgba(225, 233, 243, 0.7), rgba(244, 246, 248, 1) 42%)",
      }}
    >
      <ResumeGenerationPage />
    </div>
  );
}
