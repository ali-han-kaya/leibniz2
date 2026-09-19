import { Suspense } from "react";
import VerdictCard from "./VerdictCard";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function HomePage() {
  return (
    <div className="space-y-6">
      {/* Streaming: verdict kartı kendi Suspense sınırında akar */}
      <Suspense
        fallback={
          <div className="h-44 animate-pulse rounded-lg border border-[#30363d] bg-[#161b22]" />
        }
      >
        <VerdictCard />
      </Suspense>

      <p className="text-sm text-[#8b949e]">
        Trend görünümü:{" "}
        <a
          className={cn(buttonVariants({ variant: "ghost" }), "text-[#58a6ff]")}
          href="/trend"
        >
          /trend
        </a>{" "}
        · Canlı pano:{" "}
        <a
          className={cn(buttonVariants({ variant: "ghost" }), "text-[#58a6ff]")}
          href="http://127.0.0.1:8000/preview.html"
        >
          preview.html
        </a>
      </p>
    </div>
  );
}
