import { spawnSync } from "node:child_process";
import process from "node:process";

const task = process.argv[2] ?? "build";
const scriptsByTask = {
  build: [["scripts/build_dashboard_data.py"]],
  refresh: [
    ["scripts/ingest_opendota.py"],
    ["scripts/build_dashboard_data.py", "--prune-details"],
  ],
  refresh_full: [
    ["scripts/ingest_opendota.py", "--full"],
    ["scripts/build_dashboard_data.py", "--prune-details"],
  ],
};

if (!(task in scriptsByTask)) {
  console.error(`Unknown data task: ${task}`);
  process.exit(1);
}

const candidates = process.platform === "win32"
  ? [{ command: "python", args: [] }, { command: "py", args: ["-3"] }]
  : [{ command: "python3", args: [] }, { command: "python", args: [] }];

const python = candidates.find((candidate) => {
  const check = spawnSync(
    candidate.command,
    [...candidate.args, "-c", "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)"],
    { stdio: "ignore" },
  );
  return !check.error && check.status === 0;
});

if (!python) {
  console.error("Python 3 was not found. Install it or add python/python3 to PATH.");
  process.exit(1);
}

for (const [script, ...scriptArgs] of scriptsByTask[task]) {
  const result = spawnSync(python.command, [...python.args, script, ...scriptArgs], { stdio: "inherit" });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}
