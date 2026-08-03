import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

for (const workbookPath of process.argv.slice(2)) {
  const input = await FileBlob.load(workbookPath);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table,region",
    maxChars: 12000,
    tableMaxRows: 12,
    tableMaxCols: 12,
    tableMaxCellChars: 120,
  });
  process.stdout.write(`${JSON.stringify({ workbookPath })}\n`);
  process.stdout.write(`${summary.ndjson}\n`);
}
