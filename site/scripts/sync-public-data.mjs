import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const options = parseArgs(process.argv.slice(2));
const sourcePublicDirectory = resolveOptionPath(options.sourcePublicDir, "../../public_stats");
const targetPublicDirectory = resolveOptionPath(options.targetPublicDir, "../public");
const sourceDataDirectory = resolve(sourcePublicDirectory, "data");
const sourceCsvDirectory = resolve(sourcePublicDirectory, "csv");
const targetDataDirectory = resolve(targetPublicDirectory, "data");
const targetCsvDirectory = resolve(targetPublicDirectory, "csv");
const targetDownloadsDirectory = resolve(targetPublicDirectory, "downloads");

if (!existsSync(sourceDataDirectory)) {
  throw new Error(`Public stats directory not found: ${sourceDataDirectory}`);
}

if (!existsSync(sourceCsvDirectory)) {
  throw new Error(`Public CSV directory not found: ${sourceCsvDirectory}`);
}

prepareTargetDirectory(targetDataDirectory, ".json");
prepareTargetDirectory(targetCsvDirectory, ".csv");
prepareTargetDirectory(targetDownloadsDirectory, ".zip");

const jsonFiles = readdirSync(sourceDataDirectory).filter((name) => name.endsWith(".json"));
if (jsonFiles.length === 0) {
  throw new Error(
    `No JSON snapshots found in ${sourceDataDirectory}. Run scripts/build_public_stats.py first.`,
  );
}

const csvFiles = readdirSync(sourceCsvDirectory).filter((name) => name.endsWith(".csv"));
if (csvFiles.length === 0) {
  throw new Error(
    `No CSV exports found in ${sourceCsvDirectory}. Run scripts/build_public_stats.py first.`,
  );
}

for (const fileName of jsonFiles) {
  cpSync(resolve(sourceDataDirectory, fileName), resolve(targetDataDirectory, fileName));
}

for (const fileName of csvFiles) {
  cpSync(resolve(sourceCsvDirectory, fileName), resolve(targetCsvDirectory, fileName));
}

buildArchive({
  archivePath: resolve(targetDownloadsDirectory, "swiss-it-jobs-json-snapshots.zip"),
  workingDirectory: resolve(currentDirectory, "../public"),
  directoryName: "data",
});

buildArchive({
  archivePath: resolve(targetDownloadsDirectory, "swiss-it-jobs-csv-exports.zip"),
  workingDirectory: resolve(currentDirectory, "../public"),
  directoryName: "csv",
});

function prepareTargetDirectory(directoryPath, extension) {
  mkdirSync(directoryPath, { recursive: true });
  for (const entry of readdirSync(directoryPath, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith(extension)) {
      rmSync(resolve(directoryPath, entry.name));
    }
  }
}

function buildArchive({ archivePath, workingDirectory, directoryName }) {
  execFileSync("zip", ["-rq", archivePath, directoryName], {
    cwd: workingDirectory,
    stdio: "inherit",
  });
}

function parseArgs(args) {
  const options = {};
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--source-public-dir") {
      options.sourcePublicDir = requireValue(args, (index += 1), arg);
    } else if (arg === "--target-public-dir") {
      options.targetPublicDir = requireValue(args, (index += 1), arg);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return options;
}

function requireValue(args, index, flag) {
  const value = args[index];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function resolveOptionPath(value, defaultPath) {
  if (value) {
    return resolve(process.cwd(), value);
  }
  return resolve(currentDirectory, defaultPath);
}
