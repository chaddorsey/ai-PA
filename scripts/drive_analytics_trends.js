#!/usr/bin/env node
/**
 * Trend Analysis for Google Drive Activity
 * Detects notable upticks and downticks in:
 * - Overall activity by type
 * - Activity on specific documents
 * - Activity by specific users
 */

const { google } = require("googleapis");
const { OAuth2Client } = require("google-auth-library");
const fs = require("fs");
const path = require("path");
const os = require("os");

// Configuration
const KEY_FILE = path.join(__dirname, "../gmail-mcp/gcp-oauth.admin-reports.desktop.json");
const TOKEN_PATH = path.join(os.homedir(), ".gmail-mcp", "admin-reports.credentials.json");

// Thresholds for "notable" changes
const MIN_ABSOLUTE_CHANGE = 10; // Minimum absolute change to be considered
const MIN_PERCENTAGE_CHANGE = 25; // Minimum percentage change (25%)
const MIN_BASE_ACTIVITY = 5; // Minimum activity in baseline period to avoid noise

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

async function queryActivities(startTime, endTime) {
  const oauth2Client = await loadCredentials();
  
  const token = await oauth2Client.getAccessToken();
  if (!token.token) {
    throw new Error("No valid access token. Please authenticate first.");
  }

  const admin = google.admin({ version: "reports_v1", auth: oauth2Client });

  const params = {
    userKey: "all",
    applicationName: "drive",
    startTime: startTime,
    endTime: endTime,
    maxResults: 1000,
  };

  let allActivities = [];
  let nextPageToken = null;

  do {
    if (nextPageToken) {
      params.pageToken = nextPageToken;
    }

    const response = await admin.activities.list(params);
    const activities = response.data.items || [];
    allActivities = allActivities.concat(activities);

    nextPageToken = response.data.nextPageToken;
    
    if (nextPageToken) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  } while (nextPageToken);

  return allActivities;
}

function analyzeActivityByType(activities) {
  const activityTypes = {};
  
  activities.forEach((activity) => {
    activity.events?.forEach((event) => {
      const eventName = event.name || "unknown";
      activityTypes[eventName] = (activityTypes[eventName] || 0) + 1;
    });
  });

  return activityTypes;
}

function analyzeActivityByDocument(activities) {
  const docActivity = {};
  
  activities.forEach((activity) => {
    activity.events?.forEach((event) => {
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

      if (docId) {
        if (!docActivity[docId]) {
          docActivity[docId] = {
            title: docTitle,
            owner: owner,
            count: 0,
            types: {}
          };
        }
        docActivity[docId].count++;
        const eventName = event.name || "unknown";
        docActivity[docId].types[eventName] = (docActivity[docId].types[eventName] || 0) + 1;
      }
    });
  });

  return docActivity;
}

function analyzeActivityByUser(activities) {
  const userActivity = {};
  
  activities.forEach((activity) => {
    const actorEmail = activity.actor?.email || "(unknown)";
    
    if (!userActivity[actorEmail]) {
      userActivity[actorEmail] = {
        count: 0,
        types: {},
        documents: new Set()
      };
    }
    
    userActivity[actorEmail].count++;
    
    activity.events?.forEach((event) => {
      const eventName = event.name || "unknown";
      userActivity[actorEmail].types[eventName] = (userActivity[actorEmail].types[eventName] || 0) + 1;
      
      // Track unique documents
      event.parameters?.forEach((param) => {
        if (param.name === "doc_id" && param.value) {
          userActivity[actorEmail].documents.add(param.value);
        }
      });
    });
  });

  // Convert Sets to counts
  Object.keys(userActivity).forEach(email => {
    userActivity[email].documentCount = userActivity[email].documents.size;
    delete userActivity[email].documents;
  });

  return userActivity;
}

function calculateChange(baseline, current) {
  const absoluteChange = current - baseline;
  const percentageChange = baseline > 0 ? ((absoluteChange / baseline) * 100) : (current > 0 ? Infinity : 0);
  
  return {
    absolute: absoluteChange,
    percentage: percentageChange,
    baseline,
    current
  };
}

function isNotableChange(change) {
  if (change.baseline < MIN_BASE_ACTIVITY && change.current < MIN_BASE_ACTIVITY) {
    return false; // Too low activity to be meaningful
  }
  
  const absChange = Math.abs(change.absolute);
  const pctChange = Math.abs(change.percentage);
  
  return absChange >= MIN_ABSOLUTE_CHANGE && pctChange >= MIN_PERCENTAGE_CHANGE;
}

