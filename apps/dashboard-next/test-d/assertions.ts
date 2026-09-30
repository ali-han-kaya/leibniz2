// Tip-düzeyi test araç seti — `AssertEqual` (assert-equal) deseni.
//
// Neden `tsc` tek başına yetmiyor: tsc "bu iki tip AYNI mı" diye sormaz;
// yalnız "bu değer şu tipe atanabilir mi" diye sorar. Atanabilirlik eşitlikten
// GEVŞEKTİR: `{ p0?: number }` ile `{ p0?: number; verdict?: string }`
// birbirine atanabilir, ama aynı sözleşme değildir — biri alanı gizler. Bir
// tel-sözleşmesini (Latest/TrendRow) kilitlemek için EŞİTLİK gerekir.
//
// Eşitlik ancak ters-varyant (invariant) bir generic üzerinden kurulabilir:
// aşağıdaki koşullu-tip hilesi iki çağrı imzasını karşılaştırır. `any`,
// `never`, `readonly`, opsiyonellik ve literal daralması bu karşılaştırmada
// görünür — düz `extends` ile görünmezler.

/**
 * `A` ve `B` TAM olarak aynı tip mi?
 *
 * Ters-varyant karşılaştırma: iki generic imzanın birbirine atanabilirliği
 * ancak gövdeleri birebir aynıysa sağlanır; bu yüzden opsiyonel/required
 * farkı, fazladan alan, `readonly` ve literal daralması hep `false` üretir.
 */
export type Equal<A, B> =
  (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2
    ? true
    : false;

/**
 * İddia çekirdeği: `T` tam olarak `true` olmalı, değilse derleme hatası.
 *
 * Kısıt (`extends true`) hata ÜRETİCİSİdir: takma adın kendisi sessiz kalır,
 * hata yalnız bu kısıt denetlendiğinde doğar.
 */
export type Assert<T extends true> = T;

/** `Assert`in okunur takma adı; iddia cümlesi gibi okunsun diye. */
export type Expect<T extends true> = T;

/**
 * `AssertEqual` DESENİ — çağrı biçimi: `Assert<Equal<A, B>>`.
 *
 * Tek parça bir `AssertEqual<A, B>` takma adı NEDEN MÜMKÜN DEĞİL (denendi,
 * ölçüldü): tsc generic bir takma adın GÖVDESİNİ çözülmemiş parametrelerle
 * denetler; o anda `Equal<A, B>` bir `boolean`a düşer ve `Assert`in `true`
 * kısıtını ihlal eder:
 *
 *   error TS2344: Type 'Equal<A, B>' does not satisfy the constraint 'true'.
 *     Type 'boolean' is not assignable to type 'true'.
 *
 * Kısıt denetimi ÇAĞRI YERİNDE olmak zorundadır. Bu yüzden desen iki parçalı
 * ve tek doğru kullanım şudur:
 *
 *   type _Ornek = Assert<Equal<1, 1>>;      // geçer
 *   type _Hata  = Assert<Equal<1, 2>>;      // TS2344 — iddia düştü
 *
 * İkinci parça olmadan (`type _ = Equal<1, 2>` → `false`) hiçbir şey olmaz:
 * `false` geçerli bir tiptir. Hatayı üreten kısıttır.
 */

/** `T` kesinlikle `never` mı? (`never` boş kümedir; `Equal` yanılabilir.) */
export type IsNever<T> = [T] extends [never] ? true : false;

/**
 * `T` kesinlikle `any` mı?
 *
 * Ayrı bir araç gerekir çünkü `any` her iki yönde de atanabildiği için
 * eşitlik testi onu "beklenmedik biçimde" geçebilir; `1 & any` = `1` kimliği
 * `any`i tek başına yakalar.
 */
export type IsAny<T> = 0 extends 1 & T ? true : false;

/** Mantıksal değil. Okunabilirlik için: `Assert<Not<Equal<...>>>`. */
export type Not<T extends boolean> = T extends true ? false : true;

/**
 * `A`, `B`ye atanabilir mi? (eşitlikten gevşek ama bazen doğru soru bu.)
 *
 * Tuple sarmalaması union dağıtımını engeller: `string | number`'ın `string`e
 * "kısmen" uyduğunu gizlemesin, tek parça olarak değerlendirilsin.
 */
export type Extends<A, B> = [A] extends [B] ? true : false;
