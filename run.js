const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const isWin = os.platform() === "win32";
const venvPythonWin = path.join(__dirname, ".venv", "Scripts", "python.exe");
const venvPythonNix = path.join(__dirname, ".venv", "bin", "python");

let pythonBin = isWin ? "python" : "python3";
if (isWin && fs.existsSync(venvPythonWin)) {
  pythonBin = venvPythonWin;
} else if (!isWin && fs.existsSync(venvPythonNix)) {
  pythonBin = venvPythonNix;
}

const instanceArg = (process.argv[2] || "pipl").toLowerCase();
const isNdcs = instanceArg.includes("ndcs");
const instanceName = isNdcs ? "NDCS" : "PIPL";
const port = isNdcs ? 4007 : 4006;

console.log(`[make-ai-service] Launching AI service for instance ${instanceName} on port ${port}...`);
console.log(`[make-ai-service] Using Python: ${pythonBin}`);

const env = {
  ...process.env,
  INSTANCE: instanceName,
  PORT: String(port),
  PYTHONUNBUFFERED: "1",
};

const args = ["-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", String(port), "--reload"];

const child = spawn(pythonBin, args, {
  cwd: __dirname,
  env,
  stdio: "inherit",
  shell: true,
});

child.on("close", (code) => {
  console.log(`[make-ai-service] Process exited with code ${code}`);
  process.exit(code || 0);
});

child.on("error", (err) => {
  console.error(`[make-ai-service] Failed to start process: ${err.message}`);
  process.exit(1);
});
