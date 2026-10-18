/**
 * 宿主级集成测试：用真实的 @deepseek-ai/dsh-tools 编译/校验工具定义。
 * 需要在 DSH 的 Electron/Node 运行时里执行（普通 node 无法读 asar）。
 */

const toolsUrl = process.env.DSH_TOOLS_URL || "file:///C:/Users/78228/AppData/Local/Programs/DeepSeek%20Harness/resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-tools/lib/index.js";
const { assertSupportedJsonSchema, defineTool } = await import(toolsUrl);
import { makeCallEngine } from "../lib/engine.js";
import { fallbackDefineTool } from "../lib/spec.js";
import { buildTools } from "../lib/tools.js";

const state = [];
const stateOf = () => state;
const callEngine = makeCallEngine({ timeoutMs: 60000 });

const tools = buildTools(defineTool, callEngine, stateOf, {});
console.log("compiled tools:", tools.length);

let bad = 0;
for (const t of tools) {
  try {
    assertSupportedJsonSchema(t.parameters);
    assertSupportedJsonSchema(t.output.schema);
    console.log("schema OK", t.name,
      "| params:", Object.keys(t.parameters.properties || {}).join(","),
      "| required:", (t.parameters.required || []).join(","),
      "| output:", JSON.stringify(t.output.schema).slice(0, 60));
  } catch (e) {
    bad++;
    console.log("schema FAIL", t.name, String(e.message).slice(0, 200));
  }
}

// 兜底实现的 schema 也必须被宿主接受
for (const t of buildTools(fallbackDefineTool, callEngine, stateOf, {})) {
  try {
    assertSupportedJsonSchema(t.parameters);
    assertSupportedJsonSchema(t.output.schema);
  } catch (e) {
    bad++;
    console.log("fallback schema FAIL", t.name, String(e.message).slice(0, 200));
  }
}
console.log("fallback schemas checked");

const analyze = tools.find((t) => t.name === "iso_analyze_finding");
const res = await analyze.execute({ text: "现场4个工位使用B/2版作业指导书，受控清单为C/0版" });
console.log("execute clause:", res.clause, "| severity:", res.severity.level, "| recorded:", state.length);
const md = (await tools.find((t) => t.name === "iso_audit_report").execute({ audit_id: "IA-H1" })).markdown;
console.log("report chars:", md.length, "| has clause:", md.includes("7.5.3"));
console.log(bad === 0 ? "HOST TEST PASS" : "HOST TEST FAIL " + bad);
