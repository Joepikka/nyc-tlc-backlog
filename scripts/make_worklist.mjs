import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = new URL("../", import.meta.url);
const data = JSON.parse(await fs.readFile(new URL("report/validation.json", root), "utf8"));
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Review list");
sheet.showGridLines = false;
sheet.tabColor = "#087E85";

const navy = "#12293F";
const teal = "#087E85";
const muted = "#456178";
const rowCount = data.taxi_review_list.length;
const end = rowCount + 7;
const columns = [9, 17, 24, 23, 16, 12, 22, 34, 18];
columns.forEach((width, column) => {
  sheet.getRangeByIndexes(0, column, end, 1).format.columnWidth = width;
});
sheet.getRange(`A1:I${end}`).format.font = { name: "Aptos", size: 11, color: navy };
sheet.getRange(`A1:I${end}`).format.verticalAlignment = "center";
sheet.getRange(`A8:I${end}`).format.rowHeight = 22;

function band(row, text, height, style) {
  const range = sheet.getRange(`A${row}:I${row}`);
  range.merge();
  range.format.rowHeight = height;
  range.format.font = { name: "Aptos", ...style.font };
  range.format.fill = style.fill;
  range.getCell(0, 0).values = [[text]];
}

band(1, " NYC TLC  /  OPERATIONS REVIEW", 25, {
  font: { color: "#B8E3E3", size: 12, bold: true }, fill: navy,
});
band(2, " Taxi Complaint review list", 39, {
  font: { color: "#FFFFFF", size: 23, bold: true }, fill: navy,
});
band(3, " March 31, 2025 end-of-day snapshot  ·  Requests created since January 1, 2024", 24, {
  font: { color: muted, size: 11 }, fill: "#F1F5F9",
});
band(4, ` ${rowCount} of ${data.by_problem["Taxi Complaint"].backlog.toLocaleString("en-US")} open Taxi Complaint records  ·  Age descending, then request key ascending`, 23, {
  font: { color: muted, size: 11 }, fill: "#F1F5F9",
});
band(5, " Enter reviewer, action and follow-up date in the shaded columns.", 23, {
  font: { color: "#075C61", size: 11, bold: true }, fill: "#E8F6F4",
});
sheet.getRange("A6:I6").format.rowHeight = 12;

sheet.getRange("A7:I7").values = [[
  "Priority", "Request key", "Problem", "Borough", "Created date", "Age (days)",
  "Reviewer", "Action", "Follow-up date",
]];
const excelDate = (iso) => Date.parse(`${iso}T00:00:00Z`) / 86400000 + 25569;
sheet.getRange(`B8:B${end}`).setNumberFormat("@");
sheet.getRange(`A8:I${end}`).values = data.taxi_review_list.map((row, index) => [
  index + 1, row.unique_key, row.problem, row.borough, excelDate(row.created_day),
  Number(row.age_days), null, null, null,
]);
sheet.getRange(`E8:E${end}`).setNumberFormat("yyyy-mm-dd");
sheet.getRange(`I8:I${end}`).setNumberFormat("yyyy-mm-dd");
sheet.getRange(`G8:I${end}`).format.fill = "#E8F6F4";
const table = sheet.tables.add(`A7:I${end}`, true, "TaxiComplaintReview");
table.style = "TableStyleMedium2";
sheet.getRange("A7:F7").format.fill = navy;
sheet.getRange("G7:I7").format.fill = teal;
sheet.getRange("A7:I7").format.font = { name: "Aptos", size: 11, color: "#FFFFFF", bold: true };
sheet.getRange("A7:I7").format.rowHeight = 29;
sheet.freezePanes.freezeRows(7);

const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(fileURLToPath(new URL("report/review-list.xlsx", root)));
if (process.argv[2]) {
  const preview = await workbook.render({ sheetName: "Review list", range: "A1:I14", scale: 1, format: "png" });
  await fs.writeFile(process.argv[2], new Uint8Array(await preview.arrayBuffer()));
}
