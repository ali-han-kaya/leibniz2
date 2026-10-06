import fs from "fs";
import path from "path";
export async function GET() {
  let refs = null;
  try {
    const p = path.join(process.cwd(), "_calisma/CIKTI/refs-index.json");
    if (!fs.existsSync(p)) {
      const p2 = "/Users/alikaya/Desktop/leibniz2/_calisma/CIKTI/refs-index.json";
      refs = JSON.parse(fs.readFileSync(p2, "utf-8"));
    } else {
      refs = JSON.parse(fs.readFileSync(p, "utf-8"));
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
