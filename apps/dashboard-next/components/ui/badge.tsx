"use client";

// NOT (shadcn CLI çıktısı, elle eklendi): `useRender` bir React hook'u
// (useMergedRefs → useRef/useMemo) çağırıyor, bu yüzden modül istemci
// sınırında olmak zorunda. components.json'daki `rsc: true` bunu atlamış;
// Server Component'ten (VerdictCard) kullanıldığında `next build`
// "component that needs useState" hatası veriyor.

import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "cn";

// NOT (2026-09-28): taban sınıfı `transition-all`dı — buton tabanındaki
// aynı kusur (bkz. components/ui/button.tsx). `all` tarayıcıya her özelliği
// animasyona sokabileceğini söyler; tema değişiminde (data-theme) layout/paint
// özellikleri de geçişe girip titreme üretir. Rozet panoda CANLI (VerdictCard
// P0/P1 istatistikleri `statBadge` ile bu primitive'i kullanır), o yüzden
// düzeltme kozmetik değil.
//
// Liste rozetin gerçekten değiştirdiği özellikler: metin/kenar/zemin rengi
// (variant + `[a]:hover:*`) ve halka (`focus-visible:ring-*`). Butondaki
// `transform`/`opacity` burada yok — rozette `active:translate-*` ya da
// `disabled:opacity-*` işareti YOK, olmayan özelliği listeye yazmak
// sözleşmeyi süsler. `link` varyantındaki `hover:underline` de bilinçli
// olarak dışarıda: `text-decoration-line` ayrık (discrete) bir özelliktir,
// geçiş üretmez.
const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-[color,background-color,border-color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        secondary:
          "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive:
          "bg-destructive/10 text-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20",
        outline:
          "border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground",
        ghost:
          "hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  });
}

export { Badge, badgeVariants };
