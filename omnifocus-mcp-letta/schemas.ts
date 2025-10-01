import { z } from "zod";

export const detailLevelEnum = z.enum(["minimal", "standard", "full"]);
export type DetailLevel = z.infer<typeof detailLevelEnum>;

export const sortOrderEnum = z.enum(["default", "freshness"]);
export type SortOrder = z.infer<typeof sortOrderEnum>;

export const detailLevelSchema = detailLevelEnum.optional();
export const sortOrderSchema = sortOrderEnum.optional();

export const MarkCompletedInputSchema = z.object({
  id: z.string().uuid().describe("The UUID to mark as completed."),
  scope: z.enum(["task", "project"]).default("task"),
});
export type MarkCompletedInput = z.infer<typeof MarkCompletedInputSchema>;

export const CompletionSuccessSchema = z.object({
  scope: z.enum(["task", "project"]),
  id: z.string().uuid(),
  completionStatus: z.literal("completed"),
  completedAt: z.string().datetime(),
  alreadyCompleted: z.boolean().optional(),
});

export const CompletionResultSchema = z.object({
  completed: z.array(CompletionSuccessSchema),
  errors: z
    .array(
      z.object({
        id: z.string(),
        scope: z.enum(["task", "project", "unknown"]),
        message: z.string(),
      }),
    )
    .optional(),
});

export const ListUncompletedTasksInputSchema = z.object({
  projectId: z.string().optional(),
  onlyFlagged: z.boolean().optional(),
  onlyAvailable: z.boolean().optional(),
});
export type ListUncompletedTasksInput = z.infer<typeof ListUncompletedTasksInputSchema>;

export const TaskSummarySchema = z.object({
  taskId: z.string(),
  name: z.string(),
  projectId: z.string().nullable().optional(),
  inInbox: z.boolean().optional(),
  flagged: z.boolean().optional(),
  created: z.string().datetime().optional(),
  due: z.string().datetime().nullable().optional(),
  deferred: z.string().datetime().nullable().optional(),
});
export type TaskSummary = z.infer<typeof TaskSummarySchema>;

export const listUncompletedTasksResultSchema = z.array(TaskSummarySchema);
export type ListUncompletedTasksResult = z.infer<typeof listUncompletedTasksResultSchema>;

export const MoveTaskToProjectInputSchema = z.object({
  taskId: z.string().min(1, "taskId is required"),
  projectId: z.string().min(1, "projectId is required"),
});
export type MoveTaskToProjectInput = z.infer<typeof MoveTaskToProjectInputSchema>;

export const moveTaskToProjectResultSchema = z.object({
  taskId: z.string(),
  projectId: z.string(),
  status: z.literal("moved"),
});
export type MoveTaskToProjectResult = z.infer<typeof moveTaskToProjectResultSchema>;

export const ListProjectsInputSchema = z.object({
  folderId: z.string().optional(),
  listProjectNames: z.boolean().optional(),
  listByFolder: z.boolean().optional(),
});
export type ListProjectsInput = z.infer<typeof ListProjectsInputSchema>;

export const ProjectTaskSummarySchema = z.object({
  taskId: z.string(),
  name: z.string(),
});
export type ProjectTaskSummary = z.infer<typeof ProjectTaskSummarySchema>;

export const ProjectSummarySchema = z.object({
  projectId: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  folderId: z.string().nullable().optional(),
  taskIds: z.array(z.string()),
  tasks: z.array(ProjectTaskSummarySchema).optional(),
});
export type ProjectSummary = z.infer<typeof ProjectSummarySchema>;

export const listProjectsResultSchema = z.union([
  z.array(ProjectSummarySchema),
  z.array(
    z.object({
      folderId: z.string().nullable(),
      folderName: z.string().nullable(),
      projects: z.array(ProjectSummarySchema),
    }),
  ),
]);
export type ListProjectsResult = z.infer<typeof listProjectsResultSchema>;

export const quickToolSchemas = {
  markCompleted: MarkCompletedInputSchema,
  listUncompletedTasks: ListUncompletedTasksInputSchema,
  listProjects: ListProjectsInputSchema,
  moveTaskToProject: MoveTaskToProjectInputSchema,
};

export type CompletionSuccess = z.infer<typeof CompletionSuccessSchema>;
export type CompletionResult = z.infer<typeof CompletionResultSchema>;

