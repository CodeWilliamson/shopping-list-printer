import type { KeepSnapshot } from "./types.js";
import { google, keep_v1 } from "googleapis";
import { OAuth2Client } from "google-auth-library";

export interface KeepClient {
  fetchSnapshot(): Promise<KeepSnapshot>;
}

export class MockKeepClient implements KeepClient {
  private counter = 0;

  async fetchSnapshot(): Promise<KeepSnapshot> {
    this.counter += 1;

    return {
      noteId: process.env.KEEP_TARGET_NOTE_ID ?? "mock-note",
      title: process.env.PRINT_TITLE ?? "Shopping List",
      uncheckedItems: ["Milk", "Eggs", "Bread"],
      checkedItems: this.counter % 2 === 0 ? ["Apples"] : [],
      updatedAt: new Date().toISOString()
    };
  }
}

export class GoogleKeepClient implements KeepClient {
  private readonly targetNoteId: string;
  private readonly printTitleFallback: string;
  private readonly oauthClient: OAuth2Client;
  private readonly keepApi: keep_v1.Keep;

  constructor() {
    const clientId = process.env.KEEP_GOOGLE_CLIENT_ID;
    const clientSecret = process.env.KEEP_GOOGLE_CLIENT_SECRET;
    const refreshToken = process.env.KEEP_GOOGLE_REFRESH_TOKEN;
    this.targetNoteId = process.env.KEEP_TARGET_NOTE_ID ?? "";
    this.printTitleFallback = process.env.PRINT_TITLE ?? "Shopping List";

    if (!clientId || !clientSecret || !refreshToken || !this.targetNoteId) {
      throw new Error(
        "Missing Keep config. Expected KEEP_GOOGLE_CLIENT_ID, KEEP_GOOGLE_CLIENT_SECRET, KEEP_GOOGLE_REFRESH_TOKEN, KEEP_TARGET_NOTE_ID"
      );
    }

    const redirectUri = process.env.KEEP_GOOGLE_REDIRECT_URI ?? "http://localhost:8787/oauth2callback";

    this.oauthClient = new OAuth2Client(clientId, clientSecret, redirectUri);
    this.oauthClient.setCredentials({ refresh_token: refreshToken });
    this.keepApi = google.keep({ version: "v1", auth: this.oauthClient });
  }

  async fetchSnapshot(): Promise<KeepSnapshot> {
    const noteName = normalizeNoteName(this.targetNoteId);
    const noteResponse = await this.keepApi.notes.get({ name: noteName });
    const note = noteResponse.data;

    const listItems = note.body?.list?.listItems ?? [];
    const uncheckedItems: string[] = [];
    const checkedItems: string[] = [];

    for (const listItem of listItems) {
      const text = extractListItemText(listItem).trim();
      if (!text) {
        continue;
      }

      if (listItem.checked) {
        checkedItems.push(text);
      } else {
        uncheckedItems.push(text);
      }
    }

    return {
      noteId: note.name ?? noteName,
      title: note.title?.trim() || this.printTitleFallback,
      uncheckedItems,
      checkedItems,
      updatedAt: note.updateTime ?? new Date().toISOString()
    };
  }
}

function normalizeNoteName(noteIdOrName: string): string {
  return noteIdOrName.startsWith("notes/") ? noteIdOrName : `notes/${noteIdOrName}`;
}

function extractListItemText(item: keep_v1.Schema$ListItem): string {
  const textField = item.text as unknown;

  if (typeof textField === "string") {
    return textField;
  }

  if (textField && typeof textField === "object") {
    if ("text" in textField && typeof (textField as { text?: unknown }).text === "string") {
      return (textField as { text: string }).text;
    }
  }

  return "";
}

export function createKeepClient(): KeepClient {
  const useMock = process.env.KEEP_USE_MOCK === "true";
  if (useMock) {
    return new MockKeepClient();
  }

  return new GoogleKeepClient();
}
