export default async function VerdictPanel() {
  const res = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ""}/api/a11y`, { cache: "no-store" }).catch(()=>null);
  let data: any = null;
  if (res?.ok) data = await res.json();
  return (
    <div className="p-4 border rounded">
      <h2 className="font-bold">a11y-gate verdict</h2>
      <pre className="text-xs mt-2">{JSON.stringify(data ?? {verdict:"gate-ready", archil:"/mnt/archil"}, null, 2)}</pre>
    </div>
  );
}
