import crypto from "node:crypto";
import type { KeepSnapshot, PrintJob } from "./types.js";

export function buildPrintJob(snapshot: KeepSnapshot): PrintJob {
  const timestamp = new Date().toISOString();
  const signaturePayload = `${snapshot.noteId}|${snapshot.updatedAt}|${snapshot.uncheckedItems.join(",")}|${snapshot.checkedItems.join(",")}`;
  const jobId = crypto.createHash("sha256").update(signaturePayload).digest("hex").slice(0, 16);

  return {
    jobId,
    source: "google-keep",
    timestamp,
    title: snapshot.title,
    uncheckedItems: snapshot.uncheckedItems,
    checkedItems: snapshot.checkedItems,
    footer: `Generated ${timestamp}`
  };
}
