import { useState } from "react";
import type { ProcessResult } from "../types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onUploadAndProcess: (file: File) => Promise<ProcessResult>;
}

export default function SourceUploader({ open, onClose, onUploadAndProcess }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleProcess() {
    if (!file) return;
    setProcessing(true);
    setError(null);
    setResult(null);
    try {
      setResult(await onUploadAndProcess(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="modalBackdrop">
      <div className="modal">
        <div className="modalHeader">
          <h2>Upload Source</h2>
          <button className="ghostButton" onClick={onClose}>Close</button>
        </div>
        <div className="uploadBox">
          <input
            type="file"
            accept=".mp4,.mov,.mkv,.pdf,.png,.jpg,.jpeg"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <p>Video · PDF · Image</p>
        </div>
        {file && (
          <div className="filePreview">
            <strong>{file.name}</strong>
            <span>{(file.size / (1024 * 1024)).toFixed(1)} MB</span>
            <span>{file.type || "Unknown type"}</span>
          </div>
        )}
        <button className="primaryButton" disabled={!file || processing} onClick={handleProcess}>
          {processing ? "Processing..." : "Upload & Process"}
        </button>
        {processing && <p className="muted">Processing can take a few minutes for video sources.</p>}
        {result && <p className="success">Source ready · {result.stats.index_events ?? 0} indexed events</p>}
        {error && <p className="errorText">{error}</p>}
      </div>
    </div>
  );
}
