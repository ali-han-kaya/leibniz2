const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const sourceDir = path.join(repoRoot, "_calisma", "CIKTI");
const runtimeDir = path.join(__dirname, ".runtime");
const installedMarker = path.join(runtimeDir, ".installed");
const startScript = path.resolve(__dirname, "start.js");

function shellQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

function pythonExecutable() {
  return process.env.PINOKIO_PYTHON || "python3";
}

function requiredFiles() {
  return [
    path.join(sourceDir, "preview_server.py"),
    path.join(sourceDir, "verify_delivery.py"),
    path.join(sourceDir, "preview.html"),
    path.join(sourceDir, "preview.js"),
    path.join(sourceDir, "vendor", "axe.min.js"),
  ];
}

function copyFile(source, target) {
  return `cp ${shellQuote(source)} ${shellQuote(target)}`;
}

function optionalCopy(source, target) {
  return `if [ -f ${shellQuote(source)} ]; then ${copyFile(source, target)}; fi`;
}

function optionalCopyDirectory(source, target) {
  return `if [ -d ${shellQuote(source)} ]; then mkdir -p ${shellQuote(target)}; cp -R ${shellQuote(`${source}/.`)} ${shellQuote(`${target}/`)}; fi`;
}

function prepareRuntimeCommand() {
  const vendorDir = path.join(runtimeDir, "vendor");
  const slidesDir = path.join(runtimeDir, "slides_z3");
  const commands = [
    `mkdir -p ${shellQuote(runtimeDir)} ${shellQuote(vendorDir)} ${shellQuote(slidesDir)}`,
    ...requiredFiles().map((file) => `test -f ${shellQuote(file)}`),
    copyFile(
      path.join(sourceDir, "preview.html"),
      path.join(runtimeDir, "preview.html")
    ),
    copyFile(
      path.join(sourceDir, "preview.js"),
      path.join(runtimeDir, "preview.js")
    ),
    copyFile(
      path.join(sourceDir, "vendor", "axe.min.js"),
      path.join(vendorDir, "axe.min.js")
    ),
    optionalCopy(
      path.join(repoRoot, "design-system", "tokens.css"),
      path.join(runtimeDir, "design-system-tokens.css")
    ),
    optionalCopy(
      path.join(sourceDir, "guide.html"),
      path.join(runtimeDir, "guide.html")
    ),
    optionalCopyDirectory(path.join(sourceDir, "slides_z3"), slidesDir),
    `${shellQuote(pythonExecutable())} -m py_compile ${shellQuote(path.join(sourceDir, "preview_server.py"))}`,
  ];
  return commands.join(" && ");
}

function serverCommand(port) {
  const numericPort = Number(port);
  if (
    !Number.isInteger(numericPort) ||
    numericPort < 1 ||
    numericPort > 65535
  ) {
    throw new Error(`invalid Pinokio port: ${port}`);
  }
  return [
    shellQuote(pythonExecutable()),
    shellQuote(path.join(sourceDir, "preview_server.py")),
    `--dir ${shellQuote(sourceDir)}`,
    `--preview-dir ${shellQuote(runtimeDir)}`,
    "--bind 127.0.0.1",
    `--port ${numericPort}`,
    "--interval 3600",
  ].join(" ");
}

module.exports = {
  repoRoot,
  sourceDir,
  runtimeDir,
  installedMarker,
  startScript,
  requiredFiles,
  prepareRuntimeCommand,
  serverCommand,
  shellQuote,
};
