import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execSync } from "node:child_process";
/**
 * Call OmniFocus via its JavaScript‐for‐Automation plugin.
 * All debug output goes to **stderr** so stdout stays JSON-only.
 */
export async function callOmniFocus(params) {
    const payload = JSON.stringify({
        method: params.command,
        params: params.args ?? {},
    });
    const tmpJson = path.join(os.tmpdir(), `omnifocus-${Date.now()}.json`);
    const tmpApple = path.join(os.tmpdir(), `omnifocus-${Date.now()}.applescript`);
    fs.writeFileSync(tmpJson, payload, "utf8");
    // Build a tiny AppleScript wrapper that pipes the JSON into the plugin.
    const script = `
set jsonPath to POSIX path of "${tmpJson}"
set jsonData to read POSIX file jsonPath as «class utf8»
set js to "const p = PlugIn.find(\\\"omnifocus-mcp\\\");\
 if(!p) throw new Error('Plugin not found');\
 const lib = p.library(\\\"omnifocus-mcp\\\");\
 JSON.stringify(lib.request(" & quoted form of jsonData & "))"

tell application "OmniFocus"
  set _res to evaluate javascript js
end tell
return _res
`;
    fs.writeFileSync(tmpApple, script, "utf8");
    try {
        const raw = execSync(`osascript "${tmpApple}"`, { encoding: "utf8" });
        return JSON.parse(raw);
    }
    catch (err) {
        console.error("🟥 OmniFocus call failed:", err); // STDERR
        return { error: "Bridge call failed", details: String(err) };
    }
    finally {
        fs.rmSync(tmpJson, { force: true });
        fs.rmSync(tmpApple, { force: true });
    }
}
// ===== FOLDER OPERATION FUNCTIONS (Task 4-1) =====
/**
 * Create a new folder in OmniFocus
 */
export async function createFolder(params) {
    // Client-side validation
    if (!params.name || typeof params.name !== 'string' || params.name.trim() === '') {
        throw new Error("Folder name is required and must be a non-empty string");
    }
    if (params.position !== undefined && (!Number.isInteger(params.position) || params.position < 0)) {
        throw new Error("Position must be a non-negative integer");
    }
    const result = await callOmniFocus({
        command: "createFolder",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
/**
 * Validate a folder name before creation
 */
export async function validateFolderName(params) {
    const result = await callOmniFocus({
        command: "validateFolderName",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
/**
 * Get folder information by ID
 */
export async function getFolderById(params) {
    if (!params.folderId || typeof params.folderId !== 'string') {
        throw new Error("folderId is required and must be a string");
    }
    const result = await callOmniFocus({
        command: "getFolderById",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
/**
 * List folders with optional filtering
 */
export async function listFolders(params = {}) {
    const result = await callOmniFocus({
        command: "listFolders",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
// ===== PROJECT MOVEMENT FUNCTIONS (Task 4-2) =====
/**
 * Move a project to a different folder
 */
export async function moveProject(params) {
    // Client-side validation
    if (!params.projectId || typeof params.projectId !== 'string') {
        throw new Error("projectId is required and must be a string");
    }
    if (params.position !== undefined && (!Number.isInteger(params.position) || params.position < 0)) {
        throw new Error("Position must be a non-negative integer");
    }
    const result = await callOmniFocus({
        command: "moveProject",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
/**
 * Validate a project move before execution
 */
export async function validateProjectMove(params) {
    if (!params.projectId || typeof params.projectId !== 'string') {
        throw new Error("projectId is required and must be a string");
    }
    const result = await callOmniFocus({
        command: "validateProjectMove",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
/**
 * Get project information by ID
 */
export async function getProjectById(params) {
    if (!params.projectId || typeof params.projectId !== 'string') {
        throw new Error("projectId is required and must be a string");
    }
    const result = await callOmniFocus({
        command: "getProjectById",
        args: params
    });
    if (result.error) {
        throw new Error(result.error);
    }
    return result.result;
}
