/**
 * 导出日期优先使用运营人员选择的估值区间；未选择时使用数据库最新净值日。
 * 数据库为空时返回空字符串，由页面禁用导出，绝不回退到自然日。
 */
export function resolveExportDate(selectedDates: string[], latestNavDate: string | null) {
  return selectedDates[1] || selectedDates[0] || latestNavDate || ''
}
