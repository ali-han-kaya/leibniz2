"use client";

import { Component, type ReactNode } from "react";

import PanelError from "./PanelError";

// Panel-içi hata sınırı — `/trend` ve `/` sayfalarındaki kartları AYRI
// sınırlara alır.
//
// Neden `error.tsx` yetmiyor: App Router'da bir `error.tsx` TÜM segmenti
// sarar. `/trend` sayfası üç veri panelinden (koşum tablosu, karşılaştırma,
// refs grafiği) oluşuyor; sayfa seviyesindeki tek sınır yalnız grafiğin
// kaynağı bozulduğunda tabloyu da düşürürdü. Bu sınır her kartın kendi
// `PanelError`ini basmasını sağlar; sağlam paneller yerinde kalır.
//
// Neden class: React'te hata sınırı hâlâ yalnız `componentDidCatch` /
// `getDerivedStateFromError` ile kurulur (hook karşılığı yok). Hata
// yakalama sınırın KENDİ render'ında olmaz; alt ağaçta olur — yani sınırın
// içine konan server component'lerin async render hatası da buraya düşer.
//
// `reset`: yalnız state'i temizler; alt ağaç yeniden render edilir. Yeni bir
// upstream turu için `PanelError` ayrıca `router.refresh()` çağırır (bkz. o
// dosyadaki retry sözleşmesi) — ikisi birlikte gerekli.
//
// `resetKey` — YAPIŞKAN HATA ÇÖZÜMÜ:
// Sınırın state'i, yeni RSC verisi gelse bile kendiliğinden temizlenmez;
// kaynak düzeldiğinde kart "yüklenemedi"de kalır (ölçüldü: E2E'de tablo
// tazelenirken karşılaştırma/refs kartları hata mesajını React'in minify
// edilmiş iç hatasına çevirip asılı kalıyordu — kullanıcıya kaynağın gerçek
// sebebi de görünmüyordu). Üst sunucu bileşeni her render'da değişen bir
// `resetKey` (ör. `Date.now()`) geçerse sınır yeni veriyi "yeni tur" sayar ve
// hatayı bırakır: kaynak düzeldiyse kart kendini toparlar, düzelmediyse
// GÜNCEL hata metnini gösterir. Verilmezse davranış eskisi gibidir
// (yalnız elle retry).
type Props = {
  /** Hata kartının başlığı — panelin adını taşır, genel "hata" değil. */
  title: string;
  hint?: string;
  /** Her yeni sunucu render'ında değişen anahtar; değişince hata bırakılır. */
  resetKey?: string | number;
  children: ReactNode;
};

type State = { error: Error | null; resetKey?: string | number };

export default class PanelBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromProps(props: Props, state: State): State | null {
    if (props.resetKey === undefined || props.resetKey === state.resetKey) {
      return null; // değişiklik yok: hatayı koru
    }
    // Yeni tur: eski hata ARTIK kanıt değil — gelen veriyle yeniden dene.
    return { error: null, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  private reset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <PanelError
          title={this.props.title}
          message={this.state.error.message}
          hint={this.props.hint}
          onRetry={this.reset}
        />
      );
    }
    return this.props.children;
  }
}
