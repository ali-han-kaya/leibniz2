-- =============================================================================
-- trend_runs — K0-K21 katman fotoğrafı + P0/P1 bulgu ayrıntısı
-- =============================================================================
-- Neden yeni kolon: tarihsel olarak yalnız SKALERLER (p0/p1, z3_*) kalıcıydı;
-- per-katman durumu (K0-K21) ve bulgu AYRINTISI (id/check/issue/evidence)
-- yalnız canlı preview_server belleğinde (/api/latest) duruyordu. Sunucu
-- yeniden başlayınca katman geçmişi kayboluyor, /layers sayfası yalnız "son
-- koşum"u gösterebiliyordu. Bu kolon her koşumun katman fotoğrafını arşive
-- yazar; dashboard DB kaynağında buradan okur.
--
-- Şekil (verify_delivery.py --klayers-out / build_layers_summary):
--   {"K0": {"label": "...", "status": "PASS|FAIL|SKIP", "ran": true,
--           "findings": [{"id","priority","check","issue","evidence"}]},
--    ... "UNREGISTERED": {...}}
--
-- Neden JSONB (katman başına satır değil): okuma deseni daima "bir koşumun
-- TAM fotoğrafı" (trend_runs'ta zaten satır başına tek snapshot); 22 katmanı
-- ayrı tabloya açmak her koşumda 22 kopya satır + JOIN gerektirir ve pano tek
-- satır okuyor. JSONB yine de alan bazında sorgulanabilir:
--   layers->'K14'->>'status'
--   layers @> '{"K14": {"status": "FAIL"}}'
--
-- İndeks: bugünkü okuma `order by ts desc limit 1` (unique ts indeksi yeter);
-- katman-bazlı "son N koşumda K14 kaç kez FAIL" sorgusu geldiğinde GIN
-- (jsonb_path_ops) eklenir — 300 satırlık tabloda bugün seq scan doğru.
--
-- Not: findings kolonu zaten vardı (P0/P1 ayrıntısı); bu migration onu
-- DEĞİŞTİRMEZ, yalnız katman haritasını ekler. Yeni kolon RLS politikasının
-- kapsamındadır (satır düzeyi kural kolondan bağımsız).
-- =============================================================================

alter table public.trend_runs
  add column if not exists layers jsonb;

-- Geri alma:
--   alter table public.trend_runs drop column if exists layers;
