import fs from "fs";
import path from "path";
export async function GET() {
  let refs = null;
  try {
    // refs-index.json repo kökünde yaşar; cwd repo kökü ya da
    // apps/dashboard-next olabildiği için yukarı doğru aranır.
    // Mutlak (/Users/...) yol YASAK — check-absolute-paths kapısı.
    let dir = process.cwd();
    for (let i = 0; i < 6; i++) {
      const p = path.join(dir, "_calisma/CIKTI/refs-index.json");
      if (fs.existsSync(p)) {
        refs = JSON.parse(fs.readFileSync(p, "utf-8"));
        break;
      }
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  } catch {}
  return Response.json({
    verdict: "gate-ready",
    archil: "/mnt/archil",
    memory: "/mnt/archil/memory/long_term_memory.md",
    refs_index: refs,
    generated_at: new Date().toISOString()
  });
}
