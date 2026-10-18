/**
 * dsh-plugin-iso-audit —— ISO 9001 贯标审核助手（DSH Host 插件）
 *
 * 提供 6 个工具：
 *   iso_analyze_finding  现象定性（条款 + 等级 + 四段式陈述 + 整改）
 *   iso_match_clause     只做条款匹配
 *   iso_suggest_capa     整改三件套
 *   iso_clause_lookup    条款原文/证据/案例/检查项
 *   iso_audit_findings   本会话不符合清单（list/clear）
 *   iso_audit_report     生成内审报告
 */

import { appendFileSync } from "node:fs";
import { makeCallEngine } from "./engine.js";
import { fallbackDefineTool } from "./spec.js";
import { buildTools } from "./tools.js";

export const name = "tool-iso-audit";
export const inject = ["tools"];

let defineTool;
try {
  const mod = await import("@deepseek-ai/dsh-tools");
  defineTool = mod.defineTool;
} catch (error) {
  defineTool = fallbackDefineTool;
}

/** 按会话隔离的不符合清单（进程内）。 */
const FINDINGS = new Map();

function stateOf(exec) {
  const session = exec && exec.agent && exec.agent.session;
  const key = (session && session.id) || "default";
  if (!FINDINGS.has(key)) FINDINGS.set(key, []);
  return FINDINGS.get(key);
}

export function apply(ctx, config) {
  const cfg = config || {};
  const callEngine = makeCallEngine(cfg);
  const tools = buildTools(defineTool, callEngine, stateOf, cfg);
  for (const tool of tools) ctx.tools.register(tool);

  if (cfg.debugMarker) {
    try {
      appendFileSync(cfg.debugMarker, JSON.stringify({
        event: "loaded",
        at: new Date().toISOString(),
        pid: process.pid,
        tools: tools.map((t) => t.name),
        python: process.env.ISO_KB_PYTHON || "",
      }) + "\n", "utf8");
    } catch (error) {
      /* 标记失败不影响插件 */
    }
  }

  if (typeof ctx.on === "function") {
    ctx.on("dispose", () => FINDINGS.clear());
  }
}
