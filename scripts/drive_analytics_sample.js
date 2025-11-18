#!/usr/bin/env node
/**
 * Sample query of Admin Reports API for Google Drive activity
 * Queries November 3-5, 2025 as a representative example
 */

const { google } = require("googleapis");
const { OAuth2Client } = require("google-auth-library");
const fs = require("fs");
const path = require("path");
const os = require("os");

// Configuration
const KEY_FILE = path.join(__dirname, "../gmail-mcp/gcp-oauth.admin-reports.desktop.json");
const TOKEN_PATH = path.join(os.homedir(), ".gmail-mcp", "admin-reports.credentials.json");

// Date range: November 3-5, 2025
const START_TIME = "2025-11-03T00:00:00Z";
const END_TIME = "2025-11-05T23:59:59Z";

async function loadCredentials() {
  if (!fs.existsSync(KEY_FILE)) {
    throw new Error(`OAuth keys file not found at ${KEY_FILE}`);
  }

  const keysContent = JSON.parse(fs.readFileSync(KEY_FILE, "utf8"));
  const cfg = keysContent.installed || keysContent.web;
  if (!cfg) {
    throw new Error('Invalid OAuth keys file: missing "installed" or "web"');
  }

  const oauth2Client = new OAuth2Client(
    cfg.client_id,
    cfg.client_secret,
    "http://localhost:3017/oauth2callback"
  );

  if (fs.existsSync(TOKEN_PATH)) {
    try {
      const tokens = JSON.parse(fs.readFileSync(TOKEN_PATH, "utf8"));
      oauth2Client.setCredentials(tokens);
    } catch (e) {
      console.warn(`Failed to load tokens: ${e.message}`);
    }
  }

  return oauth2Client;
}

async function queryDriveActivity() {
  try {
    const oauth2Client = await loadCredentials();
    
    // Ensure we have valid credentials
    const token = await oauth2Client.getAccessToken();
    if (!token.token) {
      throw new Error("No valid access token. Please authenticate first.");
    }

    const admin = google.admin({ version: "reports_v1", auth: oauth2Client });

    console.log(`\nQuerying Drive activity for: ${START_TIME} to ${END_TIME}\n`);
    console.log("This may take a moment...\n");

    const params = {
      userKey: "all",
      applicationName: "drive",
      startTime: START_TIME,
      endTime: END_TIME,
      maxResults: 1000, // Maximum per page
    };

    let allActivities = [];
    let pageCount = 0;
    let nextPageToken = null;

    do {
      if (nextPageToken) {
        params.pageToken = nextPageToken;
      }

      const response = await admin.activities.list(params);
      const activities = response.data.items || [];
      allActivities = allActivities.concat(activities);
      pageCount++;

      console.log(`Page ${pageCount}: Retrieved ${activities.length} activities (Total: ${allActivities.length})`);

      nextPageToken = response.data.nextPageToken;
      
      // Small delay between requests to be respectful of API rate limits
      if (nextPageToken) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    } while (nextPageToken);

    console.log(`\n${"=".repeat(60)}`);
    console.log(`SUMMARY`);
    console.log(`${"=".repeat(60)}`);
    console.log(`Total activities: ${allActivities.length}`);
    console.log(`Pages retrieved: ${pageCount}`);
    console.log(`Date range: ${START_TIME} to ${END_TIME}`);
    console.log(`Time span: 3 days`);

    // Analyze activity types
    const activityTypes = {};
    const actors = new Set();
    const documents = new Set();

    allActivities.forEach((activity) => {
      const actorEmail = activity.actor?.email || "(unknown)";
      actors.add(actorEmail);

      activity.events?.forEach((event) => {
        const eventName = event.name || "unknown";
        activityTypes[eventName] = (activityTypes[eventName] || 0) + 1;

        // Extract document IDs
        event.parameters?.forEach((param) => {
          if (param.name === "doc_id" && param.value) {
            documents.add(param.value);
          }
        });
      });
    });

    console.log(`\n${"=".repeat(60)}`);
    console.log(`ACTIVITY BREAKDOWN`);
    console.log(`${"=".repeat(60)}`);
    console.log(`Unique actors: ${actors.size}`);
    console.log(`Unique documents: ${documents.size}`);
    console.log(`\nActivity types:`);
    Object.entries(activityTypes)
      .sort((a, b) => b[1] - a[1])
      .forEach(([type, count]) => {
        console.log(`  ${type}: ${count}`);
      });

    // Show sample of most active actors
    const actorCounts = {};
    allActivities.forEach((activity) => {
      const email = activity.actor?.email || "(unknown)";
      actorCounts[email] = (actorCounts[email] || 0) + 1;
    });

    console.log(`\n${"=".repeat(60)}`);
    console.log(`TOP 10 MOST ACTIVE USERS`);
    console.log(`${"=".repeat(60)}`);
    Object.entries(actorCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .forEach(([email, count], index) => {
        console.log(`${(index + 1).toString().padStart(2)}. ${email.padEnd(40)} ${count} activities`);
      });

    // Show sample of most active documents
    const docCounts = {};
    allActivities.forEach((activity) => {
      activity.events?.forEach((event) => {
        event.parameters?.forEach((param) => {
          if (param.name === "doc_id" && param.value) {
            const docId = param.value;
            const docTitle = event.parameters.find((p) => p.name === "doc_title")?.value || "(untitled)";
            const key = `${docId}|${docTitle}`;
            docCounts[key] = (docCounts[key] || 0) + 1;
          }
        });
      });
    });

    console.log(`\n${"=".repeat(60)}`);
    console.log(`TOP 10 MOST ACTIVE DOCUMENTS`);
    console.log(`${"=".repeat(60)}`);
    Object.entries(docCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .forEach(([key, count], index) => {
        const [, title] = key.split("|");
        const displayTitle = title.length > 50 ? title.substring(0, 47) + "..." : title;
        console.log(`${(index + 1).toString().padStart(2)}. ${displayTitle.padEnd(50)} ${count} activities`);
      });

    // Show sample activities
    console.log(`\n${"=".repeat(60)}`);
    console.log(`SAMPLE ACTIVITIES (first 5)`);
    console.log(`${"=".repeat(60)}`);
    allActivities.slice(0, 5).forEach((activity, index) => {
      const actor = activity.actor?.email || "(unknown)";
      const time = activity.id?.time || "unknown";
      const event = activity.events?.[0];
      const eventName = event?.name || "unknown";
      const docTitle = event?.parameters?.find((p) => p.name === "doc_title")?.value || "(untitled)";
      
      console.log(`\n${index + 1}. ${time}`);
      console.log(`   Actor: ${actor}`);
      console.log(`   Action: ${eventName}`);
      console.log(`   Document: ${docTitle}`);
    });

    console.log(`\n${"=".repeat(60)}`);
    console.log(`\n✅ Query complete! (Full dataset retrieved)`);
    console.log(`\nPracticality assessment:`);
    if (allActivities.length < 100) {
      console.log(`  ✓ Very manageable volume (< 100 records)`);
    } else if (allActivities.length < 1000) {
      console.log(`  ✓ Manageable volume (< 1,000 records)`);
    } else if (allActivities.length < 10000) {
      console.log(`  ⚠ Moderate volume (1,000-10,000 records) - pagination recommended`);
    } else {
      console.log(`  ⚠ Large volume (> 10,000 records) - requires efficient processing`);
    }

  } catch (error) {
    console.error("\n❌ Error:", error.message);
    if (error.response) {
      console.error("API Response:", JSON.stringify(error.response.data, null, 2));
    }
    process.exit(1);
  }
}

queryDriveActivity();

