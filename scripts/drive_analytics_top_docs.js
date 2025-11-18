#!/usr/bin/env node
/**
 * Analyze Drive activity to find top documents by edit, share, and view activity
 * Uses previously retrieved data or queries fresh data
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

async function queryAllActivities() {
  const oauth2Client = await loadCredentials();
  
  const token = await oauth2Client.getAccessToken();
  if (!token.token) {
    throw new Error("No valid access token. Please authenticate first.");
  }

  const admin = google.admin({ version: "reports_v1", auth: oauth2Client });

  console.log(`\nQuerying Drive activity for: ${START_TIME} to ${END_TIME}\n`);
  console.log("Retrieving all activities...\n");

  const params = {
    userKey: "all",
    applicationName: "drive",
    startTime: START_TIME,
    endTime: END_TIME,
    maxResults: 1000,
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

    if (pageCount % 5 === 0) {
      console.log(`  Retrieved ${pageCount} pages (${allActivities.length} activities so far)...`);
    }

    nextPageToken = response.data.nextPageToken;
    
    if (nextPageToken) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  } while (nextPageToken);

  console.log(`\n✅ Retrieved ${allActivities.length} total activities across ${pageCount} pages\n`);
  return allActivities;
}

function analyzeTopDocuments(activities) {
  // Track documents by activity type
  const editCounts = {};      // doc_id -> {title, count}
  const shareCounts = {};     // doc_id -> {title, count}
  const viewCounts = {};      // doc_id -> {title, count}

  activities.forEach((activity) => {
    activity.events?.forEach((event) => {
      const eventName = event.name;
      
      // Extract document info
      let docId = null;
      let docTitle = "(untitled)";
      let owner = null;

      event.parameters?.forEach((param) => {
        if (param.name === "doc_id" && param.value) {
          docId = param.value;
        }
        if (param.name === "doc_title" && param.value) {
          docTitle = param.value;
        }
        if (param.name === "owner" && param.value) {
          owner = param.value;
        }
      });

      if (!docId) return;

      // Categorize by event type
      if (eventName === "edit") {
        if (!editCounts[docId]) {
          editCounts[docId] = { title: docTitle, count: 0, owner: owner };
        }
        editCounts[docId].count++;
      }
      
      if (eventName === "change_user_access" || eventName === "change_acl_editors" || 
          eventName === "change_document_visibility" || eventName === "change_document_access_scope") {
        if (!shareCounts[docId]) {
          shareCounts[docId] = { title: docTitle, count: 0, owner: owner };
        }
        shareCounts[docId].count++;
      }
      
      if (eventName === "view") {
        if (!viewCounts[docId]) {
          viewCounts[docId] = { title: docTitle, count: 0, owner: owner };
        }
        viewCounts[docId].count++;
      }
    });
  });

  // Sort and get top 3 for each category
  const topEdited = Object.entries(editCounts)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 3)
    .map(([docId, data]) => ({ docId, ...data }));

  const topShared = Object.entries(shareCounts)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 3)
    .map(([docId, data]) => ({ docId, ...data }));

  const topViewed = Object.entries(viewCounts)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 3)
    .map(([docId, data]) => ({ docId, ...data }));

  return { topEdited, topShared, topViewed };
}

async function main() {
  try {
    const activities = await queryAllActivities();
    
    console.log(`${"=".repeat(70)}`);
    console.log(`ANALYZING TOP DOCUMENTS`);
    console.log(`${"=".repeat(70)}\n`);

    const { topEdited, topShared, topViewed } = analyzeTopDocuments(activities);

    console.log(`${"=".repeat(70)}`);
    console.log(`TOP 3 MOST EDITED DOCUMENTS`);
    console.log(`${"=".repeat(70)}`);
    if (topEdited.length === 0) {
      console.log("  No edit activities found in this period.");
    } else {
      topEdited.forEach((doc, index) => {
        const title = doc.title.length > 60 ? doc.title.substring(0, 57) + "..." : doc.title;
        console.log(`\n${index + 1}. ${title}`);
        console.log(`   Edit count: ${doc.count}`);
        console.log(`   Owner: ${doc.owner || "(unknown)"}`);
        console.log(`   Document ID: ${doc.docId}`);
      });
    }

    console.log(`\n${"=".repeat(70)}`);
    console.log(`TOP 3 MOST SHARED DOCUMENTS`);
    console.log(`${"=".repeat(70)}`);
    if (topShared.length === 0) {
      console.log("  No sharing activities found in this period.");
    } else {
      topShared.forEach((doc, index) => {
        const title = doc.title.length > 60 ? doc.title.substring(0, 57) + "..." : doc.title;
        console.log(`\n${index + 1}. ${title}`);
        console.log(`   Share/permission change count: ${doc.count}`);
        console.log(`   Owner: ${doc.owner || "(unknown)"}`);
        console.log(`   Document ID: ${doc.docId}`);
      });
    }

    console.log(`\n${"=".repeat(70)}`);
    console.log(`TOP 3 MOST VIEWED DOCUMENTS`);
    console.log(`${"=".repeat(70)}`);
    if (topViewed.length === 0) {
      console.log("  No view activities found in this period.");
    } else {
      topViewed.forEach((doc, index) => {
        const title = doc.title.length > 60 ? doc.title.substring(0, 57) + "..." : doc.title;
        console.log(`\n${index + 1}. ${title}`);
        console.log(`   View count: ${doc.count}`);
        console.log(`   Owner: ${doc.owner || "(unknown)"}`);
        console.log(`   Document ID: ${doc.docId}`);
      });
    }

    console.log(`\n${"=".repeat(70)}`);
    console.log(`✅ Analysis complete!`);
    console.log(`${"=".repeat(70)}\n`);

  } catch (error) {
    console.error("\n❌ Error:", error.message);
    if (error.response) {
      console.error("API Response:", JSON.stringify(error.response.data, null, 2));
    }
    process.exit(1);
  }
}

main();

