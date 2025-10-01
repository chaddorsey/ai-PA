import { z } from "zod";

export const detailLevelEnum = z.enum(["minimal", "standard", "full"]);
export type DetailLevel = z.infer<typeof detailLevelEnum>;

export const sortOrderEnum = z.enum(["default", "freshness"]);
export type SortOrder = z.infer<typeof sortOrderEnum>;

export const detailLevelSchema = detailLevelEnum.optional();
export const sortOrderSchema = sortOrderEnum.optional();

export const markTaskCompletedInputSchema = z.object({
  taskId: z.string().min(1, "taskId is required"),
});
export type MarkTaskCompletedInput = z.infer<typeof markTaskCompletedInputSchema>;

export const markTaskCompletedResultSchema = z.object({
  taskId: z.string(),
  completionStatus: z.literal("completed"),
  completedAt: z.string().datetime().optional(),
  alreadyCompleted: z.boolean().optional(),
});
export type MarkTaskCompletedResult = z.infer<typeof markTaskCompletedResultSchema>;

export const listUncompletedTasksInputSchema = z.object({
  projectId: z.string().optional(),
  onlyFlagged: z.boolean().optional(),
  onlyAvailable: z.boolean().optional(),
});
export type ListUncompletedTasksInput = z.infer<typeof listUncompletedTasksInputSchema>;

export const taskSummarySchema = z.object({
  taskId: z.string(),
  name: z.string(),
  projectId: z.string().nullable().optional(),
  inInbox: z.boolean().optional(),
  flagged: z.boolean().optional(),
  created: z.string().datetime().optional(),
  due: z.string().datetime().nullable().optional(),
  deferred: z.string().datetime().nullable().optional(),
});
export type TaskSummary = z.infer<typeof taskSummarySchema>;

export const listUncompletedTasksResultSchema = z.array(taskSummarySchema);
export type ListUncompletedTasksResult = z.infer<typeof listUncompletedTasksResultSchema>;

export const moveTaskToProjectInputSchema = z.object({
  taskId: z.string().min(1, "taskId is required"),
  projectId: z.string().min(1, "projectId is required"),
});
export type MoveTaskToProjectInput = z.infer<typeof moveTaskToProjectInputSchema>;

export const moveTaskToProjectResultSchema = z.object({
  taskId: z.string(),
  projectId: z.string(),
  status: z.literal("moved"),
});
export type MoveTaskToProjectResult = z.infer<typeof moveTaskToProjectResultSchema>;

export const listProjectsInputSchema = z.object({
  folderId: z.string().optional(),
  listProjectNames: z.boolean().optional(),
  listByFolder: z.boolean().optional(),
});
export type ListProjectsInput = z.infer<typeof listProjectsInputSchema>;

export const projectTaskSummarySchema = z.object({
  taskId: z.string(),
  name: z.string(),
});
export type ProjectTaskSummary = z.infer<typeof projectTaskSummarySchema>;

export const projectSummarySchema = z.object({
  projectId: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  folderId: z.string().nullable().optional(),
  taskIds: z.array(z.string()),
  tasks: z.array(projectTaskSummarySchema).optional(),
});
export type ProjectSummary = z.infer<typeof projectSummarySchema>;

export const listProjectsResultSchema = z.union([
  z.array(projectSummarySchema),
  z.array(
    z.object({
      folderId: z.string().nullable(),
      folderName: z.string().nullable(),
      projects: z.array(projectSummarySchema),
    }),
  ),
]);
export type ListProjectsResult = z.infer<typeof listProjectsResultSchema>;

