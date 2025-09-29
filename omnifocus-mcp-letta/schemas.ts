import { z } from "zod";

export const detailLevelEnum = z.enum(["minimal", "standard", "full"]);
export type DetailLevel = z.infer<typeof detailLevelEnum>;

export const sortOrderEnum = z.enum(["default", "freshness"]);
export type SortOrder = z.infer<typeof sortOrderEnum>;

export const detailLevelSchema = detailLevelEnum.optional();
export const sortOrderSchema = sortOrderEnum.optional();

