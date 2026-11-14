export async function readDocument(file: File): Promise<{ title: string; body: string }> {
  const name = file.name.replace(/\.[^.]+$/, "");
  const lower = file.name.toLowerCase();
  if (file.size > 8_000_000) throw new Error("That file is larger than 8 MB.");
  if (lower.endsWith(".docx")) {
    const mammoth = await import("mammoth");
    const result = await mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() });
    return { title: name, body: result.value.slice(0, 20000) };
  }
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls") || lower.endsWith(".csv")) {
    const XLSX = await import("xlsx");
    const book = XLSX.read(await file.arrayBuffer(), { type: "array" });
    const parts = book.SheetNames.slice(0, 6).map((sheet) => {
      const rows = XLSX.utils.sheet_to_csv(book.Sheets[sheet] ?? {});
      return `# ${sheet}\n${rows}`;
    });
    return { title: name, body: parts.join("\n\n").slice(0, 20000) };
  }
  if (lower.endsWith(".pdf")) {
    const pdfjs = await import("pdfjs-dist");
    const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
    pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
    const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
    const pages: string[] = [];
    const count = Math.min(doc.numPages, 20);
    for (let i = 1; i <= count; i += 1) {
      const page = await doc.getPage(i);
      const content = await page.getTextContent();
      pages.push(content.items.map((item) => ("str" in item ? item.str : "")).join(" "));
    }
    return { title: name, body: pages.join("\n\n").slice(0, 20000) };
  }
  const text = await file.text();
  return { title: name || file.name, body: text.slice(0, 20000) };
}
