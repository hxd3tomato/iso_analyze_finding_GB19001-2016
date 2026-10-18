/**
 * 六个工具的定义。与宿主解耦：defineTool 与引擎调用都由外部注入，
 * 便于在宿主之外做单元测试。
 */

function renderAnalyze(_args, value) {
  const lines = [];
  lines.push("条款 " + value.clause + " " + value.clause_title + "（置信度 " + value.confidence + "）");
  lines.push("等级 " + value.severity.level + "（" + value.severity.score + " 分）" +
    (value.severity.drivers && value.severity.drivers.length ? "｜" + value.severity.drivers.join(", ") : ""));
  lines.push("【判定依据】" + value.statement.basis);
  lines.push("【影响】" + value.statement.impact);
  if (value.exclusions && value.exclusions.length) {
    lines.push("【排除】" + value.exclusions.map((x) => x.clause + "：" + x.reason).join("；"));
  }
  if (value.evidence_gap && value.evidence_gap.length) {
    lines.push("【待补证据】" + value.evidence_gap.join("、"));
  }
  if (value.next_questions && value.next_questions.length) {
    lines.push("【追问】" + value.next_questions.join("；"));
  }
  lines.push("【整改】纠正：" + value.capa.correction);
  lines.push("　　　　纠正措施：" + (value.capa.corrective_actions || []).join("；"));
  lines.push("　　　　验证：" + (value.capa.verification || []).join("；"));
  if (value.need_human) lines.push("提示：置信度不足或存在候选冲突，建议人工确认条款与等级。");
  return [{ type: "text", text: lines.join("\n") }];
}

function renderClause(_args, value) {
  return [{
    type: "text",
    text: [
      value.number + " " + value.title,
      "要求：" + String(value.requirement_text || "").slice(0, 220),
      "意图：" + value.intent,
      "证据：" + (value.evidence || []).join("、"),
      "案例：" + (value.cases || []).map((c) => c.id + "(" + c.severity + ")").join("、"),
      "检查项：" + (value.audit_items || []).slice(0, 3).map((i) => i.question).join(" / "),
    ].join("\n"),
  }];
}


function renderMatch(_args, value) {
  const lines = (value.candidates || []).map((c) =>
    c.clause + " " + c.title + "  score=" + c.score + " conf=" + c.confidence +
    (c.matched_terms && c.matched_terms.length ? "  命中：" + c.matched_terms.join("/") : ""));
  return [{ type: "text", text: lines.join("\n") || "无匹配条款" }];
}

function renderCapa(_args, value) {
  const p = value.plan;
  return [{
    type: "text",
    text: [
      "条款 " + value.clause + "｜建议等级 " + value.severity,
      "纠正：" + p.correction,
      "纠正措施：" + (p.corrective_actions || []).join("；"),
      "验证：" + (p.verification || []).join("；"),
      "责任：" + p.owner_suggestion + "｜时限：" + JSON.stringify(p.timeline),
      "横向排查：" + (p.horizontal_check || []).join("；"),
      "待修订：" + (p.documents_to_update || []).join("；"),
    ].join("\n"),
  }];
}

