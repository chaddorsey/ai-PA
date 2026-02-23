import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execSync } from "node:child_process";

// ===== FOLDER OPERATION INTERFACES (Task 4-1) =====

/**
 * Parameters for creating a new folder
 */
export interface CreateFolderParams {
  name: string;
  parentFolderId?: string;
  position?: number;
}

/**
 * Parameters for validating a folder name
 */
export interface ValidateFolderNameParams {
  name: string;
  parentFolderId?: string;
}

/**
 * Parameters for getting a folder by ID
 */
export interface GetFolderByIdParams {
  folderId: string;
}

/**
 * Parameters for listing folders
 */
export interface ListFoldersParams {
  includeDropped?: boolean;
  parentFolderId?: string;
}

/**
 * Response from folder creation
 */
export interface CreateFolderResponse {
  folderId: string;
  folderName: string;
  parentFolderId: string | null;
  active: boolean;
  created: boolean;
}

/**
 * Response from folder validation
 */
export interface ValidateFolderNameResponse {
  valid: boolean;
  error?: string;
  trimmedName?: string;
}

/**
 * Folder information response
 */
export interface FolderInfo {
  folderId: string;
  folderName: string;
  parentFolderId: string | null;
  active: boolean;
  status: string;
  subfolderCount: number;
  projectCount: number;
  totalSubfoldersCount?: number;
  totalProjectsCount?: number;
  added: string | null;
  modified: string | null;
}

// ===== PROJECT MOVEMENT INTERFACES (Task 4-2) =====

/**
 * Parameters for moving a project between folders
 */
export interface MoveProjectParams {
  projectId: string;
  targetFolderId?: string; // null/undefined for library root
  position?: number;
}

/**
 * Parameters for validating a project move
 */
export interface ValidateProjectMoveParams {
  projectId: string;
  targetFolderId?: string;
}

/**
 * Parameters for getting a project by ID
 */
export interface GetProjectByIdParams {
  projectId: string;
}

export interface TimestampedEntity {
  added: string | null;
  modified: string | null;
}

/**
 * Response from project movement
 */
export interface MoveProjectResponse {
  projectId: string;
  projectName: string;
  originalFolderId: string | null;
  newFolderId: string | null;
  moved: boolean;
  taskCount: number;
  added: string | null;
  modified: string | null;
}

/**
 * Response from project move validation
 */
export interface ValidateProjectMoveResponse {
  valid: boolean;
  error?: string;
  projectName?: string;
  currentFolderId?: string | null;
  targetFolderId?: string | null;
}

/**
 * Project information response
 */
export interface ProjectInfo {
  projectId: string;
  projectName: string;
  folderId: string | null;
  folderName: string | null;
  status: string;
  completed: boolean;
  active: boolean;
  sequential: boolean;
  completedByChildren: boolean;
  taskCount: number;
  activeTaskCount: number;
  completedTaskCount: number;
  dueDate: string | null;
  deferDate: string | null;
  flagged: boolean;
  note: string;
  added: string | null;
  modified: string | null;
}

export interface PlannedDates {
  plannedDate: string | null;
  effectivePlannedDate: string | null;
}

export interface TaskInfo extends PlannedDates, TimestampedEntity {
  taskId: string;
  taskName: string;
  note: string;
  flagged: boolean;
  deferDate: string | null;
  dueDate: string | null;
  duration: number | null;
  projectId: string | null;
  folderId: string | null;
  contexts: string[];
  completed: boolean;
  dropped: boolean;
}

/**
 * Call OmniFocus via its JavaScript‐for‐Automation plugin.
 * All debug output goes to **stderr** so stdout stays JSON-only.
 * 
 * If HOST_BRIDGE_URL is set, uses HTTP service on host instead of direct osascript.
 */
