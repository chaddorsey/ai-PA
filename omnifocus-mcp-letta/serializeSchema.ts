// src/serializeSchema.ts ------------------------------------------------
import { z } from "zod";

/**
 * Minimal, MCP-compatible JSON-schema converter for our single tool.
 * Works for the `{ command: string, args?: object }` shape.
 */
export function serializeSchema(schema: z.ZodTypeAny) {
  return {
    type: "object",
    properties: {
      command: { type: "string" },
      args: { type: "object", additionalProperties: true },
    },
    required: ["command"],
    additionalProperties: false,
    $schema: "http://json-schema.org/draft-07/schema#",
  };
}
