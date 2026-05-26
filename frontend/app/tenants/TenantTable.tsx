import { useState } from "react"
import { useSWR, mutate } from "swr"
import { cn } from "@/lib/utils"

interface Tenant {
  id: string
  name: string
  email: string
  phone: string | null
  unit_id: string | null
}

export default function TenantTable({ tenants }: { tenants: Tenant[] }) {
  const [showModal, setShowModal] = useState(false)

  const handleDeleteTenant = async (tenantId: string) => {
    try {
      await fetch(`/api/v1/tenants/${tenantId}`, {
        method: "DELETE",
      })

      mutate("/api/v1/tenants")
    } catch (error) {
      console.error(error)
      alert("An error occurred while deleting the tenant.")
    }
  }

  return (
    <div className={cn(
      "flex flex-col gap-4 p-8",
      tenants.length === 0 ? "opacity-50 pointer-events-none" : ""
    )}>
      {showModal && (
        <TenantTable onClose={handleCloseModal} />
      )}
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Unit ID</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((tenant) => (
            <tr key={tenant.id}>
              <td>{tenant.name}</td>
              <td>{tenant.email}</td>
              <td>{tenant.phone || "N/A"}</td>
              <td>{tenant.unit_id || "N/A"}</td>
              <td>
                <button onClick={() => handleDeleteTenant(tenant.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}