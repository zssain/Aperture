import { useRef, useState } from "react";

import { Button } from "../../components/ui/Button";
import type { IngestionResult } from "./useIngest";

interface DocumentUploadProps {
  file: File | null;
  ingestion: IngestionResult | null;
  disabled?: boolean;
  error?: string | null;
  existingCaseUrl?: string | null;
  onFileChange: (file: File | null) => void;
  onSubmit: () => void;
}

export function DocumentUpload({
  file,
  ingestion,
  disabled = false,
  error,
  existingCaseUrl,
  onFileChange,
  onSubmit,
}: DocumentUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function accept(files: FileList | null): void {
    onFileChange(files?.item(0) ?? null);
  }

  return (
    <section aria-labelledby="upload-heading" className="rounded border border-border bg-surface p-5">
      <div className="mb-4">
        <p className="eyebrow">Step 3 · Statement upload</p>
        <h2 id="upload-heading" className="text-heading font-semibold text-ink">
          Upload financial evidence
        </h2>
        <p id="file-rules" className="mt-1 text-sm text-muted">
          Accepted: UTF-8 CSV with Date, Description, Amount (Balance optional), or PDF. Maximum
          10 MB, 20,000 transaction rows, and 50 PDF pages.
        </p>
      </div>
      <div
        className={`rounded border border-border-strong p-5 text-center ${dragging ? "bg-sunken" : "bg-surface"}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files);
        }}
      >
        <label htmlFor="statement-file" className="block font-medium text-ink">
          Statement file
        </label>
        <p className="my-2 text-sm text-muted">Drop one file here or choose it from your device.</p>
        <input
          ref={inputRef}
          id="statement-file"
          name="statement-file"
          type="file"
          accept=".csv,.pdf,text/csv,application/pdf"
          aria-describedby="file-rules"
          disabled={disabled}
          className="mx-auto block text-sm text-ink"
          onChange={(event) => accept(event.target.files)}
        />
        {file ? (
          <p className="mt-2 text-sm text-ink">
            Selected: {file.name} ({Math.ceil(file.size / 1024)} KB)
          </p>
        ) : null}
      </div>
      {error ? (
        <div role="alert" className="mt-3 rounded border border-negative p-3 text-sm text-negative">
          <p>{error}</p>
          <p className="mt-1">The selected file is retained so you can correct and reselect it.</p>
        </div>
      ) : null}
      {existingCaseUrl ? (
        <p role="status" className="mt-3 text-sm text-caution">
          This file was already ingested. <a className="underline" href={existingCaseUrl}>Open the existing case</a>.
        </p>
      ) : null}
      {ingestion ? <UploadAccounting ingestion={ingestion} /> : null}
      <div className="mt-4">
        <Button type="button" disabled={disabled || file === null} onClick={onSubmit}>
          {disabled ? "Uploading…" : "Upload and start case"}
        </Button>
      </div>
    </section>
  );
}

function UploadAccounting({ ingestion }: { ingestion: IngestionResult }) {
  return (
    <div aria-live="polite" className="mt-4 rounded border border-border bg-sunken p-3">
      <h3 className="text-sm font-medium text-ink">Upload result</h3>
      <dl className="mt-2 grid grid-cols-3 gap-3 text-sm">
        <div><dt className="text-muted">Ingested</dt><dd className="font-medium text-ink">{ingestion.ingested}</dd></div>
        <div><dt className="text-muted">Deduplicated</dt><dd className="font-medium text-ink">{ingestion.deduplicated}</dd></div>
        <div><dt className="text-muted">Rejected</dt><dd className="font-medium text-ink">{ingestion.rejected}</dd></div>
      </dl>
      {ingestion.rejected_reasons.length > 0 ? (
        <div className="mt-3">
          <p className="text-sm font-medium text-ink">Rejected rows and reasons</p>
          <ul className="mt-1 list-disc pl-5 text-sm text-negative">
            {ingestion.rejected_reasons.map((reason, index) => (
              <li key={`${reason.row ?? "row"}-${index}`}>
                Row {reason.row ?? "unknown"}: {reason.reason ?? "invalid row"}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
