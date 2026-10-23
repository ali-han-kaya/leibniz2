// scripts_build_player.mjs — @remotion/player paketini tek statik dosyaya toplar.
//
// Neden esbuild: Remotion Studio'nun webpack dev-cache'i arac tarafindan
// olduruluyor ve CWD'ye yazıyor; preview sunucusu yalnizca statik dosya
// servis edebilir. esbuild tek dosya, hizli, yapilandirmasiz.
//
// Cikti: dist/player.js  (preview sunucusu /video/player.js olarak servis eder)
//         dist/leibniz.json (make_data.py ciktisinin kopyasi)
// dist/ yeniden uretilebilir → repoda tutulmaz.
import { build } from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// script scripts/ altinda durur -> proje koku bir seviye yukarida.
const here = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(here, "dist");
mkdirSync(dist, { recursive: true });

const result = await build({
  entryPoints: [join(here, "src", "player.tsx")],
  outfile: join(dist, "player.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["chrome110", "safari16", "firefox115"],
  minify: true,
  sourcemap: false,
  legalComments: "none",
  define: { "process.env.NODE_ENV": '"production"' },
  // Remotion birkac kez uyarir (dynamic require vb.); sessiz gecmek yerine
  // ucuz paket oncesi gorunur tutalim.
  logLevel: "warning",
  metafile: true,
});

const bytes = Object.values(result.metafile.outputs)[0].bytes;
console.log(`build:player → dist/player.js (${Math.round(bytes / 1024)} KiB)`);

// Sayfa kabugu ve veri kopyasi: preview sunucusu /video/* altindan servis eder.
copyFileSync(join(here, "build", "player.html"), join(dist, "player.html"));
copyFileSync(join(here, "build", "player.css"), join(dist, "player.css"));
copyFileSync(
  join(here, "public", "data", "leibniz.json"),
  join(dist, "leibniz.json")
);
console.log("build:player → dist/{player.html,player.css,leibniz.json}");