export async function callOmniFocus(params: { command: string; args?: any }) {
  // Check if we should use host bridge service (for Docker)
  const hostBridgeUrl = process.env.HOST_BRIDGE_URL;
  if (hostBridgeUrl) {
    try {
      // Node.js 18+ has built-in fetch
      const response = await fetch(`${hostBridgeUrl}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: params.command, args: params.args }),
      });
      const data = await response.json();
      if (data.success) {
        return data.result;
      } else {
        console.error("🟥 Host bridge call failed:", data.error, data.details);
        return { error: "Bridge call failed", details: data.details || data.error };
      }
    } catch (err: any) {
      console.error("🟥 Host bridge HTTP error:", err);
      return { error: "Bridge HTTP call failed", details: String(err) };
    }
  }

  // Direct osascript execution (for host-side execution)
  const payload = JSON.stringify({
    method: params.command,
    params: params.args ?? {},
  });

  // Base64-encode to avoid escaping issues with quoted form.
  // See host-bridge-service.js for full explanation.
  const b64 = Buffer.from(payload).toString("base64");
  const tmpApple = path.join(os.tmpdir(), `omnifocus-${Date.now()}.applescript`);

  const script = `
tell application "OmniFocus"
  set _res to evaluate javascript "var C='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',s='${b64}',r='';for(var i=0;i<s.length;){var a=C.indexOf(s[i++]),b=C.indexOf(s[i++]),c=C.indexOf(s[i++]),d=C.indexOf(s[i++]);r+=String.fromCharCode((a<<2)|(b>>4));if(c>=0)r+=String.fromCharCode(((b&15)<<4)|(c>>2));if(d>=0)r+=String.fromCharCode(((c&3)<<6)|d)}var p=PlugIn.find('omnifocus-mcp');if(!p)throw new Error('Plugin not found');var lib=p.library('omnifocus-mcp');JSON.stringify(lib.request(r))"
end tell
return _res
`;
  fs.writeFileSync(tmpApple, script, "utf8");

  try {
    const raw = execSync(`/usr/bin/osascript "${tmpApple}"`, { encoding: "utf8" });
    return JSON.parse(raw);
  } catch (err: any) {
    console.error("🟥 OmniFocus call failed:", err);       // STDERR
    return { error: "Bridge call failed", details: String(err) };
  } finally {
    fs.rmSync(tmpApple, { force: true });
  }
}

// ===== FOLDER OPERATION FUNCTIONS (Task 4-1) =====

/**
 * Create a new folder in OmniFocus
 */
export async function createFolder(params: CreateFolderParams): Promise<CreateFolderResponse> {
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

  return result.result as CreateFolderResponse;
}

/**
 * Validate a folder name before creation
 */
export async function validateFolderName(params: ValidateFolderNameParams): Promise<ValidateFolderNameResponse> {
  const result = await callOmniFocus({
    command: "validateFolderName",
    args: params
  });

  if (result.error) {
    throw new Error(result.error);
  }

  return result.result as ValidateFolderNameResponse;
}

/**
 * Get folder information by ID
 */
export async function getFolderById(params: GetFolderByIdParams): Promise<FolderInfo | null> {
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

  return result.result as FolderInfo | null;
}

/**
 * List folders with optional filtering
 */
export async function listFolders(params: ListFoldersParams = {}): Promise<FolderInfo[]> {
  const result = await callOmniFocus({
    command: "listFolders",
    args: params
  });

  if (result.error) {
    throw new Error(result.error);
  }

  return result.result as FolderInfo[];
}

// ===== PROJECT MOVEMENT FUNCTIONS (Task 4-2) =====

/**
 * Move a project to a different folder
 */
export async function moveProject(params: MoveProjectParams): Promise<MoveProjectResponse> {
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

  return result.result as MoveProjectResponse;
}

/**
 * Validate a project move before execution
 */
export async function validateProjectMove(params: ValidateProjectMoveParams): Promise<ValidateProjectMoveResponse> {
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

  return result.result as ValidateProjectMoveResponse;
}

/**
 * Get project information by ID
 */
export async function getProjectById(params: GetProjectByIdParams): Promise<ProjectInfo | null> {
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

  return result.result as ProjectInfo | null;
}
