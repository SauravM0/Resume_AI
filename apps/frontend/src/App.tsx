import { useState } from "react";
import { ResumeGenerationPage } from "./pages/ResumeGenerationPage";
import { MasterProfilePage } from "./pages/MasterProfilePage";

type Page = "generation" | "profile";

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("generation");

  return (
    <div
      style={{
        minHeight: "100vh",
        background:
          "radial-gradient(circle at top, rgba(225, 233, 243, 0.7), rgba(244, 246, 248, 1) 42%)",
      }}
    >
      <nav style={{ 
        padding: "12px 20px", 
        borderBottom: "1px solid #e0e0e0",
        display: "flex",
        gap: 16,
        marginBottom: 16,
      }}>
        <button 
          onClick={() => setCurrentPage("generation")}
          style={{
            padding: "8px 16px",
            backgroundColor: currentPage === "generation" ? "#007bff" : "transparent",
            color: currentPage === "generation" ? "white" : "#007bff",
            border: "1px solid #007bff",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          Resume Generation
        </button>
        <button 
          onClick={() => setCurrentPage("profile")}
          style={{
            padding: "8px 16px",
            backgroundColor: currentPage === "profile" ? "#007bff" : "transparent",
            color: currentPage === "profile" ? "white" : "#007bff",
            border: "1px solid #007bff",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          Master Profile
        </button>
      </nav>
      
      {currentPage === "generation" ? (
        <ResumeGenerationPage />
      ) : (
        <MasterProfilePage />
      )}
    </div>
  );
}
