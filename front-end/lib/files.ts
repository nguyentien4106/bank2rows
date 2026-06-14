import { apiMessage } from "@/lib/api";
import { FilesService } from "@/lib/client";
import type { FileJobPublic, FileWithJobPublic } from "@/lib/client";
import type { DocRow, DocStatus } from "@/lib/data";

/** Maps a backend FileJob state (pending/running/done/failed) onto the UI pill status. */
export function jobStatus(job: FileJobPublic | null | undefined): DocStatus {
  if (!job) return "proc";
  if (job.state === "done") return "done";
  if (job.state === "failed") return "fail";
  return "proc";
}

/** Percentage of pages extracted so far, when the job reports page counts. */
export function jobProgress(job: FileJobPublic | null | undefined): number | undefined {
  if (!job?.total_pages) return undefined;
  return Math.min(100, Math.round(((job.extracted_pages ?? 0) / job.total_pages) * 100));
}

export function formatBytes(size: number | null | undefined): string {
  if (!size) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function isImageType(contentType: string, filename: string): boolean {
  return /image/i.test(contentType) || /\.(png|jpe?g|tiff?|webp)$/i.test(filename);
}

/** Converts an API file (with its OCR job) into the row shape the tables/feeds render. */
export function toDocRow(f: FileWithJobPublic): DocRow {
  return {
    id: f.id,
    name: f.filename,
    type: isImageType(f.content_type, f.filename) ? "img" : "pdf",
    size: formatBytes(f.size),
    date: formatDate(f.created_at),
    status: jobStatus(f.job),
    pages: f.job?.total_pages ?? 0,
    progress: jobProgress(f.job),
    model: f.job?.model ?? null,
  };
}

/**
 * Downloads the generated export for a parsed file and saves it in the browser.
 * Delegates to the generated SDK; the request interceptor in `@/lib/api` forces a
 * blob responseType for download endpoints so the binary payload survives.
 */
export async function downloadExport(
  fileId: string,
  filename: string,
  type: "xlsx" | "csv" | "json" | "ai" | "html" = "xlsx",
): Promise<void> {
  let data: unknown;
  try {
    data =
      type === "ai"
        ? await FilesService.downloadAiVersionExcel({ fileId })
        : await FilesService.downloadTableExcelFile({ fileId, type });
  } catch (err) {
    throw new Error(apiMessage(err));
  }
  const blob = data instanceof Blob ? data : new Blob([data as BlobPart]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename.replace(/\.[^.]+$/, "")}.${type == "ai" ? "xlsx" : type}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
