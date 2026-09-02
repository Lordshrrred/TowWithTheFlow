#!/usr/bin/env node

import { execFileSync } from "node:child_process";

function git(args) {
  return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function changedFiles() {
  const from = process.env.VERCEL_GIT_PREVIOUS_SHA || "";
  const to = process.env.VERCEL_GIT_COMMIT_SHA || "HEAD";
  if (from && !/^0+$/.test(from)) {
    try {
      return git(["diff", "--name-only", `${from}...${to}`]).split("\n").filter(Boolean);
    } catch {
      // A shallow Vercel clone may not contain the prior deployment commit.
    }
  }
  return git(["diff-tree", "--no-commit-id", "--name-only", "-r", to]).split("\n").filter(Boolean);
}

const PUBLIC_PREFIXES = [
  "api/",
  "assets/",
  "content/",
  "data/",
  "layouts/",
  "static/",
  "themes/",
];
const PUBLIC_FILES = new Set([
  "config.toml",
  "hugo.toml",
  "package.json",
  "package-lock.json",
  "vercel.json",
  ".vercelignore",
  "scripts/build_dashboard.py",
  "scripts/vercel-ignore-build.js",
]);

try {
  const files = changedFiles();
  const publicFiles = files.filter(
    (file) => PUBLIC_FILES.has(file) || PUBLIC_PREFIXES.some((prefix) => file.startsWith(prefix)),
  );
  if (publicFiles.length) {
    console.log(`[vercel-ignore] Public output changed: ${publicFiles.slice(0, 8).join(", ")}`);
    process.exit(1);
  }
  console.log(`[vercel-ignore] Skipping operational-only commit: ${files.slice(0, 8).join(", ") || "no files"}`);
  process.exit(0);
} catch (error) {
  console.log(`[vercel-ignore] Could not classify changes; deploying fail-safe: ${error.message}`);
  process.exit(1);
}
