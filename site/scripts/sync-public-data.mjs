import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const sourceDirectory = resolve(currentDirectory, "../../public_stats/data");
const targetDirectory = resolve(currentDirectory, "../public/data");

if (!existsSync(sourceDirectory)) {
  throw new Error(`Public stats directory not found: ${sourceDirectory}`);
}

mkdirSync(targetDirectory, { recursive: true });
for (const entry of readdirSync(targetDirectory, { withFileTypes: true })) {
  if (entry.isFile() && entry.name.endsWith(".json")) {
    rmSync(resolve(targetDirectory, entry.name));
  }
}

const jsonFiles = readdirSync(sourceDirectory).filter((name) => name.endsWith(".json"));
if (jsonFiles.length === 0) {
  throw new Error(
    `No JSON snapshots found in ${sourceDirectory}. Run scripts/build_public_stats.py first.`,
  );
}

for (const fileName of jsonFiles) {
  cpSync(resolve(sourceDirectory, fileName), resolve(targetDirectory, fileName));
}