function buildReport(meta, findings) {
  const L = [];
  L.push("# 内部审核报告", "");
  L.push("- 审核编号：" + meta.id);
  L.push("- 审核目的：" + meta.purpose);
  L.push("- 审核范围：" + meta.scope);
  L.push("- 审核准则：GB/T 19001-2016、体系文件、适用法律法规");
  L.push("- 审核日期：" + meta.date);
  L.push("- 审核组：" + meta.team);
  L.push("", "## 一、不符合汇总", "", "| 序号 | 条款 | 等级 | 现象摘要 |", "|---|---|---|---|");
  findings.forEach((f, i) => {
    const fact = String(f.fact || (f.statement && f.statement.fact) || "").replace(/\|/g, "／").slice(0, 60);
    L.push("| " + (i + 1) + " | " + f.clause + " " + (f.clause_title || "") + " | " + f.level + " | " + fact + " |");
  });
  L.push("", "## 二、逐条详情", "");
  findings.forEach((f, i) => {
    const s = f.statement || {};
    L.push("### " + (i + 1) + ". " + f.clause + " " + (f.clause_title || ""), "");
    L.push("**不符合事实**：" + (s.fact || ""), "");
    L.push("**判定依据**：" + (s.basis || ""), "");
    L.push("**差异**：" + (s.gap || ""), "");
    L.push("**影响**：" + (s.impact || ""), "");
    L.push("**等级**：" + f.level + "（" + f.score + " 分）", "");
    const cp = f.capa || {};
    L.push("**整改要求**：", "");
    L.push("- 纠正：" + (cp.correction || ""));
    L.push("- 纠正措施：" + (cp.corrective_actions || []).join("；"));
    L.push("- 验证：" + (cp.verification || []).join("；"));
    L.push("- 责任：" + (cp.owner_suggestion || ""));
    L.push("");
  });
  const dist = {};
  for (const f of findings) dist[f.level] = (dist[f.level] || 0) + 1;
  L.push("## 三、统计", "", "| 等级 | 数量 |", "|---|---|");
  for (const k of Object.keys(dist).sort()) L.push("| " + k + " | " + dist[k] + " |");
  L.push("", "> 本报告由知识库引擎生成，条款与等级须经审核组长复核后签发。");
  return L.join("\n");
}


