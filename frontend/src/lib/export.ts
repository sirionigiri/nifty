import * as XLSX from 'xlsx';

/**
 * Single sheet export
 */
export function exportToExcel(data: any[], fileName: string) {
  const worksheet = XLSX.utils.json_to_sheet(data);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Data");
  XLSX.writeFile(workbook, `${fileName}.xlsx`);
}

/**
 * Multi-sheet export for the Full Report
 */
export function exportFullReport(sections: { name: string, data: any[] }[], fileName: string) {
  const workbook = XLSX.utils.book_new();
  
  sections.forEach(section => {
    if (section.data && section.data.length > 0) {
      const worksheet = XLSX.utils.json_to_sheet(section.data);
      XLSX.utils.book_append_sheet(workbook, worksheet, section.name);
    }
  });

  XLSX.writeFile(workbook, `${fileName}.xlsx`);
}