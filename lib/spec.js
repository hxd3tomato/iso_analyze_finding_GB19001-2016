/**
 * 作者侧参数/输出 schema -> 原始 JSON Schema。
 *
 * 仅在宿主未提供 @deepseek-ai/dsh-tools 时作为兜底使用（正常路径由宿主
 * 的 defineTool 编译）。覆盖本插件用到的子集：object/array/string/number/
 * boolean/enum/description/required，以及 json（注解型，等价于空 schema）。
 */

function valueSchema(node) {
  const type = node.type || "string";
  if (type === "json") return {};
  const out = {};
  if (node.description) out.description = node.description;
  if (type === "array") {
    out.type = "array";
    out.items = valueSchema(node.items || { type: "string" });
    return out;
  }
  if (type === "object") {
    const map = node.properties || {};
    out.type = "object";
    out.properties = {};
    for (const key of Object.keys(map)) out.properties[key] = valueSchema(map[key]);
    return out;
  }
  out.type = type;
  if (node.enum) out.enum = node.enum.slice();
  return out;
}

export function parametersToJsonSchema(spec) {
  const properties = {};
  const required = [];
  for (const key of Object.keys(spec || {})) {
    const node = spec[key];
    properties[key] = valueSchema(node);
    if (node.required) required.push(key);
  }
  const schema = { type: "object", properties, additionalProperties: false };
  if (required.length) schema.required = required;
  return schema;
}

export function outputToJsonSchema(spec) {
  return valueSchema(spec || { type: "json" });
}

/** 宿主缺省时的最小 defineTool：只做 schema 编译，不做额外校验。 */
export function fallbackDefineTool(options) {
  const tool = {
    name: options.name,
    description: options.description,
    parameters: parametersToJsonSchema(options.parameters),
    output: {
      schema: outputToJsonSchema(options.output && options.output.schema),
      render: options.output && options.output.render
        ? options.output.render
        : () => [{ type: "text", text: options.name + " done" }],
    },
    execute: options.execute,
  };
  if (options.isConcurrencySafe) tool.isConcurrencySafe = options.isConcurrencySafe;
  return tool;
}
