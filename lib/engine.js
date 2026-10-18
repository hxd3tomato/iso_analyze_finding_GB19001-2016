/** Python 引擎调用（桥接 engine/bridge.py）。 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
export const DEFAULT_BRIDGE = join(PKG_ROOT, "engine", "bridge.py");
export const DEFAULT_DATA = join(PKG_ROOT, "knowledge", "data");

function dshHome() {
  return process.env.DSH_HOME || join(homedir(), ".dsh");
}

export function pythonCandidates(cfg) {
  const list = [];
  if (cfg && cfg.python) list.push(cfg.python);
  if (process.env.ISO_KB_PYTHON) list.push(process.env.ISO_KB_PYTHON);
  const bundled = join(dshHome(), "dsh-runtimes", "dsh-primary-runtime", "dependencies", "python", "python.exe");
  if (existsSync(bundled)) list.push(bundled);
  list.push("python", "python3", "py");
  return Array.from(new Set(list));
}

function runOnce(python, bridge, cmd, payload, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [bridge, cmd], {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }),
    });
    let out = "";
    let err = "";
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try { child.kill(); } catch (e) { /* ignore */ }
      reject(new Error("引擎调用超时（" + timeoutMs + "ms）"));
    }, timeoutMs);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (c) => { out += c; });
    child.stderr.on("data", (c) => { err += c; });
    child.on("error", (e) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(e);
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error("引擎退出码 " + code + (err ? "：" + err.slice(-400) : "")));
        return;
      }
      try {
        const parsed = JSON.parse(out);
        if (!parsed.ok) reject(new Error(parsed.error || "引擎返回失败"));
        else resolve(parsed.data);
      } catch (e) {
        reject(new Error("引擎输出无法解析：" + out.slice(0, 300)));
      }
    });
    child.stdin.end(JSON.stringify(payload || {}), "utf8");
  });
}

/** 生成绑定到配置的调用函数；会缓存第一个可用的解释器。 */
export function makeCallEngine(cfg) {
  const bridge = cfg.bridge || DEFAULT_BRIDGE;
  const timeoutMs = cfg.timeoutMs || 60000;
  let cached = null;

  return async function callEngine(cmd, payload) {
    const candidates = cached ? [cached].concat(pythonCandidates(cfg)) : pythonCandidates(cfg);
    let lastError = null;
    for (const python of candidates) {
      try {
        const data = await runOnce(python, bridge, cmd, payload, timeoutMs);
        cached = python;
        return data;
      } catch (e) {
        lastError = e;
        if (e && (e.code === "ENOENT" || String(e.message).indexOf("ENOENT") >= 0)) continue;
        throw e;
      }
    }
    throw lastError || new Error("未找到可用的 Python 解释器");
  };
}
