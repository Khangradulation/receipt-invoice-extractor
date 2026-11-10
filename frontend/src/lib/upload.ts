import { config } from './config';

export const ACCEPTED_TYPES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
};

/** Client-side checks mirroring the API's (the server re-checks everything). */
export function validateFile(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  const type = file.type === 'image/jpg' ? 'image/jpeg' : file.type;
  const allowed = ACCEPTED_TYPES[type];
  if (!allowed) return 'Unsupported file type. Upload a PDF, PNG or JPEG.';
  if (!allowed.includes(ext)) return `The extension "${ext}" does not match the file type.`;
  if (file.size === 0) return 'The file is empty.';
  if (file.size > config.maxUploadBytes) {
    return `File is too large (max ${config.maxUploadBytes / (1024 * 1024)} MB).`;
  }
  return null;
}

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** PUT the file to the signed URL with exactly the headers the API returned, reporting progress. */
export function putWithProgress(
  url: string,
  file: Blob,
  headers: Record<string, string>,
  onProgress: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed (HTTP ${xhr.status}).`));
    xhr.onerror = () => reject(new Error('Upload failed: network error.'));
    xhr.send(file);
  });
}
