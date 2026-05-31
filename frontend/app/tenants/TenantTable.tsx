"use client";
interface Tenant {
  id: string; name: string; email: string;
  phone: string | null; unit_id: string | null;
}
interface Props {
  tenants: Tenant[];
  onDelete: (id: string) => void;
}
export default function TenantTable({ tenants, onDelete }: Props) {
  if (tenants.length === 0)
    return <p className="text-gray-500 text-sm">No tenants yet. Add one or upload a CSV.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-gray-400 text-left">
            <th className="pb-2 pr-4">Name</th>
            <th className="pb-2 pr-4">Email</th>
            <th className="pb-2 pr-4">Phone</th>
            <th className="pb-2 pr-4">Unit</th>
            <th className="pb-2" />
          </tr>
        </thead>
        <tbody>
          {tenants.map((t) => (
            <tr key={t.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
              <td className="py-2 pr-4 text-white">{t.name}</td>
              <td className="py-2 pr-4 text-gray-300">{t.email}</td>
              <td className="py-2 pr-4 text-gray-400">{t.phone ?? "—"}</td>
              <td className="py-2 pr-4 text-gray-400">{t.unit_id ?? "—"}</td>
              <td className="py-2">
                <button onClick={() => onDelete(t.id)}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors">
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
