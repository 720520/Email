import { describe, expect, it } from 'vitest'

import { resolveExportDate } from './export-date'

describe('resolveExportDate', () => {
  it('未选择日期时使用数据库最新净值日期', () => {
    expect(resolveExportDate([], '2026-07-31')).toBe('2026-07-31')
  })

  it('选择日期时优先使用区间结束日期', () => {
    expect(resolveExportDate(['2026-07-01', '2026-07-24'], '2026-07-31'))
      .toBe('2026-07-24')
  })

  it('数据库没有净值时不回退到今天', () => {
    expect(resolveExportDate([], null)).toBe('')
  })
})
