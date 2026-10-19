const fs = require("fs");
const path = require("path");
const {
  installedMarker,
  repoRoot,
  requiredFiles,
  startScript,
} = require("./runtime");

function scriptHref(name) {
  // Pinokio resolves nested launcher hrefs from the detected launcher root
  // (the directory containing this pinokio.js), not from the repository root.
  return name;
}

function isRunning(info, name) {
  return [name, `pinokio/${name}`].some((candidate) => {
    try {
      return info.running(candidate);
    } catch (_error) {
      return false;
    }
  });
}

function localUrl(kernel) {
  const local = kernel && kernel.memory && kernel.memory.local;
  if (!local) {
    return null;
  }
  const entry =
    local[startScript] ||
    local[scriptHref("start.js")] ||
    local[path.join(repoRoot, "pinokio", "start.js")];
  return entry && entry.url ? entry.url : null;
}

module.exports = {
  version: "1.0.0",
  title: "Leibniz Verification Dashboard",
  description:
    "Local verification dashboard with accessibility and reproducibility evidence.",
  menu: async (kernel, info) => {
    const installing = isRunning(info, "install.js");
    const running = isRunning(info, "start.js");
    const installed =
      fs.existsSync(installedMarker) &&
      requiredFiles().every((file) => fs.existsSync(file));

    if (installing) {
      return [
        {
          default: true,
          icon: "fa-solid fa-plug",
          text: "Installing",
          href: scriptHref("install.js"),
        },
      ];
    }

    if (running) {
      const items = [];
      const url = localUrl(kernel);
      if (url) {
        items.push({
          default: true,
          popout: true,
          icon: "fa-solid fa-arrow-up-right-from-square",
          text: "Open Dashboard",
          href: url,
        });
      }
      items.push({
        default: items.length === 0,
        icon: "fa-solid fa-terminal",
        text: "Terminal",
        href: scriptHref("start.js"),
      });
      return items;
    }

    if (installed) {
      return [
        {
          default: true,
          icon: "fa-solid fa-play",
          text: "Start",
          href: scriptHref("start.js"),
        },
        {
          icon: "fa-solid fa-rotate",
          text: "Refresh Dashboard Files",
          href: scriptHref("install.js"),
        },
      ];
    }

    return [
      {
        default: true,
        icon: "fa-solid fa-plug",
        text: "Install",
        href: scriptHref("install.js"),
      },
    ];
  },
};
