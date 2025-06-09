#!/usr/bin/env node
import { gzip } from "node:zlib";
import { promisify } from "node:util";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

const MAX_SIZE = 140 * 1024; // 140 KiB
const gzipAsync = promisify(gzip);

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else if (entry.isFile() && path.endsWith(".js")) {
      yield path;
    }
  }
}

async function check() {
  let failed = false;
  for await (const file of walk("app/static/js")) {
    const content = await readFile(file);
    const gzipped = await gzipAsync(content);
    const size = gzipped.length;
    console.log(`${file}: ${size} bytes`);
    if (size > MAX_SIZE) {
      console.error(`ERROR: ${file} exceeds ${MAX_SIZE} bytes`);
      failed = true;
    }
  }
  if (failed) process.exitCode = 1;
}

check();
