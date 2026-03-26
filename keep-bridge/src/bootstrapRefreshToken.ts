import "dotenv/config";
import http from "node:http";
import { URL } from "node:url";
import { OAuth2Client } from "google-auth-library";

const clientId = process.env.KEEP_GOOGLE_CLIENT_ID;
const clientSecret = process.env.KEEP_GOOGLE_CLIENT_SECRET;
const redirectUri = process.env.KEEP_GOOGLE_REDIRECT_URI ?? "http://localhost:8787/oauth2callback";

if (!clientId || !clientSecret) {
  console.error("Missing KEEP_GOOGLE_CLIENT_ID or KEEP_GOOGLE_CLIENT_SECRET in environment.");
  process.exit(1);
}

const oauthClient = new OAuth2Client(clientId, clientSecret, redirectUri);

const authUrl = oauthClient.generateAuthUrl({
  access_type: "offline",
  prompt: "consent",
  scope: ["https://www.googleapis.com/auth/keep.readonly"]
});

const redirect = new URL(redirectUri);
const port = Number(redirect.port || "80");
const callbackPath = redirect.pathname || "/";

console.log("Open this URL in your browser and grant access:");
console.log(authUrl);
console.log(`Waiting for callback on ${redirect.origin}${callbackPath} ...`);

const server = http.createServer(async (req, res) => {
  if (!req.url) {
    res.statusCode = 400;
    res.end("Missing request URL");
    return;
  }

  const callbackUrl = new URL(req.url, redirect.origin);
  if (callbackUrl.pathname !== callbackPath) {
    res.statusCode = 404;
    res.end("Not found");
    return;
  }

  const error = callbackUrl.searchParams.get("error");
  if (error) {
    res.statusCode = 400;
    res.end(`OAuth error: ${error}`);
    console.error(`OAuth error: ${error}`);
    server.close();
    process.exit(1);
    return;
  }

  const code = callbackUrl.searchParams.get("code");
  if (!code) {
    res.statusCode = 400;
    res.end("Missing authorization code");
    console.error("Missing authorization code");
    server.close();
    process.exit(1);
    return;
  }

  try {
    const tokenResponse = await oauthClient.getToken(code);
    const refreshToken = tokenResponse.tokens.refresh_token;

    if (!refreshToken) {
      res.statusCode = 500;
      res.end("No refresh token returned. Re-run and ensure prompt=consent.");
      console.error("No refresh token returned. Re-run with a fresh consent grant.");
      server.close();
      process.exit(1);
      return;
    }

    res.statusCode = 200;
    res.end("Authorization successful. You can close this tab.");

    console.log("\nCopy this into your .env:");
    console.log(`KEEP_GOOGLE_REFRESH_TOKEN=${refreshToken}`);

    server.close();
    process.exit(0);
  } catch (tokenError) {
    res.statusCode = 500;
    res.end("Failed to exchange authorization code.");
    console.error("Failed to exchange authorization code", tokenError);
    server.close();
    process.exit(1);
  }
});

server.listen(port, () => {
  console.log(`OAuth callback server listening on port ${port}`);
});
