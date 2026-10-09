export function hasImportableRows(preview) {
  return Number.isInteger(preview?.valid_rows) && preview.valid_rows > 0;
}
