import { useEffect, useState } from "react";
import {
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
} from "remotion";
import type { LeibnizData } from "./data";

/**
 * delayRender + fetch: veri dosyasi ilk kareyi bekletir, hicbir sahne yari
 * yuklenmis veriyle cizilmez.
 *
 * `url` verilirse o adres okunur — tarayici-ici oynatmada (@remotion/player)
 * veri preview sunucusundan gelir, `staticFile` ise render pipeline'ina
 * ozgudur. Verilmezse render varsayilanina dusulur.
 */
export const useLeibnizData = (url?: string): LeibnizData | null => {
  const [data, setData] = useState<LeibnizData | null>(null);
  const [handle] = useState(() => delayRender("leibniz-data"));
  const source = url ?? staticFile("data/leibniz.json");

  useEffect(() => {
    let cancelled = false;
    fetch(source)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`leibniz.json ${res.status}`);
        }
        return res.json() as Promise<LeibnizData>;
      })
      .then((json) => {
        if (cancelled) {
          return;
        }
        setData(json);
        continueRender(handle);
      })
      .catch((err: unknown) => cancelRender(err));

    return () => {
      cancelled = true;
    };
  }, [handle, source]);

  return data;
};