function findTrends(baselineData, currentData, dataType) {
  const trends = {
    upticks: [],
    downticks: []
  };

  // Get all keys from both periods
  const allKeys = new Set([
    ...Object.keys(baselineData),
    ...Object.keys(currentData)
  ]);

  allKeys.forEach(key => {
    const baseline = baselineData[key] || 0;
    const current = currentData[key] || 0;
    const change = calculateChange(baseline, current);

    if (isNotableChange(change)) {
      const trend = {
        key,
        ...change,
        data: currentData[key] || {}
      };

      if (change.absolute > 0) {
        trends.upticks.push(trend);
      } else {
        trends.downticks.push(trend);
      }
    }
  });

  // Sort by absolute change magnitude
  trends.upticks.sort((a, b) => Math.abs(b.absolute) - Math.abs(a.absolute));
  trends.downticks.sort((a, b) => Math.abs(b.absolute) - Math.abs(a.absolute));

  return trends;
}

function formatPercentage(value) {
  if (value === Infinity) return "∞";
  if (value === -Infinity) return "-∞";
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

async function main() {
  try {
    // Parse command line arguments for date ranges
    const args = process.argv.slice(2);
    let baselineStart, baselineEnd, currentStart, currentEnd;

    if (args.length === 4) {
      // Custom date ranges: baselineStart baselineEnd currentStart currentEnd
      baselineStart = args[0];
      baselineEnd = args[1];
      currentStart = args[2];
      currentEnd = args[3];
    } else {
      // Default: Compare last 3 days vs previous 3 days
      const now = new Date();
      const threeDaysAgo = new Date(now);
      threeDaysAgo.setDate(now.getDate() - 3);
      const sixDaysAgo = new Date(threeDaysAgo);
      sixDaysAgo.setDate(threeDaysAgo.getDate() - 3);

      currentEnd = now.toISOString();
      currentStart = threeDaysAgo.toISOString();
      baselineEnd = threeDaysAgo.toISOString();
      baselineStart = sixDaysAgo.toISOString();
    }

    console.log(`${"=".repeat(70)}`);
    console.log(`DRIVE ACTIVITY TREND ANALYSIS`);
    console.log(`${"=".repeat(70)}`);
    console.log(`\nBaseline Period: ${baselineStart} to ${baselineEnd}`);
    console.log(`Current Period:  ${currentStart} to ${currentEnd}`);
    console.log(`\nThresholds: ${MIN_PERCENTAGE_CHANGE}% change, ${MIN_ABSOLUTE_CHANGE} min absolute change`);
    console.log(`${"=".repeat(70)}\n`);

    // Query both periods
    console.log("Querying baseline period...");
    const baselineActivities = await queryActivities(baselineStart, baselineEnd);
    console.log(`  Retrieved ${baselineActivities.length} activities\n`);

    console.log("Querying current period...");
    const currentActivities = await queryActivities(currentStart, currentEnd);
    console.log(`  Retrieved ${currentActivities.length} activities\n`);

    // Analyze by type
    console.log("Analyzing activity by type...");
    const baselineByType = analyzeActivityByType(baselineActivities);
    const currentByType = analyzeActivityByType(currentActivities);
    const typeTrends = findTrends(baselineByType, currentByType, "type");

    // Analyze by document
    console.log("Analyzing activity by document...");
    const baselineByDoc = analyzeActivityByDocument(baselineActivities);
    const currentByDoc = analyzeActivityByDocument(currentActivities);
    
    // Convert document objects to counts for comparison
    const baselineDocCounts = {};
    const currentDocCounts = {};
    Object.keys(baselineByDoc).forEach(docId => {
      baselineDocCounts[docId] = baselineByDoc[docId].count;
    });
    Object.keys(currentByDoc).forEach(docId => {
      currentDocCounts[docId] = currentByDoc[docId].count;
    });
    const docTrends = findTrends(baselineDocCounts, currentDocCounts, "document");

    // Add document metadata to trends
    docTrends.upticks.forEach(trend => {
      trend.title = currentByDoc[trend.key]?.title || baselineByDoc[trend.key]?.title || "(untitled)";
      trend.owner = currentByDoc[trend.key]?.owner || baselineByDoc[trend.key]?.owner || "(unknown)";
    });
    docTrends.downticks.forEach(trend => {
      trend.title = currentByDoc[trend.key]?.title || baselineByDoc[trend.key]?.title || "(untitled)";
      trend.owner = currentByDoc[trend.key]?.owner || baselineByDoc[trend.key]?.owner || "(unknown)";
    });

    // Analyze by user
    console.log("Analyzing activity by user...");
    const baselineByUser = analyzeActivityByUser(baselineActivities);
    const currentByUser = analyzeActivityByUser(currentActivities);
    
    // Convert user objects to counts for comparison
    const baselineUserCounts = {};
    const currentUserCounts = {};
    Object.keys(baselineByUser).forEach(email => {
      baselineUserCounts[email] = baselineByUser[email].count;
    });
    Object.keys(currentByUser).forEach(email => {
      currentUserCounts[email] = currentByUser[email].count;
    });
    const userTrends = findTrends(baselineUserCounts, currentUserCounts, "user");

    // Report results
    console.log(`${"=".repeat(70)}`);
    console.log(`TREND ANALYSIS RESULTS`);
    console.log(`${"=".repeat(70)}\n`);

    // Activity Type Trends
    console.log(`📊 ACTIVITY TYPE TRENDS\n`);
    if (typeTrends.upticks.length === 0 && typeTrends.downticks.length === 0) {
      console.log("  No notable changes in activity types.\n");
    } else {
      if (typeTrends.upticks.length > 0) {
        console.log("  ⬆️  UPTICKS:");
        typeTrends.upticks.slice(0, 10).forEach(trend => {
          console.log(`     ${trend.key.padEnd(30)} ${trend.baseline} → ${trend.current} (${formatPercentage(trend.percentage)})`);
        });
        console.log();
      }
      if (typeTrends.downticks.length > 0) {
        console.log("  ⬇️  DOWNTICKS:");
        typeTrends.downticks.slice(0, 10).forEach(trend => {
          console.log(`     ${trend.key.padEnd(30)} ${trend.baseline} → ${trend.current} (${formatPercentage(trend.percentage)})`);
        });
        console.log();
      }
    }

    // Document Trends
    console.log(`📄 DOCUMENT ACTIVITY TRENDS\n`);
    if (docTrends.upticks.length === 0 && docTrends.downticks.length === 0) {
      console.log("  No notable changes in document activity.\n");
    } else {
      if (docTrends.upticks.length > 0) {
        console.log("  ⬆️  UPTICKS (Top 10):");
        docTrends.upticks.slice(0, 10).forEach((trend, idx) => {
          const title = trend.title.length > 45 ? trend.title.substring(0, 42) + "..." : trend.title;
          console.log(`     ${(idx + 1).toString().padStart(2)}. ${title}`);
          console.log(`        ${trend.baseline} → ${trend.current} activities (${formatPercentage(trend.percentage)})`);
          console.log(`        Owner: ${trend.owner || "(unknown)"}`);
        });
        console.log();
      }
      if (docTrends.downticks.length > 0) {
        console.log("  ⬇️  DOWNTICKS (Top 10):");
        docTrends.downticks.slice(0, 10).forEach((trend, idx) => {
          const title = trend.title.length > 45 ? trend.title.substring(0, 42) + "..." : trend.title;
          console.log(`     ${(idx + 1).toString().padStart(2)}. ${title}`);
          console.log(`        ${trend.baseline} → ${trend.current} activities (${formatPercentage(trend.percentage)})`);
          console.log(`        Owner: ${trend.owner || "(unknown)"}`);
        });
        console.log();
      }
    }

    // User Trends
    console.log(`👥 USER ACTIVITY TRENDS\n`);
    if (userTrends.upticks.length === 0 && userTrends.downticks.length === 0) {
      console.log("  No notable changes in user activity.\n");
    } else {
      if (userTrends.upticks.length > 0) {
        console.log("  ⬆️  UPTICKS (Top 10):");
        userTrends.upticks.slice(0, 10).forEach((trend, idx) => {
          console.log(`     ${(idx + 1).toString().padStart(2)}. ${trend.key.padEnd(40)} ${trend.baseline} → ${trend.current} activities (${formatPercentage(trend.percentage)})`);
        });
        console.log();
      }
      if (userTrends.downticks.length > 0) {
        console.log("  ⬇️  DOWNTICKS (Top 10):");
        userTrends.downticks.slice(0, 10).forEach((trend, idx) => {
          console.log(`     ${(idx + 1).toString().padStart(2)}. ${trend.key.padEnd(40)} ${trend.baseline} → ${trend.current} activities (${formatPercentage(trend.percentage)})`);
        });
        console.log();
      }
    }

    // Summary statistics
    console.log(`${"=".repeat(70)}`);
    console.log(`SUMMARY STATISTICS`);
    console.log(`${"=".repeat(70)}`);
    console.log(`Total baseline activities: ${baselineActivities.length}`);
    console.log(`Total current activities:  ${currentActivities.length}`);
    const overallChange = calculateChange(baselineActivities.length, currentActivities.length);
    console.log(`Overall change: ${formatPercentage(overallChange.percentage)} (${overallChange.absolute} activities)`);
    console.log(`\nNotable trends detected:`);
    console.log(`  Activity types: ${typeTrends.upticks.length} upticks, ${typeTrends.downticks.length} downticks`);
    console.log(`  Documents: ${docTrends.upticks.length} upticks, ${docTrends.downticks.length} downticks`);
    console.log(`  Users: ${userTrends.upticks.length} upticks, ${userTrends.downticks.length} downticks`);
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

