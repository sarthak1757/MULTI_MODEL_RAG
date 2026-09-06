import type { ProcessResult } from "../types/api";

interface Props {
  result: ProcessResult | null;
  processing: boolean;
}

export default function ProcessingProgress({ result, processing }: Props) {
  if (!processing && !result) return null;
  return (
    <section className="panel">
      <h3>Processing</h3>
      {processing && <p className="muted">Processing source...</p>}
      {result && (
        <ul className="checkList">
          {Object.entries(result.stats).map(([key, value]) => (
            <li key={key}>✓ {key.replace(/_/g, " ")} — {value}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
