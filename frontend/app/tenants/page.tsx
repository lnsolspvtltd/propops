import { useState } from "react"
import { useSWR, mutate } from "swr"
import { cn } from "@/lib/utils"
import TenantTable from "./TenantTable"
import UploadCSV from "./UploadCSV"

export default function Page() {
  const [showModal, setShowModal] = useState(false)

  const { data: tenants, error, isLoading } = useSWR("/api/v1/tenants", async (url) => {
    const res = await fetch(url)
    if (!res.ok) throw new Error("Failed to fetch tenants")
    return res.json()
  })

  const handleCreateTenant = async () => {
    setShowModal(true)
  }

  const handleCloseModal = () => {
    setShowModal(false)
  }

  const handleUploadCSV = async (file: File) => {
    const formData = new FormData()
    formData.append("file", file)

    try {
      const res = await fetch("/api/v1/tenants/bulk", {
        method: "POST",
        body: formData,
      })

      if (!res.ok) throw new Error("Failed to upload CSV")

      const { created, skipped, errors } = await res.json()
      alert(`Created ${created} tenants, skipped ${skipped}. Errors: ${errors.map(e => e.email).join(", ")}`)
    } catch (error) {
      console.error(error)
      alert("An error occurred while uploading the CSV.")
    }
  }

  return (
    <div className={cn(
      "flex flex-col gap-4 p-8",
      isLoading ? "opacity-50 pointer-events-none" : ""
    )}>
      {showModal && (
        <TenantTable onClose={handleCloseModal} />
      )}
      <button onClick={handleCreateTenant}>Add Tenant</button>
      <UploadCSV onUpload={handleUploadCSV} />
      {tenants && (
        <div className="mt-4">
          <h2>Tenants</h2>
          <TenantTable tenants={tenants.tenants} />
        </div>
      )}
    </div>
  )
}