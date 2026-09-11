import { useEffect, useState } from "react";
import { UploadCloud, X } from "lucide-react";
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

  useEffect(() => {
    if (!open) {
      setFile(null);
      setResult(null);
      setError(null);
      setProcessing(false);
    }
  }, [open]);

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
          <div>
            <span className="eyebrow">New Source</span>
            <h2>Upload & Process</h2>
          </div>
          <button className="ghostButton iconOnlyButton" onClick={onClose} aria-label="Close upload dialog"><X size={17} /></button>
        </div>
        <label className="uploadBox">
          <input
            type="file"
            accept=".mp4,.mov,.mkv,.pdf,.png,.jpg,.jpeg"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setResult(null);
              setError(null);
            }}
          />
          <strong><UploadCloud size={19} />{file ? "Replace Selected File" : "Choose Video, PDF, Or Image"}</strong>
          <span>MP4, MOV, MKV, PDF, PNG, JPG, JPEG</span>
        </label>
        {file && (
          <div className="filePreview">
            <strong>{file.name}</strong>
            <div className="metadataRow">
              <span>{(file.size / (1024 * 1024)).toFixed(1)} MB</span>
              <span>{file.type || "Unknown type"}</span>
            </div>
          </div>
        )}
        <div className="modalActions">
          <button className="ghostButton" disabled={processing} onClick={onClose}>Cancel</button>
          <button className="primaryButton iconTextButton" disabled={!file || processing} onClick={handleProcess}>
            <UploadCloud size={15} />{processing ? "Processing..." : "Upload & Process"}
          </button>
        </div>
        {processing && <p className="muted">Processing can take a few minutes for video sources.</p>}
        {result && <p className="success">Source ready · {typeof result.stats.index_events === "number" ? result.stats.index_events : 0} indexed events</p>}
        {error && <p className="errorText">{error}</p>}
      </div>
    </div>
  );
}
