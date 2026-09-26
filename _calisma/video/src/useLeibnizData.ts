import { useEffect, useState } from "react";
import {
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
} from "remotion";
import type { LeibnizData } from "./data";

/**
 * delayRender + staticFile: the data file gates the first frame, so no scene
 * ever renders against a half-loaded payload.
 */
export const useLeibnizData = (): LeibnizData | null => {
  const [data, setData] = useState<LeibnizData | null>(null);
  const [handle] = useState(() => delayRender("leibniz-data"));

  useEffect(() => {
    let cancelled = false;
    fetch(staticFile("data/leibniz.json"))
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
  }, [handle]);

  return data;
};
