import { useState } from "react"
import { useSWR, mutate } from "swr"

interface CSVFile {
  file: File | null;
}

export default function UploadCSV({ onUpload }: { onUpload: (file: File) => void }) {
  const [csvFile, setCsvFile] = useState<CSVFile>({ file: null });

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setCsvFile({ file: event.target.files[0] });
    }
  };

  const handleSubmit = async () => {
    if (!csvFile.file) return;

    onUpload(csvFile.file);
  };

  return (
    <div className="mt-4">
      <input type="file" onChange={handleFileChange} />
      <button onClick={handleSubmit}>Upload CSV</button>
    </div>
  );
}