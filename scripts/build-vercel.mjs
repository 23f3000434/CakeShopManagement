import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const frontend = resolve(root, "frontend");
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
execFileSync(npm, ["ci", "--include=dev"], { cwd: frontend, stdio: "inherit" });
execFileSync(npm, ["run", "build"], { cwd: frontend, stdio: "inherit" });
// Vercel serves public files from its CDN; Flask retains dist for SPA fallback.
mkdirSync(resolve(root, "public"), { recursive: true });
cpSync(resolve(frontend, "dist"), resolve(root, "public"), { recursive: true });
