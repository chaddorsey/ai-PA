import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { callOmniFocus } from "./bridge.js";
import * as bplist from "bplist-parser";
const server = new McpServer({
    name: "omnifocus",
    version: "1.0.0",
});
function asJsonText(body) {
    return {
        content: [
            { type: "text", text: JSON.stringify(body, null, 2) }
        ],
    };
}
server.tool("listRemaining", "Return all of your incomplete OmniFocus tasks", {}, async () => {
    const tasks = await callOmniFocus({ command: "listRemaining" });
    return asJsonText(tasks);
});
server.tool("getTask", "Fetch details for one task", { taskId: z.string().describe("The task’s UUID") }, async ({ taskId }) => {
    const task = await callOmniFocus({ command: "getTask", args: { taskId } });
    return asJsonText(task);
});
server.tool("listProjects", "Return all your OmniFocus projects", {}, async () => {
    const list = await callOmniFocus({ command: "listProjects" });
    return asJsonText(list);
});
server.tool("listTags", "Return all your OmniFocus tags", {}, async () => {
    const list = await callOmniFocus({ command: "listTags" });
    return asJsonText(list);
});
server.tool("listTasksByProject", "Return all tasks inside a specific OmniFocus project (including nested tasks)", { projectId: z.string().describe("The project’s UUID") }, async ({ projectId }) => {
    const tasks = await callOmniFocus({
        command: "listTasksByProject",
        args: { projectId }
    });
    return asJsonText(tasks);
});
server.tool("listTasksByTag", "Return all tasks with a specific OmniFocus tag (context)", {
    tagId: z.string().describe("The tag's UUID"),
    active: z.boolean().optional().describe("Filter for active tasks (true=only active, false=only dropped/inactive)"),
    includeCompleted: z.boolean().optional().describe("Include completed tasks (default: false)"),
    projectId: z.string().optional().describe("Scope to specific project UUID")
}, async (args) => {
    const tasks = await callOmniFocus({
        command: "listTasksByTag",
        args
    });
    return asJsonText(tasks);
});
server.tool("listInbox", "Return all tasks currently in the OmniFocus inbox for processing", {
    includeCompleted: z.boolean().optional().describe("Include completed inbox items (default: false)"),
    limit: z.number().int().positive().optional().describe("Maximum number of inbox items to return for performance")
}, async (args) => {
    const inboxItems = await callOmniFocus({
        command: "listInbox",
        args
    });
    return asJsonText(inboxItems);
});
server.tool("processInboxItem", "Process an inbox item by performing multiple operations in a single call (assign project, add tags, set dates, rename, add notes, flag, set duration, or delete). ALREADY ATOMIC - no need to wrap in transaction. Use directly for inbox processing.", {
    taskId: z.string().describe("The inbox task's UUID"),
    projectId: z.string().optional().describe("Project UUID to assign task to (moves task out of inbox)"),
    tagIds: z.array(z.string()).optional().describe("Tag UUIDs to add to the task"),
    name: z.string().optional().describe("New task title/name"),
    note: z.string().optional().describe("Task note content"),
    flagged: z.boolean().optional().describe("Whether to flag the task"),
    deferDate: z.string().optional().describe("ISO defer date"),
    dueDate: z.string().optional().describe("ISO due date"),
    estimatedMinutes: z.number().positive().max(1440).optional().describe("Estimated duration in minutes (1-1440)"),
    deleteTask: z.boolean().optional().describe("Delete the task completely (mutually exclusive with other operations)")
}, async (args) => {
    const result = await callOmniFocus({
        command: "processInboxItem",
        args
    });
    return asJsonText(result);
});
server.tool("getInboxProcessingContext", "Get comprehensive context for intelligent bulk inbox processing including pre-analyzed items, user patterns, suggestions, and available destinations. Use this BEFORE bulk processing to gather all intelligence the AI needs to make smart decisions efficiently.", {
    max_items: z.number().int().positive().max(25).optional().describe("Maximum number of inbox items to analyze (default: 15, max: 25 for performance)"),
    include_examples: z.boolean().optional().describe("Include historical processing examples for learning (default: true)"),
    include_user_patterns: z.boolean().optional().describe("Include user behavior patterns and preferences (default: true)"),
    pre_analyze_content: z.boolean().optional().describe("Pre-analyze content for dates, projects, tags suggestions (default: true)"),
    default_project_id: z.string().optional().describe("UUID of default project for inbox processing. Defaults to Today project (bdRrScFC2eT). Most tasks will be suggested to move here unless content clearly indicates another project.")
}, async (args) => {
    const context = await callOmniFocus({
        command: "getInboxProcessingContext",
        args
    });
    return asJsonText(context);
});
server.tool("executeBulkInboxProcessing", "Execute multiple inbox operations in a single efficient batch with comprehensive error handling, validation, and undo capabilities. Supports processing, merging, holding, and deleting multiple items with atomic transaction support.", {
    item_operations: z.array(z.object({
        item_id: z.string().describe("Task UUID from inbox"),
        action: z.enum(["process", "process_with_subtasks", "merge", "hold", "delete"]).describe("Operation type to perform"),
        // Process action parameters
        target_project: z.string().optional().describe("Project UUID to assign task to (for process action)"),
        target_tags: z.array(z.string()).optional().describe("Tag UUIDs to add (for process action)"),
        new_name: z.string().optional().describe("New task name (for process action)"),
        note_additions: z.string().optional().describe("Content to append to task notes (for process action)"),
        due_date: z.string().optional().describe("ISO due date (for process action)"),
        defer_date: z.string().optional().describe("ISO defer date (for process action)"),
        flagged: z.boolean().optional().describe("Flag status (for process action)"),
        estimated_minutes: z.number().positive().max(1440).optional().describe("Duration in minutes (for process action)"),
        // Merge action parameters
        merge_target: z.string().optional().describe("Target task UUID to merge into (for merge action)"),
        merge_type: z.enum(["note_append", "url_reference"]).optional().describe("How to merge content (default: note_append)"),
        // Process with subtasks action parameters
        parent_task_name: z.string().optional().describe("New name for the parent task (for process_with_subtasks action)"),
        subtasks: z.array(z.object({
            name: z.string().describe("Subtask name"),
            tags: z.array(z.string()).optional().describe("Tag UUIDs for subtask"),
            due_date: z.string().optional().describe("ISO due date for subtask"),
            defer_date: z.string().optional().describe("ISO defer date for subtask"),
            note: z.string().optional().describe("Note content for subtask"),
            flagged: z.boolean().optional().describe("Flag status for subtask"),
            estimated_minutes: z.number().positive().max(1440).optional().describe("Duration in minutes for subtask")
        })).optional().describe("Array of subtasks to create under the parent task (for process_with_subtasks action, max 15 subtasks)")
    })).min(1).max(100).describe("Array of operations to execute (1-100 operations)"),
    execution_options: z.object({
        validate_before_execute: z.boolean().optional().describe("Validate all operations before execution (default: true)"),
        create_undo_checkpoint: z.boolean().optional().describe("Create transaction for undo capability (default: true)"),
        batch_size: z.number().int().positive().max(50).optional().describe("Operations per batch (default: 20, max: 50)"),
        continue_on_errors: z.boolean().optional().describe("Continue processing if individual operations fail (default: true)")
    }).optional().describe("Execution configuration options")
}, async (args) => {
    const result = await callOmniFocus({
        command: "executeBulkInboxProcessing",
        args
    });
    return asJsonText(result);
});
server.tool("listPerspectives", "Return all OmniFocus perspectives (both built-in and custom) with metadata", {}, async () => {
    const perspectives = await callOmniFocus({ command: "listPerspectives" });
    return asJsonText(perspectives);
});
server.tool("switchToPerspective", "Switch OmniFocus to a specific perspective (by ID or name)", {
    perspectiveId: z.string().describe("The perspective ID or name to switch to")
}, async ({ perspectiveId }) => {
    const result = await callOmniFocus({ command: "switchToPerspective", args: { perspectiveId } });
    return asJsonText(result);
});
server.tool("listTasksByPerspective", "Get all tasks currently visible in a specific perspective (or current perspective if none specified)", {
    perspectiveId: z.string().optional().describe("The perspective ID or name to query (if not provided, uses current perspective)"),
    includeCompleted: z.boolean().optional().describe("Include completed tasks (default: false)"),
    limit: z.number().int().positive().optional().describe("Maximum number of tasks to return")
}, async (args) => {
    const result = await callOmniFocus({ command: "listTasksByPerspective", args });
    return asJsonText(result);
});
server.tool("getPerspective", "Get detailed information about a specific perspective including configuration details for custom perspectives with full binary plist parsing", {
    perspectiveId: z.string().describe("The perspective ID or name to retrieve details for")
}, async ({ perspectiveId }) => {
    const rawResult = await callOmniFocus({ command: "getPerspective", args: { perspectiveId } });
    // Parse the JSON string if needed
    let result;
    if (typeof rawResult === 'string') {
        try {
            result = JSON.parse(rawResult);
        }
        catch (parseError) {
            return asJsonText({
                error: "Failed to parse JSON result from OmniFocus",
                parseError: parseError.message,
                rawResult: rawResult.substring(0, 500) + '...'
            });
        }
    }
    else {
        result = rawResult;
    }
    // Ensure we have the expected result structure
    if (!result || !result.result) {
        return asJsonText({
            error: "No valid result structure after parsing",
            resultType: typeof result,
            resultKeys: result ? Object.keys(result) : [],
            originalResult: result
        });
    }
    // If we have binary plist data, parse it on the server side
    // Debug: Log the condition check
    const hasConfigFormat = result?.result?.configFormat === 'binary-plist';
    const hasBase64Data = !!result?.result?.configuration?.base64Data;
    // Add debug info to response
    if (!result.result.serverSideProcessing) {
        result.result.serverSideProcessing = {
            conditionCheck: {
                hasConfigFormat,
                hasBase64Data,
                configFormat: result?.result?.configFormat,
                hasConfiguration: !!result?.result?.configuration,
                willProcess: hasConfigFormat && hasBase64Data
            }
        };
    }
    if (hasConfigFormat && hasBase64Data) {
        try {
            // Add processing status
            result.result.serverSideProcessing.status = 'attempting-parse';
            // Decode the base64 data to binary
            const binaryData = Buffer.from(result.result.configuration.base64Data, 'base64');
            result.result.serverSideProcessing.binaryDataLength = binaryData.length;
            // Parse the binary plist
            const parsedPlist = bplist.parseBuffer(binaryData);
            result.result.serverSideProcessing.parseResult = {
                success: !!parsedPlist,
                arrayLength: parsedPlist ? parsedPlist.length : 0,
                hasFirstElement: !!(parsedPlist && parsedPlist[0])
            };
            if (parsedPlist && parsedPlist.length > 0) {
                const perspectiveConfig = parsedPlist[0]; // Binary plists usually have the main object as first element
                // Enhance the result with parsed configuration
                result.result.configuration.parsed = perspectiveConfig;
                result.result.configuration.parsingSuccess = true;
                // Parse filterRules if it's a JSON string
                let parsedFilterRules = perspectiveConfig.filterRules || [];
                if (typeof perspectiveConfig.filterRules === 'string') {
                    try {
                        parsedFilterRules = JSON.parse(perspectiveConfig.filterRules);
                    }
                    catch (parseError) {
                        parsedFilterRules = [];
                        result.result.configuration.filterRulesParseError = parseError.message;
                    }
                }
                // Extract detailed view configuration from viewState
                const viewState = perspectiveConfig.viewState || {};
                const extractedViewMode = viewState.viewMode || perspectiveConfig.viewMode || null;
                const viewModeState = viewState.viewModeState || {};
                // Extract view-specific settings
                let detailedViewSettings = {
                    viewMode: extractedViewMode,
                    sortOrder: perspectiveConfig.sortOrder || null,
                    groupBy: perspectiveConfig.groupBy || null,
                    useSavedColumns: perspectiveConfig.useSavedColumns || false,
                    useCustomOrderWhenUngrouped: perspectiveConfig.useCustomOrderWhenUngrouped || false,
                    useSavedFocus: perspectiveConfig.useSavedFocus || false,
                    useSavedExpansion: perspectiveConfig.useSavedExpansion || false
                };
                // Add view mode specific settings
                if (extractedViewMode && viewModeState[extractedViewMode]) {
                    detailedViewSettings.viewModeSpecific = {
                        mode: extractedViewMode,
                        settings: viewModeState[extractedViewMode]
                    };
                }
                // Extract column information if available
                if (perspectiveConfig.columns || perspectiveConfig.columnConfiguration) {
                    detailedViewSettings.columnConfiguration = perspectiveConfig.columns || perspectiveConfig.columnConfiguration;
                }
                // Extract and organize key configuration elements
                const organizedConfig = {
                    viewSettings: detailedViewSettings,
                    filterSettings: {
                        filterRules: parsedFilterRules,
                        topLevelFilterAggregation: perspectiveConfig.topLevelFilterAggregation || null,
                        sidebarFilter: perspectiveConfig.sidebarFilter || null
                    },
                    displaySettings: {
                        viewState: perspectiveConfig.viewState || {},
                        version: perspectiveConfig.version || null,
                        collation: perspectiveConfig.collation || viewState?.viewModeState?.[extractedViewMode]?.collation || null,
                        sidebarFilter: perspectiveConfig.sidebarFilter || viewState?.viewModeState?.[extractedViewMode]?.sidebarFilter || null,
                        // Extract any additional display preferences
                        additionalSettings: {
                            hasCustomLayout: !!(perspectiveConfig.layout || perspectiveConfig.layoutConfiguration),
                            hasCustomSorting: !!(perspectiveConfig.sortOrder || perspectiveConfig.sortConfiguration),
                            hasCustomGrouping: !!(perspectiveConfig.groupBy || perspectiveConfig.groupConfiguration),
                            hasViewModeState: !!viewModeState[extractedViewMode],
                            viewStateKeys: viewState ? Object.keys(viewState) : []
                        }
                    },
                    metadata: {
                        name: perspectiveConfig.name || result.result.name,
                        allKeys: Object.keys(perspectiveConfig)
                    },
                    enhancements: {
                        parsedFilterRules: Array.isArray(parsedFilterRules) && parsedFilterRules.length > 0,
                        extractedViewModeDetails: !!viewModeState[extractedViewMode],
                        foundColumnConfiguration: !!(perspectiveConfig.columns || perspectiveConfig.columnConfiguration),
                        enhancedDisplaySettings: true,
                        nextStepsNeeded: [
                            ...(parsedFilterRules.some((rule) => rule.actionWithinFocus || rule.actionHasAllOfTags || rule.actionHasAnyOfTags) ?
                                ['Resolve filter reference IDs to human-readable names'] : []),
                            ...(perspectiveConfig.useSavedColumns && !(perspectiveConfig.columns || perspectiveConfig.columnConfiguration) ?
                                ['Extract detailed column configuration'] : []),
                            ...(!perspectiveConfig.sortOrder ? ['Extract sort order configuration'] : []),
                            ...(!perspectiveConfig.groupBy ? ['Extract grouping configuration'] : [])
                        ]
                    }
                };
                result.result.configuration.organized = organizedConfig;
                // Extract specific filter details if available
                if (parsedFilterRules && Array.isArray(parsedFilterRules)) {
                    const filterDetails = parsedFilterRules.map((rule) => {
                        const ruleType = typeof rule === 'object' ? Object.keys(rule)[0] : 'unknown';
                        const ruleValue = rule;
                        // Create enhanced rule description
                        let description = 'Unknown filter rule';
                        if (typeof rule === 'object') {
                            const key = Object.keys(rule)[0];
                            const value = rule[key];
                            switch (key) {
                                case 'actionAvailability':
                                    description = `Tasks with availability: ${value}`;
                                    break;
                                case 'actionWithinFocus':
                                    description = `Tasks within focus (IDs: ${Array.isArray(value) ? value.join(', ') : value})`;
                                    break;
                                case 'actionHasAllOfTags':
                                    description = `Tasks with all tags (IDs: ${Array.isArray(value) ? value.join(', ') : value})`;
                                    break;
                                case 'actionHasAnyOfTags':
                                    description = `Tasks with any tags (IDs: ${Array.isArray(value) ? value.join(', ') : value})`;
                                    break;
                                case 'aggregateRules':
                                    // Handle complex aggregate rules with proper type interpretation
                                    if (Array.isArray(value) && rule.aggregateType) {
                                        const ruleDescriptions = value.map((subRule) => {
                                            const subKey = Object.keys(subRule)[0];
                                            const subValue = subRule[subKey];
                                            switch (subKey) {
                                                case 'actionHasAnyOfTags':
                                                    return rule.aggregateType === 'none'
                                                        ? `EXCLUDES tasks with any of these tags (IDs: ${Array.isArray(subValue) ? subValue.join(', ') : subValue})`
                                                        : `INCLUDES tasks with any of these tags (IDs: ${Array.isArray(subValue) ? subValue.join(', ') : subValue})`;
                                                case 'actionHasAllOfTags':
                                                    return rule.aggregateType === 'none'
                                                        ? `EXCLUDES tasks with all of these tags (IDs: ${Array.isArray(subValue) ? subValue.join(', ') : subValue})`
                                                        : `INCLUDES tasks with all of these tags (IDs: ${Array.isArray(subValue) ? subValue.join(', ') : subValue})`;
                                                default:
                                                    return `${subKey}: ${JSON.stringify(subValue)}`;
                                            }
                                        });
                                        description = `Aggregate filter (${rule.aggregateType}): ${ruleDescriptions.join(', ')}`;
                                    }
                                    else {
                                        description = `Aggregate rules: ${JSON.stringify(value)}`;
                                    }
                                    break;
                                default:
                                    description = `${key}: ${JSON.stringify(value)}`;
                            }
                        }
                        return {
                            type: ruleType,
                            value: ruleValue,
                            description: description,
                            readable: JSON.stringify(rule, null, 2),
                            needsResolution: ruleType === 'actionWithinFocus' || ruleType === 'actionHasAllOfTags' || ruleType === 'actionHasAnyOfTags' || ruleType === 'aggregateRules'
                        };
                    });
                    result.result.configuration.organized.filterSettings.filterDetails = filterDetails;
                }
            }
            else {
                result.result.configuration.parsingError = "No data found in parsed plist";
            }
        }
        catch (parseError) {
            result.result.configuration.parsingError = `Failed to parse binary plist: ${parseError.message}`;
            result.result.configuration.parsingSuccess = false;
            result.result.serverSideProcessing.error = {
                message: parseError.message,
                stack: parseError.stack,
                status: 'parse-failed'
            };
        }
    }
    else {
        // Add info about why processing didn't happen
        result.result.serverSideProcessing.status = 'skipped';
        result.result.serverSideProcessing.reason = !hasConfigFormat ? 'not-binary-plist' : 'no-base64-data';
    }
    return asJsonText(result);
});
server.tool("listFolders", "Return folders with optional filtering and hierarchy navigation", {
    parentFolderId: z.string().optional().describe("Parent folder UUID to list children from (root level if not provided)"),
    includeEmpty: z.boolean().optional().describe("Include folders with no projects or subfolders (default: true)"),
    maxDepth: z.number().int().positive().optional().describe("Maximum hierarchy depth to traverse")
}, async (args) => {
    const folders = await callOmniFocus({
        command: "listFolders",
        args
    });
    return asJsonText(folders);
});
server.tool("getFolderHierarchy", "Return complete folder hierarchy with optional project inclusion", {
    folderId: z.string().optional().describe("Folder UUID to start from (library root if not provided)"),
    includeProjects: z.boolean().optional().describe("Include projects in each folder (default: false)"),
    maxDepth: z.number().int().positive().optional().describe("Maximum hierarchy depth to traverse")
}, async (args) => {
    const hierarchy = await callOmniFocus({
        command: "getFolderHierarchy",
        args
    });
    return asJsonText(hierarchy);
});
server.tool("getProjectsByFolder", "Return all projects within a specific folder with filtering and sorting options", {
    folderId: z.string().describe("Folder UUID to get projects from"),
    includeSubfolders: z.boolean().optional().describe("Include projects from subfolders (default: false)"),
    includeCompleted: z.boolean().optional().describe("Include completed projects (default: false)"),
    sortBy: z.enum(['name', 'created', 'modified']).optional().describe("Sort projects by specified criteria (default: name)")
}, async (args) => {
    const projects = await callOmniFocus({
        command: "getProjectsByFolder",
        args
    });
    return asJsonText(projects);
});
server.tool("getProjectPath", "Return the complete folder path and context information for a specific project", {
    projectId: z.string().describe("Project UUID to get path information for")
}, async (args) => {
    const pathInfo = await callOmniFocus({
        command: "getProjectPath",
        args
    });
    return asJsonText(pathInfo);
});
server.tool("createTask", "Create a new OmniFocus task", {
    name: z.string().describe("Task title"),
    note: z.string().optional().describe("Optional note"),
    projectId: z.string().optional().describe("Optional project UUID"),
    tagIds: z.array(z.string()).optional().describe("Optional tag UUIDs"),
    deferDate: z.string().optional().describe("Optional ISO defer date"),
    dueDate: z.string().optional().describe("Optional ISO due date"),
    flagged: z.boolean().optional().describe("Optional flagged state"),
    estimatedMinutes: z.number().positive().max(1440).optional().describe("Estimated duration in minutes (1-1440)")
}, async (args) => {
    const task = await callOmniFocus({ command: "createTask", args });
    return asJsonText(task);
});
server.tool("updateTask", "Update fields on an existing OmniFocus task", {
    taskId: z.string().describe("The task’s UUID"),
    name: z.string().optional().describe("New title"),
    note: z.string().optional().describe("New note"),
    flagged: z.boolean().optional().describe("Flagged state"),
    completed: z.boolean().optional().describe("Completed state"),
    dropped: z.boolean().optional().describe("Dropped state (inactive tasks)"),
    deferDate: z.string().optional().describe("ISO defer date"),
    dueDate: z.string().optional().describe("ISO due date"),
    projectId: z.string().optional().describe("New project UUID"),
    tagIds: z.array(z.string()).optional().describe("New tag UUIDs"),
    estimatedMinutes: z.number().positive().max(1440).optional().describe("Estimated duration in minutes (1-1440)")
}, async (args) => {
    const result = await callOmniFocus({ command: "updateTask", args });
    return asJsonText(result);
});
server.tool("completeTask", "Mark an OmniFocus task as completed", { taskId: z.string().describe("The task’s UUID") }, async ({ taskId }) => {
    const result = await callOmniFocus({ command: "completeTask", args: { taskId } });
    return asJsonText(result);
});
server.tool("queryTasks", "Query OmniFocus tasks with advanced multi-dimensional filtering including exclusions and metadata-based filters", {
    dueBefore: z.string().optional().describe("ISO date string for due date upper bound (find tasks due before this date)"),
    dueAfter: z.string().optional().describe("ISO date string for due date lower bound (find tasks due after this date)"),
    deferBefore: z.string().optional().describe("ISO date string for defer date upper bound (find tasks deferred before this date)"),
    deferAfter: z.string().optional().describe("ISO date string for defer date lower bound (find tasks deferred after this date)"),
    minDuration: z.number().positive().optional().describe("Minimum estimated duration in minutes"),
    maxDuration: z.number().positive().optional().describe("Maximum estimated duration in minutes"),
    flagged: z.boolean().optional().describe("Filter for flagged tasks (true=only flagged, false=only unflagged)"),
    completed: z.boolean().optional().describe("Include completed tasks (true=only completed, false=only incomplete)"),
    blocked: z.boolean().optional().describe("Filter for blocked tasks (true=only blocked, false=only unblocked)"),
    active: z.boolean().optional().describe("Filter for active tasks (true=only active, false=only dropped/inactive)"),
    projectId: z.string().optional().describe("Scope query to specific project UUID"),
    tagId: z.string().optional().describe("Scope query to specific tag UUID"),
    tagCombination: z.object({
        and: z.array(z.string()).optional().describe("All of these tag UUIDs must be present"),
        or: z.array(z.string()).optional().describe("At least one of these tag UUIDs must be present"),
        any: z.array(z.string()).optional().describe("Legacy: equivalent to 'or' - at least one tag UUID must be present"),
        not: z.array(z.string()).optional().describe("None of these tag UUIDs can be present")
    }).optional().describe("Complex tag filtering with boolean logic (AND/OR/NOT operations)"),
    includeCompleted: z.boolean().optional().describe("Include completed tasks in results (default: false)"),
    excludeProjectIds: z.array(z.string()).optional().describe("Project UUIDs to exclude from results"),
    excludeTagIds: z.array(z.string()).optional().describe("Tag UUIDs to exclude - tasks with any of these tags will be filtered out"),
    excludeFolderIds: z.array(z.string()).optional().describe("Folder UUIDs to exclude - tasks in projects within these folders will be filtered out"),
    // Advanced metadata filters - Task 1-20
    hasEstimate: z.boolean().optional().describe("Filter for tasks with/without time estimates (true=has estimate, false=no estimate)"),
    minEstimate: z.number().positive().max(1440).optional().describe("Minimum time estimate in minutes (1-1440)"),
    maxEstimate: z.number().positive().max(1440).optional().describe("Maximum time estimate in minutes (1-1440)"),
    hasNotes: z.boolean().optional().describe("Filter for tasks with/without notes (true=has notes, false=no notes)"),
    hasDueDate: z.boolean().optional().describe("Filter for tasks with/without due dates (true=has due date, false=no due date)"),
    hasDeferDate: z.boolean().optional().describe("Filter for tasks with/without defer dates (true=has defer date, false=no defer date)"),
    isOverdue: z.boolean().optional().describe("Filter for overdue tasks (true=overdue only, false=not overdue)"),
    isDueToday: z.boolean().optional().describe("Filter for tasks due today (true=due today only, false=not due today)"),
    isDueSoon: z.number().positive().max(365).optional().describe("Filter for tasks due within N days (1-365 days)"),
    isAvailable: z.boolean().optional().describe("Filter for available tasks (true=available now, false=blocked/deferred)")
}, async (args) => {
    const tasks = await callOmniFocus({ command: "queryTasks", args });
    return asJsonText(tasks);
});
server.tool("deleteTask", "Permanently delete an OmniFocus task", {
    taskId: z.string().describe("The task's UUID"),
    force: z.boolean().optional().describe("Force deletion (currently unused, for future safety features)")
}, async ({ taskId, force }) => {
    const result = await callOmniFocus({ command: "deleteTask", args: { taskId, force } });
    return asJsonText(result);
});
server.tool("searchTasks", "Search tasks with full-text matching, exclusion filtering, date/duration/status filters, and advanced metadata filters. Returns scored results with match type information.", {
    query: z.string().describe("Search query to match against task names and notes"),
    scope: z.enum(['all', 'project', 'tag']).optional().describe("Search scope (default: all)"),
    projectId: z.string().optional().describe("Project UUID when scope is 'project'"),
    tagId: z.string().optional().describe("Tag UUID when scope is 'tag'"),
    tagCombination: z.object({
        and: z.array(z.string()).optional().describe("All of these tag UUIDs must be present"),
        or: z.array(z.string()).optional().describe("At least one of these tag UUIDs must be present"),
        any: z.array(z.string()).optional().describe("Legacy: equivalent to 'or' - at least one tag UUID must be present"),
        not: z.array(z.string()).optional().describe("None of these tag UUIDs can be present")
    }).optional().describe("Complex tag filtering with boolean logic (AND/OR/NOT operations)"),
    fuzzy: z.boolean().optional().describe("Enable fuzzy matching for typos (default: true)"),
    active: z.boolean().optional().describe("Filter for active tasks (true=only active, false=only dropped/inactive)"),
    includeCompleted: z.boolean().optional().describe("Include completed tasks (default: false)"),
    includeDropped: z.boolean().optional().describe("Include dropped/inactive tasks (default: false)"),
    maxResults: z.number().int().positive().optional().describe("Maximum number of results to return (default: 100)"),
    excludeProjectIds: z.array(z.string()).optional().describe("Project UUIDs to exclude from search results"),
    excludeTagIds: z.array(z.string()).optional().describe("Tag UUIDs to exclude - tasks with any of these tags will be filtered out"),
    excludeFolderIds: z.array(z.string()).optional().describe("Folder UUIDs to exclude - tasks in projects within these folders will be filtered out"),
    // Date range filters - Task 1-17
    dueBefore: z.string().optional().describe("ISO date string for due date upper bound (find tasks due before this date)"),
    dueAfter: z.string().optional().describe("ISO date string for due date lower bound (find tasks due after this date)"),
    deferBefore: z.string().optional().describe("ISO date string for defer date upper bound (find tasks deferred before this date)"),
    deferAfter: z.string().optional().describe("ISO date string for defer date lower bound (find tasks deferred after this date)"),
    // Duration filters - Task 1-17
    minDuration: z.number().positive().optional().describe("Minimum estimated duration in minutes"),
    maxDuration: z.number().positive().optional().describe("Maximum estimated duration in minutes"),
    // Status filters - Task 1-17
    flagged: z.boolean().optional().describe("Filter for flagged tasks (true=only flagged, false=only unflagged)"),
    completed: z.boolean().optional().describe("Include completed tasks (true=only completed, false=only incomplete)"),
    blocked: z.boolean().optional().describe("Filter for blocked tasks (true=only blocked, false=only unblocked)"),
    dropped: z.boolean().optional().describe("Filter for dropped tasks (true=only dropped, false=only active)"),
    // Advanced metadata filters - Task 1-20
    hasEstimate: z.boolean().optional().describe("Filter for tasks with/without time estimates (true=has estimate, false=no estimate)"),
    minEstimate: z.number().positive().max(1440).optional().describe("Minimum time estimate in minutes (1-1440)"),
    maxEstimate: z.number().positive().max(1440).optional().describe("Maximum time estimate in minutes (1-1440)"),
    hasNotes: z.boolean().optional().describe("Filter for tasks with/without notes (true=has notes, false=no notes)"),
    hasDueDate: z.boolean().optional().describe("Filter for tasks with/without due dates (true=has due date, false=no due date)"),
    hasDeferDate: z.boolean().optional().describe("Filter for tasks with/without defer dates (true=has defer date, false=no defer date)"),
    isOverdue: z.boolean().optional().describe("Filter for overdue tasks (true=overdue only, false=not overdue)"),
    isDueToday: z.boolean().optional().describe("Filter for tasks due today (true=due today only, false=not due today)"),
    isDueSoon: z.number().positive().max(365).optional().describe("Filter for tasks due within N days (1-365 days)"),
    isAvailable: z.boolean().optional().describe("Filter for available tasks (true=available now, false=blocked/deferred)")
}, async (args) => {
    const results = await callOmniFocus({ command: "searchTasks", args });
    return asJsonText(results);
});
server.tool("universalQuery", "Universal query interface combining search and structured filtering with intelligent optimization. Supports all searchTasks and queryTasks capabilities in a single optimized method.", {
    // Search parameters
    search: z.string().optional().describe("Optional search query to match against task names and notes - if provided, results include search scoring"),
    fuzzy: z.boolean().optional().describe("Enable fuzzy matching for search queries (default: true)"),
    // Scope and targeting parameters
    projectId: z.string().optional().describe("Scope query to specific project UUID"),
    tagId: z.string().optional().describe("Scope query to specific tag UUID"),
    tagCombination: z.object({
        and: z.array(z.string()).optional().describe("All of these tag UUIDs must be present"),
        or: z.array(z.string()).optional().describe("At least one of these tag UUIDs must be present"),
        any: z.array(z.string()).optional().describe("Legacy: equivalent to 'or' - at least one tag UUID must be present"),
        not: z.array(z.string()).optional().describe("None of these tag UUIDs can be present")
    }).optional().describe("Complex tag filtering with boolean logic (AND/OR/NOT operations)"),
    // Date range filters
    dueBefore: z.string().optional().describe("ISO date string for due date upper bound (find tasks due before this date)"),
    dueAfter: z.string().optional().describe("ISO date string for due date lower bound (find tasks due after this date)"),
    deferBefore: z.string().optional().describe("ISO date string for defer date upper bound (find tasks deferred before this date)"),
    deferAfter: z.string().optional().describe("ISO date string for defer date lower bound (find tasks deferred after this date)"),
    // Duration filters
    minDuration: z.number().positive().optional().describe("Minimum estimated duration in minutes"),
    maxDuration: z.number().positive().optional().describe("Maximum estimated duration in minutes"),
    // Status filters
    flagged: z.boolean().optional().describe("Filter for flagged tasks (true=only flagged, false=only unflagged)"),
    completed: z.boolean().optional().describe("Filter for completed tasks (true=only completed, false=only incomplete)"),
    blocked: z.boolean().optional().describe("Filter for blocked tasks (true=only blocked, false=only unblocked)"),
    dropped: z.boolean().optional().describe("Filter for dropped tasks (true=only dropped, false=only active)"),
    active: z.boolean().optional().describe("Filter for active tasks (true=only active, false=only dropped/inactive)"),
    // Inclusion parameters
    includeCompleted: z.boolean().optional().describe("Include completed tasks in results (default: false)"),
    includeDropped: z.boolean().optional().describe("Include dropped/inactive tasks in results (default: false)"),
    // Exclusion filters
    excludeProjectIds: z.array(z.string()).optional().describe("Project UUIDs to exclude from results"),
    excludeTagIds: z.array(z.string()).optional().describe("Tag UUIDs to exclude - tasks with any of these tags will be filtered out"),
    excludeFolderIds: z.array(z.string()).optional().describe("Folder UUIDs to exclude - tasks in projects within these folders will be filtered out"),
    // Advanced metadata filters
    hasEstimate: z.boolean().optional().describe("Filter for tasks with/without time estimates (true=has estimate, false=no estimate)"),
    minEstimate: z.number().positive().max(1440).optional().describe("Minimum time estimate in minutes (1-1440)"),
    maxEstimate: z.number().positive().max(1440).optional().describe("Maximum time estimate in minutes (1-1440)"),
    hasNotes: z.boolean().optional().describe("Filter for tasks with/without notes (true=has notes, false=no notes)"),
    hasDueDate: z.boolean().optional().describe("Filter for tasks with/without due dates (true=has due date, false=no due date)"),
    hasDeferDate: z.boolean().optional().describe("Filter for tasks with/without defer dates (true=has defer date, false=no defer date)"),
    isOverdue: z.boolean().optional().describe("Filter for overdue tasks (true=overdue only, false=not overdue)"),
    isDueToday: z.boolean().optional().describe("Filter for tasks due today (true=due today only, false=not due today)"),
    isDueSoon: z.number().positive().max(365).optional().describe("Filter for tasks due within N days (1-365 days)"),
    isAvailable: z.boolean().optional().describe("Filter for available tasks (true=available now, false=blocked/deferred)"),
    // Result control
    maxResults: z.number().int().positive().optional().describe("Maximum number of results to return (default: 100)")
}, async (args) => {
    const results = await callOmniFocus({ command: "universalQuery", args });
    return asJsonText(results);
});
// ============ FOLDER MANAGEMENT TOOLS (Task 4-1) ============
server.tool("createFolder", "Create a new folder in OmniFocus with optional parent folder and positioning", {
    name: z.string().describe("Folder name (required, non-empty string)"),
    parentFolderId: z.string().optional().describe("Parent folder UUID for nested folder creation"),
    position: z.number().int().min(0).optional().describe("Position within parent folder or library (0-based index)")
}, async (args) => {
    const result = await callOmniFocus({ command: "createFolder", args });
    return asJsonText(result);
});
server.tool("validateFolderName", "Validate a folder name before creation, checking for duplicates and invalid characters", {
    name: z.string().describe("Folder name to validate"),
    parentFolderId: z.string().optional().describe("Parent folder UUID to check for duplicate names within")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateFolderName", args });
    return asJsonText(result);
});
server.tool("getFolderById", "Get detailed information about a specific folder by its UUID", {
    folderId: z.string().describe("Folder UUID to retrieve information for")
}, async (args) => {
    const result = await callOmniFocus({ command: "getFolderById", args });
    return asJsonText(result);
});
server.tool("moveProject", "Move a project between folders with optional position control", {
    projectId: z.string().describe("Project UUID to move"),
    targetFolderId: z.string().optional().describe("Target folder UUID (omit for library root)"),
    position: z.number().int().min(0).optional().describe("Position within target folder (0-based index)")
}, async (args) => {
    const result = await callOmniFocus({ command: "moveProject", args });
    return asJsonText(result);
});
server.tool("validateProjectMove", "Validate a project move before execution, checking for errors and redundant moves", {
    projectId: z.string().describe("Project UUID to validate move for"),
    targetFolderId: z.string().optional().describe("Target folder UUID (omit for library root)")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateProjectMove", args });
    return asJsonText(result);
});
server.tool("getProjectById", "Get detailed information about a specific project by its UUID", {
    projectId: z.string().describe("Project UUID to retrieve information for")
}, async (args) => {
    const result = await callOmniFocus({ command: "getProjectById", args });
    return asJsonText(result);
});
server.tool("deleteFolder", "Delete a folder with safe handling of contained projects. Requires explicit confirmation to prevent accidental data loss.", {
    folderId: z.string().describe("Folder UUID to delete"),
    moveProjectsTo: z.string().optional().describe("Target folder UUID to move contained projects to (omit for library root)"),
    confirmDeletion: z.boolean().describe("Required explicit confirmation flag - must be true to proceed with deletion")
}, async (args) => {
    const result = await callOmniFocus({ command: "deleteFolder", args });
    return asJsonText(result);
});
server.tool("validateFolderDeletion", "Validate folder deletion before execution, checking for contained projects and subfolders", {
    folderId: z.string().describe("Folder UUID to validate deletion for"),
    moveProjectsTo: z.string().optional().describe("Target folder UUID for contained projects (omit for library root)")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateFolderDeletion", args });
    return asJsonText(result);
});
server.tool("getFolderProjects", "Get detailed information about all projects contained within a folder", {
    folderId: z.string().describe("Folder UUID to get projects for")
}, async (args) => {
    const result = await callOmniFocus({ command: "getFolderProjects", args });
    return asJsonText(result);
});
server.tool("createProject", "Create a new project with optional folder assignment, positioning, and property setting", {
    name: z.string().describe("Project name (required, non-empty string)"),
    folderId: z.string().optional().describe("Folder UUID to create project in (omit for library root)"),
    position: z.number().int().min(0).optional().describe("Position within folder or library (0-based index)"),
    properties: z.object({
        note: z.string().optional().describe("Project note/description"),
        dueDate: z.string().optional().describe("ISO due date"),
        deferDate: z.string().optional().describe("ISO defer date"),
        flagged: z.boolean().optional().describe("Whether to flag the project"),
        sequential: z.boolean().optional().describe("Whether tasks complete in sequence (true) or parallel (false)"),
        completedByChildren: z.boolean().optional().describe("Whether project auto-completes when last task is done"),
        estimatedMinutes: z.number().positive().optional().describe("Estimated duration in minutes"),
        tagIds: z.array(z.string()).optional().describe("Array of tag UUIDs to assign to project")
    }).optional().describe("Optional project properties to set during creation")
}, async (args) => {
    const result = await callOmniFocus({ command: "createProject", args });
    return asJsonText(result);
});
server.tool("validateProjectCreation", "Validate project creation parameters before execution, checking for duplicates and invalid properties", {
    name: z.string().describe("Project name to validate"),
    folderId: z.string().optional().describe("Target folder UUID (omit for library root)"),
    properties: z.object({
        dueDate: z.string().optional().describe("ISO due date to validate"),
        deferDate: z.string().optional().describe("ISO defer date to validate"),
        tagIds: z.array(z.string()).optional().describe("Array of tag UUIDs to validate")
    }).optional().describe("Optional project properties to validate")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateProjectCreation", args });
    return asJsonText(result);
});
server.tool("setProjectProperties", "Update properties of an existing project", {
    projectId: z.string().describe("Project UUID to update"),
    properties: z.object({
        name: z.string().optional().describe("New project name"),
        note: z.string().optional().describe("Project note/description"),
        dueDate: z.string().nullable().optional().describe("ISO due date (null to clear)"),
        deferDate: z.string().nullable().optional().describe("ISO defer date (null to clear)"),
        flagged: z.boolean().optional().describe("Whether to flag the project"),
        sequential: z.boolean().optional().describe("Whether tasks complete in sequence (true) or parallel (false)"),
        completedByChildren: z.boolean().optional().describe("Whether project auto-completes when last task is done"),
        estimatedMinutes: z.number().nullable().optional().describe("Estimated duration in minutes (null to clear)"),
        tagIds: z.array(z.string()).optional().describe("Array of tag UUIDs to assign to project (replaces existing tags)")
    }).describe("Project properties to update")
}, async (args) => {
    const result = await callOmniFocus({ command: "setProjectProperties", args });
    return asJsonText(result);
});
server.tool("convertTaskToProject", "Convert an existing task into a project with optional folder placement and subtask preservation", {
    taskId: z.string().describe("Task UUID to convert to project"),
    folderId: z.string().optional().describe("Target folder UUID for new project (omit for library root)"),
    position: z.number().int().min(0).optional().describe("Position within target folder or library (0-based index)"),
    preserveSubtasks: z.boolean().optional().describe("Whether to preserve existing subtasks as project tasks (default: true)")
}, async (args) => {
    const result = await callOmniFocus({ command: "convertTaskToProject", args });
    return asJsonText(result);
});
server.tool("validateTaskConversion", "Validate task-to-project conversion before execution, checking for constraints and potential issues", {
    taskId: z.string().describe("Task UUID to validate for conversion"),
    folderId: z.string().optional().describe("Target folder UUID (omit for library root)")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateTaskConversion", args });
    return asJsonText(result);
});
server.tool("getTaskSubtasks", "Get detailed information about all subtasks of a specific task", {
    taskId: z.string().describe("Task UUID to get subtasks for")
}, async (args) => {
    const result = await callOmniFocus({ command: "getTaskSubtasks", args });
    return asJsonText(result);
});
server.tool("moveTask", "Move a task between projects or within project hierarchy while preserving relationships. USE DIRECTLY for single task moves ONLY. For multiple moves, hierarchy restructuring, or complex reorganization, use restructureTaskHierarchy or executeTransactional(restructureTaskHierarchy) instead - do NOT chain multiple moveTask calls.", {
    taskId: z.string().describe("Task UUID to move"),
    targetProjectId: z.string().optional().describe("Target project UUID (omit for inbox)"),
    parentTaskId: z.string().optional().describe("Parent task UUID for creating subtask relationship (omit for project root level)"),
    position: z.number().int().min(0).optional().describe("Position within target location (0-based index)"),
    includeSubtasks: z.boolean().optional().describe("Whether to move all subtasks with the parent task (default: true)")
}, async (args) => {
    const result = await callOmniFocus({ command: "moveTask", args });
    return asJsonText(result);
});
server.tool("validateTaskMove", "Validate task movement before execution, checking for constraints and relationship integrity", {
    taskId: z.string().describe("Task UUID to validate for movement"),
    targetProjectId: z.string().optional().describe("Target project UUID (omit for inbox)"),
    parentTaskId: z.string().optional().describe("Parent task UUID for subtask relationship (omit for project root level)")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateTaskMove", args });
    return asJsonText(result);
});
server.tool("getTaskRelationships", "Get detailed information about all relationships of a specific task (children, dependencies, etc.)", {
    taskId: z.string().describe("Task UUID to get relationship information for")
}, async (args) => {
    const result = await callOmniFocus({ command: "getTaskRelationships", args });
    return asJsonText(result);
});
// ============ SUBTASK CREATION AND HIERARCHY MANAGEMENT TOOLS (Task 4-7) ============
server.tool("createSubtask", "Create a new subtask under an existing parent task with optional properties and positioning", {
    parentTaskId: z.string().describe("Parent task UUID to create subtask under"),
    name: z.string().describe("Name/title for the new subtask"),
    properties: z.object({
        note: z.string().optional().describe("Task note content"),
        dueDate: z.string().optional().describe("ISO format due date"),
        deferDate: z.string().optional().describe("ISO format defer date"),
        estimatedMinutes: z.number().positive().optional().describe("Estimated duration in minutes"),
        flagged: z.boolean().optional().describe("Whether to flag the subtask"),
        completedByChildren: z.boolean().optional().describe("Whether subtask completes when all its children are complete"),
        tagNames: z.array(z.string()).optional().describe("Tag names to apply to the subtask")
    }).optional().describe("Optional properties for the new subtask"),
    position: z.enum(['beginning', 'ending', 'before', 'after']).optional().describe("Position within parent's children"),
    siblingTaskId: z.string().optional().describe("Sibling task UUID (required for 'before' or 'after' position)")
}, async (args) => {
    const result = await callOmniFocus({ command: "createSubtask", args });
    return asJsonText(result);
});
server.tool("getTaskHierarchy", "Get the complete hierarchy tree of a task and all its descendants with full task details", {
    taskId: z.string().describe("Task UUID to get hierarchy for"),
    maxDepth: z.number().int().positive().optional().describe("Maximum depth to traverse (default: 10)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getTaskHierarchy", args });
    return asJsonText(result);
});
server.tool("createSubtaskHierarchy", "Create multiple subtasks at once with support for multi-level hierarchies and complex parent-child relationships", {
    parentTaskId: z.string().describe("Parent task UUID to create subtask hierarchy under"),
    subtaskSpecs: z.array(z.object({
        name: z.string().describe("Name for this subtask"),
        properties: z.object({
            note: z.string().optional().describe("Task note content"),
            dueDate: z.string().optional().describe("ISO format due date"),
            deferDate: z.string().optional().describe("ISO format defer date"),
            estimatedMinutes: z.number().positive().optional().describe("Estimated duration in minutes"),
            flagged: z.boolean().optional().describe("Whether to flag the subtask"),
            completedByChildren: z.boolean().optional().describe("Whether subtask completes when all its children are complete"),
            tagNames: z.array(z.string()).optional().describe("Tag names to apply to the subtask")
        }).optional().describe("Optional properties for this subtask"),
        position: z.enum(['beginning', 'ending', 'before', 'after']).optional().describe("Position within parent's children"),
        siblingTaskId: z.string().optional().describe("Sibling task UUID (required for 'before' or 'after' position)"),
        parentName: z.string().optional().describe("Name of previously created subtask to use as parent (for multi-level hierarchies)")
    })).describe("Array of subtask specifications to create")
}, async (args) => {
    const result = await callOmniFocus({ command: "createSubtaskHierarchy", args });
    return asJsonText(result);
});
server.tool("validateSubtaskCreation", "Validate subtask creation parameters before execution, checking parent task status and property validity", {
    parentTaskId: z.string().describe("Parent task UUID to validate subtask creation for"),
    properties: z.object({
        note: z.string().optional().describe("Task note content"),
        dueDate: z.string().optional().describe("ISO format due date"),
        deferDate: z.string().optional().describe("ISO format defer date"),
        estimatedMinutes: z.number().positive().optional().describe("Estimated duration in minutes"),
        flagged: z.boolean().optional().describe("Whether to flag the subtask"),
        completedByChildren: z.boolean().optional().describe("Whether subtask completes when all its children are complete"),
        tagNames: z.array(z.string()).optional().describe("Tag names to apply to the subtask")
    }).optional().describe("Optional properties to validate")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateSubtaskCreation", args });
    return asJsonText(result);
});
// ============ ADVANCED HIERARCHY OPERATIONS TOOLS (Task 4-8) ============
server.tool("flattenTaskHierarchy", "Flatten a task hierarchy with configurable flattening behavior - either to direct children or parent level. MODERATE-RISK: Consider using executeTransactional for rollback safety when flattening large hierarchies or when user requests safety.", {
    rootTaskId: z.string().describe("UUID of the root task whose hierarchy should be flattened"),
    preserveOrder: z.boolean().optional().describe("Whether to preserve the original task order (default: true)"),
    targetProjectId: z.string().optional().describe("Optional project UUID to move flattened tasks to (otherwise follows flattenTo behavior)"),
    flattenTo: z.enum(['directChildren', 'parentLevel']).optional().describe("Flatten mode: 'directChildren' makes all subtasks direct children of root task, 'parentLevel' moves all subtasks to same level as root task (default: directChildren)")
}, async (args) => {
    const result = await callOmniFocus({ command: "flattenTaskHierarchy", args });
    return asJsonText(result);
});
server.tool("moveTaskBranch", "Move an entire task branch (task and all its descendants) to a new location. USE THIS for moving task branches with children instead of multiple moveTask calls. MODERATE-RISK: Consider executeTransactional wrapper for rollback safety.", {
    taskId: z.string().describe("UUID of the root task of the branch to move"),
    newParentId: z.string().optional().describe("UUID of the new parent task (omit to move to project root/inbox)"),
    position: z.enum(['beginning', 'ending', 'before', 'after']).optional().describe("Position within the new parent's children (default: ending)"),
    siblingTaskId: z.string().optional().describe("Sibling task UUID for before/after positioning")
}, async (args) => {
    const result = await callOmniFocus({ command: "moveTaskBranch", args });
    return asJsonText(result);
});
server.tool("nestTasksAsHierarchy", "Convert flat tasks into a hierarchical structure based on provided hierarchy definition", {
    taskIds: z.array(z.string()).describe("Array of task UUIDs to be organized into hierarchy"),
    hierarchyStructure: z.array(z.object({
        taskId: z.string().describe("Task UUID being positioned"),
        parentId: z.string().optional().describe("Parent task UUID within the hierarchy (optional for root level)"),
        position: z.enum(['beginning', 'ending']).optional().describe("Position within parent's children (default: ending)")
    })).describe("Array defining the hierarchy structure"),
    parentTaskId: z.string().optional().describe("Optional parent task UUID to nest the entire hierarchy under")
}, async (args) => {
    const result = await callOmniFocus({ command: "nestTasksAsHierarchy", args });
    return asJsonText(result);
});
server.tool("restructureTaskHierarchy", "Execute multiple hierarchy operations in sequence for complex restructuring. PREFERRED for hierarchy rearrangement: Use this instead of multiple moveTask calls when reorganizing task hierarchies, moving task branches, or complex structural changes. HIGH-RISK OPERATION: Wrap in executeTransactional for rollback safety when doing major restructuring or when user requests safety.", {
    operations: z.array(z.object({
        type: z.enum(['move', 'moveBranch', 'createSubtask', 'flatten', 'nest']).describe("Type of operation to perform"),
        taskId: z.string().optional().describe("Task UUID (for move, moveBranch operations)"),
        parentTaskId: z.string().optional().describe("Parent task UUID (for createSubtask, nest operations)"),
        newParentId: z.string().optional().describe("New parent UUID (for move, moveBranch operations)"),
        targetProjectId: z.string().optional().describe("Target project UUID (for move operations)"),
        rootTaskId: z.string().optional().describe("Root task UUID (for flatten operations)"),
        flattenTo: z.enum(['directChildren', 'parentLevel']).optional().describe("Flatten mode (for flatten operations): 'directChildren' or 'parentLevel'"),
        taskIds: z.array(z.string()).optional().describe("Task UUIDs array (for nest operations)"),
        hierarchyStructure: z.array(z.any()).optional().describe("Hierarchy structure (for nest operations)"),
        name: z.string().optional().describe("Task name (for createSubtask operations)"),
        position: z.union([
            z.string(),
            z.number().int().nonnegative()
        ]).optional().describe("Position specification: string ('beginning', 'ending', 'before', 'after') or numeric index (0, 1, 2, ...)"),
        includeSubtasks: z.boolean().optional().describe("Include subtasks when moving (for move operations)"),
        properties: z.object({}).optional().describe("Task properties (for createSubtask operations)")
    })).describe("Array of hierarchy operations to execute"),
    validateOnly: z.boolean().optional().describe("Only validate operations without executing them (default: false)"),
    stopOnError: z.boolean().optional().describe("Stop execution on first error (default: true)")
}, async (args) => {
    const result = await callOmniFocus({ command: "restructureTaskHierarchy", args });
    return asJsonText(result);
});
server.tool("previewHierarchyOperation", "Preview the effects of a hierarchy operation without executing it", {
    operation: z.object({
        type: z.enum(['move', 'moveBranch', 'flatten', 'nest']).describe("Type of operation"),
        taskId: z.string().optional().describe("Task UUID for move/moveBranch operations"),
        rootTaskId: z.string().optional().describe("Root task UUID for flatten operations"),
        taskIds: z.array(z.string()).optional().describe("Task UUIDs for nest operations"),
        hierarchyStructure: z.array(z.any()).optional().describe("Hierarchy structure for nest operations")
    }).describe("Operation to preview")
}, async (args) => {
    const result = await callOmniFocus({ command: "previewHierarchyOperation", args });
    return asJsonText(result);
});
// ============ HIERARCHY VALIDATION SYSTEM TOOLS (Task 4-9) ============
server.tool("validateHierarchyIntegrity", "Validate hierarchy integrity and detect issues like circular dependencies, orphaned tasks, and invalid relationships", {
    rootId: z.string().optional().describe("UUID of specific hierarchy root to validate (omit to validate all hierarchies)"),
    includeRepairSuggestions: z.boolean().optional().describe("Include repair suggestions for detected issues (default: true)"),
    validationLevel: z.enum(['basic', 'standard', 'comprehensive']).optional().describe("Validation thoroughness level (default: comprehensive)")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateHierarchyIntegrity", args });
    return asJsonText(result);
});
server.tool("validateOperation", "Validate a hierarchy operation before execution to prevent invalid operations and assess risk", {
    operation: z.object({
        type: z.enum(['move', 'moveBranch', 'createSubtask', 'flatten', 'nest']).describe("Type of operation to validate"),
        taskId: z.string().optional().describe("Task UUID (for move, moveBranch operations)"),
        newParentId: z.string().optional().describe("New parent UUID (for move, moveBranch operations)"),
        targetProjectId: z.string().optional().describe("Target project UUID (for move operations)"),
        parentTaskId: z.string().optional().describe("Parent task UUID (for createSubtask operations)"),
        name: z.string().optional().describe("Task name (for createSubtask operations)"),
        rootTaskId: z.string().optional().describe("Root task UUID (for flatten operations)"),
        taskIds: z.array(z.string()).optional().describe("Task UUIDs array (for nest operations)"),
        hierarchyStructure: z.array(z.any()).optional().describe("Hierarchy structure (for nest operations)")
    }).describe("Operation to validate")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateOperation", args });
    return asJsonText(result);
});
server.tool("getValidationErrors", "Get detailed validation errors and analysis for specific hierarchies or all hierarchies", {
    hierarchyIds: z.array(z.string()).optional().describe("Array of hierarchy root UUIDs to check (omit for all hierarchies)"),
    errorTypes: z.array(z.string()).optional().describe("Filter by specific error types (omit for all types)"),
    severity: z.enum(['critical', 'medium', 'low']).optional().describe("Filter by error severity (omit for all severities)"),
    includeWarnings: z.boolean().optional().describe("Include warnings in results (default: true)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getValidationErrors", args });
    return asJsonText(result);
});
server.tool("repairHierarchyIntegrity", "Automatically repair hierarchy integrity issues with safety controls and dry-run support", {
    hierarchyId: z.string().describe("UUID of hierarchy root to repair"),
    repairTypes: z.array(z.enum(['all', 'critical', 'warnings', 'circular_dependency', 'orphaned_task', 'active_task_under_completed_parent', 'completed_parent_with_active_children'])).optional().describe("Types of repairs to attempt (default: ['all'])"),
    dryRun: z.boolean().optional().describe("Preview repairs without executing them (default: true for safety)"),
    maxOperations: z.number().int().positive().optional().describe("Maximum number of repair operations to attempt (default: 50)")
}, async (args) => {
    const result = await callOmniFocus({ command: "repairHierarchyIntegrity", args });
    return asJsonText(result);
});
// ============ PROJECT & TASK WORKFLOW MANAGEMENT TOOLS (Phase 4: Tasks 3-5, 3-6, 3-7) ============
server.tool("getProjectGroupType", "Get the group type (parallel/sequential) for a project's tasks", {
    projectName: z.string().optional().describe("Project name (use either projectName or projectId)"),
    projectId: z.string().optional().describe("Project UUID (use either projectName or projectId)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getProjectGroupType", args });
    return asJsonText(result);
});
server.tool("setProjectGroupType", "Set whether project tasks complete in parallel (independently) or sequential (dependency chain) order", {
    projectName: z.string().optional().describe("Project name (use either projectName or projectId)"),
    projectId: z.string().optional().describe("Project UUID (use either projectName or projectId)"),
    groupType: z.enum(["parallel", "sequential"]).describe("Group type: 'parallel' for independent completion, 'sequential' for dependency chain")
}, async (args) => {
    const result = await callOmniFocus({ command: "setProjectGroupType", args });
    return asJsonText(result);
});
server.tool("getProjectCompletionBehavior", "Get whether a project auto-completes when the last task is done or requires manual completion", {
    projectName: z.string().optional().describe("Project name (use either projectName or projectId)"),
    projectId: z.string().optional().describe("Project UUID (use either projectName or projectId)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getProjectCompletionBehavior", args });
    return asJsonText(result);
});
server.tool("setProjectCompletionBehavior", "Set project completion behavior - whether it auto-completes with last task or requires manual completion", {
    projectName: z.string().optional().describe("Project name (use either projectName or projectId)"),
    projectId: z.string().optional().describe("Project UUID (use either projectName or projectId)"),
    completionBehavior: z.enum(["completeWithLastAction", "manual"]).describe("Completion behavior: 'completeWithLastAction' for auto-complete, 'manual' for explicit completion required")
}, async (args) => {
    const result = await callOmniFocus({ command: "setProjectCompletionBehavior", args });
    return asJsonText(result);
});
server.tool("getTaskGroupType", "Get the group type (parallel/sequential) for a parent task's subtasks. Only works on tasks that have subtasks.", {
    taskName: z.string().optional().describe("Task name (use either taskName or taskId)"),
    taskId: z.string().optional().describe("Task UUID (use either taskName or taskId)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getTaskGroupType", args });
    return asJsonText(result);
});
server.tool("setTaskGroupType", "Set whether subtasks within a parent task complete in parallel (independently) or sequential (dependency chain) order. Only works on tasks that have subtasks.", {
    taskName: z.string().optional().describe("Task name (use either taskName or taskId)"),
    taskId: z.string().optional().describe("Task UUID (use either taskName or taskId)"),
    groupType: z.enum(["parallel", "sequential"]).describe("Group type: 'parallel' for independent subtask completion, 'sequential' for subtask dependency chain")
}, async (args) => {
    const result = await callOmniFocus({ command: "setTaskGroupType", args });
    return asJsonText(result);
});
// ============ PROJECT HIERARCHY NAVIGATION TOOLS (Task 3-4) ============
server.tool("getProjectHierarchy", "Get a flat list of all projects with their folder path context. Returns comprehensive project organization data with folder paths, depths, and project metadata for AI analysis.", {
    includeCompleted: z.boolean().optional().describe("Include completed projects in results (default: false)"),
    includeDropped: z.boolean().optional().describe("Include dropped/inactive projects in results (default: false)"),
    maxDepth: z.number().int().positive().optional().describe("Maximum folder depth to include (unlimited if not specified)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getProjectHierarchy", args });
    return asJsonText(result);
});
server.tool("getProjectTree", "Get the complete project organization as a nested tree structure. Returns hierarchical view of folders and projects for sophisticated navigation and analysis. Use this for understanding overall organization structure.", {
    includeCompleted: z.boolean().optional().describe("Include completed projects in results (default: false)"),
    includeDropped: z.boolean().optional().describe("Include dropped/inactive projects and folders in results (default: false)"),
    foldersOnly: z.boolean().optional().describe("Return only folder structure without project details (default: false)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getProjectTree", args });
    return asJsonText(result);
});
// ============ TRANSACTION MANAGEMENT TOOLS (Task 4-11) ============
// 
// DECISION FRAMEWORK FOR TRANSACTIONS:
// 
// ALWAYS USE TRANSACTIONS FOR:
// - 3+ operations in one user request
// - Batch operations ("move these tasks", "reorganize projects")  
// - Hierarchy restructuring with multiple steps
// - Cross-project operations affecting multiple containers
// - When user says "safely", "carefully", "reorganize", "restructure"
// - Operations that could create circular dependencies
//
// TRANSACTION WORKFLOW:
// 1. executeTransactional performs operations and auto-accepts (changes are immediately visible in OmniFocus)
// 2. Transaction moves to history with rollback capability (default: 10 minute timeout)
// 3. CRITICAL: "Accepted" transactions can STILL be rolled back within timeout window!
// 4. User can rollbackRecentTransaction within timeout window if they want to undo changes
// 5. ALWAYS tell user that changes can be rolled back for 10 minutes after completion
// 6. Expired transactions are automatically cleaned up and can no longer be rolled back
//
// HIERARCHY OPERATION PREFERENCE:
// - For hierarchy rearrangement: Use restructureTaskHierarchy (wrapped in executeTransactional)
// - For multiple task moves: Use executeTransactional([restructureTaskHierarchy]) NOT multiple moveTask
// - For complex structural changes: Use hierarchy operations, not individual moves
// - For single task move: Use moveTask directly
//
// USE DIRECT COMMANDS FOR:
// - Single simple operations ("flag this task", "set due date")
// - Read-only operations (all list/get commands)
// - Inbox processing (already atomic)
// - Single task moves or property changes
//
// RISK INDICATORS:
// - HIGH-RISK: restructureTaskHierarchy, complex multi-project moves
// - MODERATE-RISK: flattenTaskHierarchy, moveTaskBranch
// - LOW-RISK: moveTask (single), createSubtask (single), property changes
//
server.tool("beginTransaction", "Begin a new transaction for atomic execution of multiple hierarchy operations with rollback support. ADVANCED USE: Prefer executeTransactional for most cases. Use this only when you need manual control over individual operation steps.", {
    description: z.string().optional().describe("Description of the transaction purpose (default: 'Complex hierarchy operation')"),
    validateBefore: z.boolean().optional().describe("Validate hierarchy integrity before starting transaction (default: true)"),
    dryRun: z.boolean().optional().describe("Run transaction in dry-run mode without making actual changes (default: false)")
}, async (args) => {
    const result = await callOmniFocus({ command: "beginTransaction", args });
    return asJsonText(result);
});
server.tool("executeTransactional", "Execute multiple hierarchy operations atomically with automatic rollback on failure. Changes become visible immediately in OmniFocus and are auto-accepted but REMAIN ROLLBACK-ABLE FOR 10 MINUTES via rollbackRecentTransaction. IMPORTANT: After execution, ALWAYS tell the user that changes can be rolled back within 10 minutes if they say 'undo that' or 'roll back those changes'. The transaction being 'accepted' does NOT prevent rollback within the timeout window. USE THIS FOR: 3+ operations, hierarchy changes, batch operations, cross-project moves, or when user requests safety. EXAMPLES: 'reorganize projects', 'move multiple tasks', 'safely restructure'. PREFER restructureTaskHierarchy within transactions for hierarchy rearrangement rather than multiple moveTask operations. DO NOT use for single simple operations like flagging one task.", {
    operations: z.array(z.object({
        method: z.string().describe("OmniFocus operation method name. For hierarchy changes prefer: 'restructureTaskHierarchy' (multi-step restructuring), 'flattenTaskHierarchy' (flatten hierarchies), 'moveTaskBranch' (move branches). Use 'moveTask' only for single task moves."),
        parameters: z.record(z.any()).optional().describe("Parameters for the operation method")
    })).describe("Array of operations to execute in transaction. Each operation should be a meaningful unit that contributes to the overall goal. Prefer 3-20 operations per transaction."),
    description: z.string().optional().describe("Description of the batch operation (default: 'Batch hierarchy operations')"),
    validateBefore: z.boolean().optional().describe("Validate hierarchy before execution (default: true)"),
    validateAfter: z.boolean().optional().describe("Validate hierarchy after execution (default: true)"),
    dryRun: z.boolean().optional().describe("Execute in dry-run mode without making changes (default: false)"),
    rollbackOnError: z.boolean().optional().describe("Automatically rollback if any operation fails (default: true)"),
    maxOperations: z.number().int().positive().optional().describe("Maximum number of operations to execute (default: 50)")
}, async (args) => {
    const result = await callOmniFocus({ command: "executeTransactional", args });
    return asJsonText(result);
});
server.tool("acceptTransaction", "Accept an active transaction, finalizing all changes that are already visible in OmniFocus. Use this when user is satisfied with the results and wants to make the transaction permanent. Changes are already applied - this just marks them as accepted.", {
    transactionId: z.string().describe("Transaction ID to accept"),
    validateAfter: z.boolean().optional().describe("Perform final validation before accepting (default: false)")
}, async (args) => {
    const result = await callOmniFocus({ command: "acceptTransaction", args });
    return asJsonText(result);
});
server.tool("rollbackTransaction", "Rollback an active transaction, undoing all changes that were made during the transaction. Changes will be reverted in OmniFocus and the transaction will be marked as rolled back. Only works on ACTIVE transactions - use immediately after executeTransactional or before acceptTransaction.", {
    transactionId: z.string().describe("Transaction ID to rollback")
}, async (args) => {
    const result = await callOmniFocus({ command: "rollbackTransaction", args });
    return asJsonText(result);
});
server.tool("rollbackRecentTransaction", "Rollback a recently completed transaction within the timeout window (default: 10 minutes). USE THIS when user says 'undo that', 'roll back the last change', 'revert those changes', etc. IMPORTANT: This works on ACCEPTED transactions - the transaction being 'accepted' does NOT prevent rollback within the 10-minute timeout period. Changes will be reverted using OmniFocus's undo system. Always inform the user that rollback is available for recent changes.", {
    transactionId: z.string().optional().describe("Specific transaction ID to rollback (omit to rollback most recent)"),
    findByDescription: z.string().optional().describe("Find transaction by description keywords (e.g. 'hierarchy restructuring')")
}, async (args) => {
    const result = await callOmniFocus({ command: "rollbackRecentTransaction", args });
    return asJsonText(result);
});
server.tool("getTransactionHistory", "Get history of transactions with their status, operations, and results", {
    includeActive: z.boolean().optional().describe("Include currently active transactions (default: true)"),
    maxResults: z.number().int().positive().optional().describe("Maximum number of transactions to return (default: 20)"),
    status: z.enum(['active', 'accepted', 'rolled_back']).optional().describe("Filter by transaction status (omit for all statuses)")
}, async (args) => {
    const result = await callOmniFocus({ command: "getTransactionHistory", args });
    return asJsonText(result);
});
server.tool("validateTransaction", "Validate a set of operations before executing them in a transaction. USE BEFORE complex operations to assess risk and provide user with safety information. Always use when user asks to 'check if safe' or before risky multi-step operations.", {
    operations: z.array(z.object({
        method: z.string().describe("OmniFocus operation method name"),
        parameters: z.record(z.any()).optional().describe("Parameters for the operation method")
    })).describe("Array of operations to validate"),
    description: z.string().optional().describe("Description for validation (default: 'Transaction validation')"),
    performDeepValidation: z.boolean().optional().describe("Perform deep validation including hierarchy integrity (default: true)")
}, async (args) => {
    const result = await callOmniFocus({ command: "validateTransaction", args });
    return asJsonText(result);
});
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("✅ OmniFocus MCP running on stdio");
}
main().catch((err) => {
    console.error("Fatal error starting OmniFocus MCP:", err);
    process.exit(1);
});
