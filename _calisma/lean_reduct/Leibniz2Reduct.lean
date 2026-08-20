/-
Kök modül (lake kuralı): srcDir = "." olan bir lean_lib, kendi adında bir
kök modül dosyası gerektirir (Leibniz2Reduct.lean). İçerik Leibniz2Reduct/
Content.lean'dedir — bu dosya onu içe aktarır, böylece `lake build --wfail`
8 teoremi derler. (Shim Content.lean ve K9 ReductInvariance.lean lake
target'ı DEĞİLDİR — srcDir="." düzeninde lake yalnızca Leibniz2Reduct
ad alanındaki modülleri derler; ikisi kendi kapılarıyla doğrulanır:
`lean Content.lean` ve verify_lean.sh/lean ReductInvariance.lean.)
-/
import Leibniz2Reduct.Content
