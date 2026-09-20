import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const root = path.resolve(process.cwd(), "..");
const windowsVenv = path.join(root, ".venv", "Scripts", "python.exe");
const unixVenv = path.join(root, ".venv", "bin", "python");
const python = fs.existsSync(windowsVenv) ? windowsVenv : fs.existsSync(unixVenv) ? unixVenv : "python";
const child = spawn(python, ["-m", "lifeline.cli", "serve", "--host", "127.0.0.1", "--port", "8875"], {
  cwd: root,
  stdio: "inherit"
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("exit", (code) => process.exit(code ?? 0));