export function buildTools(defineTool, callEngine, stateOf, cfg) {
  const recordByDefault = !(cfg && cfg.recordByDefault === false);

  return [
    defineTool({
      name: "iso_analyze_finding",
      description: [
        "对一条内审/外审发现（现象描述）做定性：匹配 GB/T 19001-2016 条款、判定严重程度、",
        "生成四段式不符合陈述（事实/依据/差异/影响）、待补证据、追问链与整改三件套。",
        "现象描述应包含地点、时间、对象、编号、数量等客观事实，不要先写结论。",
        "默认会把结果记入本会话清单，便于 iso_audit_report 汇总。",
      ].join(""),
      parameters: {
        text: { type: "string", required: true, description: "审核发现的客观描述" },
        doc_ref: { type: "string", description: "相关组织文件编号或条款，如 WI-ASM-03 C/0、程序 P-08 5.4" },
        top_k: { type: "number", description: "返回候选条款数量，默认 3" },
        record: { type: "boolean", description: "是否记入本会话清单，默认 true" },
      },
      output: { schema: { type: "json" }, render: renderAnalyze },
      async execute(args, exec) {
        const data = await callEngine("analyze", {
          text: args.text,
          doc_ref: args.doc_ref || "",
          top_k: args.top_k || 3,
        });
        const f = data.findings && data.findings[0];
        if (!f) throw new Error("引擎未返回定性结果");
        const findingId = "F-" + Date.now().toString(36);
        const result = {
          finding_id: findingId,
          clause: f.clause_main.number,
          clause_title: f.clause_main.title,
          confidence: f.clause_main.confidence,
          severity: f.severity,
          statement: f.statement,
          candidates: (f.clause_candidates || []).map((c) => ({
            clause: c.clause, title: c.title, score: c.score,
            confidence: c.confidence, matched_terms: c.matched_terms || [],
          })),
          exclusions: f.exclusions || [],
          evidence_gap: f.evidence_gap || [],
          next_questions: f.next_questions || [],
          capa: f.capa,
          need_human: Boolean(data.need_human),
          validation: data.validation || { ok: true, issues: [] },
        };
        const shouldRecord = args.record === undefined ? recordByDefault : args.record;
        if (shouldRecord) {
          stateOf(exec).push({
            finding_id: findingId,
            clause: result.clause,
            clause_title: result.clause_title,
            level: result.severity.level,
            score: result.severity.score,
            fact: result.statement.fact,
            statement: result.statement,
            capa: result.capa,
          });
        }
        return result;
      },
    }),


    defineTool({
      name: "iso_match_clause",
      description: "只做条款匹配，不写结论、不提整改。返回 Top N 条款、分数、命中词，以及每个候选相对首选的排除理由。适用于审核员已有判断、只想核对条款的场景。",
      parameters: {
        text: { type: "string", required: true, description: "现象描述" },
        top_k: { type: "number", description: "候选数量，默认 3，最大 5" },
      },
      output: { schema: { type: "json" }, render: renderMatch },
      async execute(args) {
        const topK = Math.min(Math.max(args.top_k || 3, 1), 5);
        const data = await callEngine("match", { text: args.text, top_k: topK });
        return { candidates: data.candidates || [], need_human: Boolean(data.need_human) };
      },
    }),

    defineTool({
      name: "iso_suggest_capa",
      description: "针对某个条款（结合一条现象）生成整改建议：纠正（止血）、纠正措施（除因）、验证证据，以及责任岗位、时限、横向排查范围与需同步修订的文件。",
      parameters: {
        clause: { type: "string", required: true, description: "条款号，如 8.5.1" },
        severity: { type: "string", enum: ["MAJOR", "MINOR", "OBS"], description: "不符合等级，缺省时按现象自动判定" },
        text: { type: "string", description: "现象描述（用于选取最接近的案例）" },
        doc_ref: { type: "string", description: "相关文件编号" },
      },
      output: { schema: { type: "json" }, render: renderCapa },
      async execute(args) {
        return await callEngine("capa", {
          clause: args.clause,
          severity: args.severity || "",
          text: args.text || "",
          doc_ref: args.doc_ref || "",
        });
      },
    }),


    defineTool({
      name: "iso_clause_lookup",
      description: "查一个条款的完整信息：条款原文、条款意图、应查证据、常见不符合、易混条款，以及关联案例与检查项。",
      parameters: {
        clause: { type: "string", required: true, description: "条款号，如 7.5.3" },
      },
      output: { schema: { type: "json" }, render: renderClause },
      async execute(args) {
        return await callEngine("clause", { clause: args.clause });
      },
    }),

    defineTool({
      name: "iso_audit_findings",
      description: "查看本会话已记录的不符合清单，或清空它。生成报告前可先确认清单是否完整。",
      parameters: {
        action: { type: "string", required: true, enum: ["list", "clear"], description: "list 查看，clear 清空" },
      },
      output: {
        schema: { type: "json" },
        render: (_a, value) => [{
          type: "text",
          text: value.count === 0 ? "当前没有记录的不符合"
            : "已记录 " + value.count + " 条：" + value.findings.map((f) => f.finding_id + " " + f.clause + " " + f.level).join("；"),
        }],
      },
      async execute(args, exec) {
        const list = stateOf(exec);
        if (args.action === "clear") {
          const cleared = list.length;
          list.length = 0;
          return { count: 0, cleared: cleared, findings: [] };
        }
        return {
          count: list.length,
          findings: list.map((f) => ({
            finding_id: f.finding_id, clause: f.clause, clause_title: f.clause_title,
            level: f.level, score: f.score, fact: f.fact,
          })),
        };
      },
    }),

    defineTool({
      name: "iso_audit_report",
      description: "生成内审报告（Markdown）：汇总表、逐条详情（四段式与整改要求）、等级统计。默认消费本会话已记录的不符合。",
      parameters: {
        audit_id: { type: "string", description: "审核编号，如 IA-2026-02" },
        purpose: { type: "string", description: "审核目的" },
        scope: { type: "string", description: "审核范围（部门/场所/过程）" },
        date: { type: "string", description: "审核日期" },
        team: { type: "string", description: "审核组成员" },
        use_recorded: { type: "boolean", description: "是否使用本会话已记录的不符合，默认 true" },
      },
      output: {
        schema: { type: "json" },
        render: (_a, value) => [{
          type: "text",
          text: "已生成内审报告：" + value.count + " 条不符合，等级分布 " + JSON.stringify(value.distribution) + "。正文见 markdown 字段。",
        }],
      },
      async execute(args, exec) {
        const list = stateOf(exec);
        const findings = (args.use_recorded === false ? [] : list).slice();
        const meta = {
          id: args.audit_id || "-",
          purpose: args.purpose || "验证质量管理体系符合性与有效性",
          scope: args.scope || "-",
          date: args.date || "-",
          team: args.team || "-",
        };
        const distribution = {};
        for (const f of findings) distribution[f.level] = (distribution[f.level] || 0) + 1;
        return { markdown: buildReport(meta, findings), count: findings.length, distribution: distribution };
      },
    }),
  ];
}
