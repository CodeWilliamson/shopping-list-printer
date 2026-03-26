import "dotenv/config";
import express from "express";
import { buildPrintJob } from "./jobBuilder.js";
import { createKeepClient } from "./keepClient.js";
import type { PrintJob } from "./types.js";

const app = express();
app.use(express.json());

const keepClient = createKeepClient();
const pollIntervalSeconds = Number(process.env.KEEP_POLL_INTERVAL_SECONDS ?? 30);

let latestJob: PrintJob | null = null;
let lastSeenJobId = "";
let lastPollError: string | null = null;

async function pollKeepOnce(): Promise<void> {
  try {
    const snapshot = await keepClient.fetchSnapshot();
    const job = buildPrintJob(snapshot);

    latestJob = job;
    if (job.jobId !== lastSeenJobId) {
      lastSeenJobId = job.jobId;
      console.log(`[keep-bridge] Updated job ${job.jobId}`);
    }

    lastPollError = null;
  } catch (error) {
    lastPollError = error instanceof Error ? error.message : "Unknown polling error";
    console.error("[keep-bridge] Polling failed", error);
  }
}

app.get("/health", (_req, res) => {
  res.json({
    ok: lastPollError === null,
    lastPollError,
    latestJobId: latestJob?.jobId ?? null
  });
});

app.get("/latest-job", (_req, res) => {
  if (!latestJob) {
    res.status(404).json({ error: "No job available yet" });
    return;
  }

  res.json(latestJob);
});

app.post("/trigger-print", (req, res) => {
  const authHeader = req.header("Authorization");
  const expectedToken = process.env.OPENHAB_API_TOKEN;

  if (expectedToken && authHeader !== `Bearer ${expectedToken}`) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }

  if (!latestJob) {
    res.status(409).json({ error: "No print job prepared yet" });
    return;
  }

  res.json({
    message: "Print trigger accepted",
    jobId: latestJob.jobId,
    job: latestJob
  });
});

const port = Number(process.env.PORT ?? 3001);
app.listen(port, async () => {
  console.log(`[keep-bridge] Listening on :${port}`);

  await pollKeepOnce();
  setInterval(() => {
    void pollKeepOnce();
  }, pollIntervalSeconds * 1000);
});
