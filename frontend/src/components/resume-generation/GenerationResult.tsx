import type { GenerateResumeResponse } from "../../types/pipeline";

export interface GenerationResultProps {
  response: GenerateResumeResponse;
}

export function GenerationResult({ response }: GenerationResultProps) {
  const pdfOutput = response.available_outputs.find((output) => output.kind === "pdf");

  return (
    <section aria-label="Generation result">
      <h2>Resume generation {response.status}</h2>
      <p>Run ID: {response.run_id}</p>
      {response.warnings.length > 0 ? (
        <div>
          <strong>Warnings</strong>
          <ul>
            {response.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {pdfOutput ? (
        <p>
          Final PDF: <a href={pdfOutput.reference}>{pdfOutput.reference}</a>
        </p>
      ) : response.final_file_reference ? (
        <p>
          Final output: <a href={response.final_file_reference}>{response.final_file_reference}</a>
        </p>
      ) : null}
      {response.available_outputs.length > 0 ? (
        <div>
          <strong>Available outputs</strong>
          <ul>
            {response.available_outputs.map((output) => (
              <li key={`${output.kind}:${output.reference}`}>
                {output.kind} ({output.storage_kind}) - {output.reference}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
