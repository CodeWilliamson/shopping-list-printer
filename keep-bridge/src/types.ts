export interface PrintJob {
  jobId: string;
  source: "google-keep";
  timestamp: string;
  title: string;
  uncheckedItems: string[];
  checkedItems: string[];
  footer?: string;
}

export interface KeepSnapshot {
  noteId: string;
  title: string;
  uncheckedItems: string[];
  checkedItems: string[];
  updatedAt: string;
}
