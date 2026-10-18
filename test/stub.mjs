/**
 * 宿主替身：用真实的 Python 引擎跑通六个工具的 execute/render。
 * 运行：node test/stub.mjs
 */

import { makeCallEngine } from "../lib/engine.js";
import { buildTools } from "../lib/tools.js";
import { fallbackDefineTool } from "../lib/spec.js";

const registered = [];
const ctx = { tools: { register: (t) => registered.push(t) }, on: () => {} };

function stateOf() {
  if (!stateOf.list) stateOf.list = [];
  return stateOf.list;
}

const callEngine = makeCallEngine({ timeoutMs: 60000 });
const tools = buildTools(fallbackDefineTool, callEngine, stateOf, {});
for (const t of tools) ctx.tools.register(t);

const byName = Object.fromEntries(registered.map((t) => [t.name, t]));
const problems = [];

function check(name, ok, detail) {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? "  " + detail : ""));
  if (!ok) problems.push(name);
}

check("registered 6 tools", registered.length === 6, registered.map((t) => t.name).join(","));

for (const t of registered) {
  if (!t.name || !t.description || !t.parameters || !t.output || !t.output.render || !t.execute) {
    check("definition shape " + t.name, false);
  }
}
check("definition shapes", problems.length === 0);

const a = await byName.iso_analyze_finding.execute(
  { text: "查机加工车间2号线，4个工位使用B/2版作业指导书，受控清单为C/0版，旧版未回收" }, {});
check("analyze clause", a.clause === "7.5.3", a.clause);
check("analyze severity", a.severity.level === "MAJOR", a.severity.level + " " + a.severity.score);
check("analyze statement", Boolean(a.statement.fact && a.statement.basis && a.statement.gap && a.statement.impact));
check("analyze capa", (a.capa.corrective_actions || []).length > 0 && (a.capa.verification || []).length > 0);
check("analyze recorded", stateOf.list.length === 1);

const m = await byName.iso_match_clause.execute({ text: "两台叉车检验合格证已过期仍在使用" }, {});
check("match top1", m.candidates[0].clause === "7.1.3", m.candidates[0].clause);

const c = await byName.iso_suggest_capa.execute({ clause: "8.6", severity: "MAJOR", text: "终检记录代签" }, {});
check("capa owner", Boolean(c.plan.owner_suggestion));

const look = await byName.iso_clause_lookup.execute({ clause: "7.5.3" }, {});
check("lookup title", look.title === "成文信息的控制", look.title);
check("lookup cases", (look.cases || []).length >= 1);

const f = await byName.iso_audit_findings.execute({ action: "list" }, {});
check("findings list", f.count === 1);

const r = await byName.iso_audit_report.execute({ audit_id: "IA-TEST", scope: "全公司" }, {});
check("report count", r.count === 1);
check("report markdown", r.markdown.includes("# 内部审核报告") && r.markdown.includes("7.5.3"));

const cleared = await byName.iso_audit_findings.execute({ action: "clear" }, {});
check("findings clear", cleared.cleared === 1 && stateOf.list.length === 0);

// render 输出
for (const t of registered) {
  try {
    const rendered = t.name === "iso_analyze_finding" ? t.output.render({}, a)
      : t.name === "iso_match_clause" ? t.output.render({}, m)
      : t.name === "iso_suggest_capa" ? t.output.render({}, c)
      : t.name === "iso_clause_lookup" ? t.output.render({}, look)
      : t.name === "iso_audit_report" ? t.output.render({}, r)
      : t.output.render({}, f);
    check("render " + t.name, Array.isArray(rendered) && rendered[0] && rendered[0].type === "text"
      && rendered[0].text.length > 0);
  } catch (e) {
    check("render " + t.name, false, String(e.message));
  }
}

console.log("");
if (problems.length) {
  console.log("FAILED: " + problems.join(" | "));
  process.exit(1);
}
console.log("ALL PASS");
