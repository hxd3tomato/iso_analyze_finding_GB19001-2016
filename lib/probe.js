/**
 * 加载探针：只写一行 JSON 到临时目录，用于排查"插件是否被 import / apply 是否成功"。
 * 路径可用环境变量 ISO_AUDIT_MARKER 覆盖；写失败不影响插件。
 */

import { appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export function mark(event, extra) {
  const file = process.env.ISO_AUDIT_MARKER || join(tmpdir(), "iso-audit-plugin.log");
  const line = JSON.stringify(Object.assign({
    event,
    at: new Date().toISOString(),
    pid: process.pid,
  }, extra || {}));
  try {
    appendFileSync(file, line + "\n", "utf8");
  } catch (error) {
    /* 探针失败不影响主流程 */
  }
}

mark("module-import");
