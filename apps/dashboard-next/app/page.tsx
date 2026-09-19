import { Suspense } from "react";
import VerdictCard from "./VerdictCard";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function HomePage() {
  return (
    <div className="space-y-6">
      {/* Streaming: verdict kartı kendi Suspense sınırında akar */}
      <Suspense
        fallback={
          <div className="h-44 animate-pulse rounded-lg border border-border bg-surface" />
        }
      >
        <VerdictCard />
      </Suspense>

      <p className="text-sm text-muted">
        Trend görünümü:{" "}
        <Link
          className={cn(buttonVariants({ variant: "ghost" }), "text-accent")}
          href="/trend"
        >
          /trend
        </Link>{" "}
        · Canlı pano:{" "}
        <a
          className={cn(buttonVariants({ variant: "ghost" }), "text-accent")}
          href="http://127.0.0.1:8000/preview.html"
        >
          preview.html
        </a>
      </p>
    </div>
  );
}
