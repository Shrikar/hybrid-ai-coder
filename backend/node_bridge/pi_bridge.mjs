#!/usr/bin/env node
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function findLocalPiBin() {
  const here = dirname(fileURLToPath(import.meta.url));
  const root = join(here, "..", "..");
  const unixBin = join(root, "node_modules", ".bin", "pi");
  if (existsSync(unixBin)) return unixBin;
  const winBin = join(root, "node_modules", ".bin", "pi.cmd");
  if (existsSync(winBin)) return winBin;
  return null;
}

async function main() {
  const raw = await readStdin();
  const req = JSON.parse(raw || "{}");
  const prompt = String(req.prompt || "");
  if (!prompt.trim()) {
    process.stderr.write("empty prompt");
    process.exit(2);
  }

  const piBin = findLocalPiBin();
  if (!piBin) {
    process.stderr.write("local pi binary not found in node_modules/.bin");
    process.exit(3);
  }

  const args = ["-p", prompt];
  if (req.provider) args.push("--provider", String(req.provider));
  if (req.model) args.push("--model", String(req.model));

  const child = spawn(piBin, args, {
    stdio: ["ignore", "pipe", "pipe"],
    env: process.env,
  });

  let out = "";
  let err = "";
  child.stdout.on("data", (chunk) => (out += chunk.toString()));
  child.stderr.on("data", (chunk) => (err += chunk.toString()));
  child.on("close", (code) => {
    if (code === 0) {
      process.stdout.write(JSON.stringify({ ok: true, text: out.trim() }));
      process.exit(0);
      return;
    }
    process.stdout.write(
      JSON.stringify({
        ok: false,
        error: err.trim() || out.trim() || `pi exited with code ${code}`,
      }),
    );
    process.exit(1);
  });
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(err) }));
  process.exit(1);
});
