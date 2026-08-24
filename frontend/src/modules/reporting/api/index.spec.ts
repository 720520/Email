import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
}))

vi.mock('@/platform/api/http', () => ({ http }))

import {
  cancelReportBatch,
  confirmReportRunAsTemplate,
  createOnlyOfficeSession,
  createReportBatch,
  downloadReportBatch,
  getReportBatch,
  getReportBatchItems,
  getReportDesignMetadata,
  createDynamicReportField,
  getDynamicReportFields,
  publishReportTemplate,
  retryReportBatch,
  resolveDynamicReportFields,
  setProductReportFieldValue,
  updateDynamicReportField,
  updateReportLayout,
  validateReportTemplate,
} from './index'

describe('报表字段与模板 API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('加载、新建和编辑字段时使用稳定接口', async () => {
    const rows = [{ field_key: 'custom.contact' }]
    http.get.mockResolvedValueOnce({ data: rows })
    http.post.mockResolvedValueOnce({ data: rows[0] })
    http.patch.mockResolvedValueOnce({ data: { ...rows[0], label: '联系人' } })

    expect(await getDynamicReportFields(true)).toBe(rows)
    await createDynamicReportField({
      field_key: 'custom.contact',
      label: '联系人',
      data_type: 'string',
      value_kind: 'scalar',
      is_required: false,
      is_sensitive: false,
      format_config: {},
    })
    await updateDynamicReportField(7, { label: '联系人' })

    expect(http.get).toHaveBeenCalledWith('/report-fields', {
      params: { include_inactive: true },
    })
    expect(http.post).toHaveBeenCalledWith('/report-fields', expect.any(Object))
    expect(http.patch).toHaveBeenCalledWith('/report-fields/7', { label: '联系人' })
  })

  it('维护产品值并测试解析结果', async () => {
    http.put.mockResolvedValueOnce({ data: { value: '王经理' } })
    http.post.mockResolvedValueOnce({ data: { fields: { 'custom.contact': { value: '王经理' } } } })

    await setProductReportFieldValue(3, 'custom.contact', {
      value: '王经理',
      source_reference: '路演资料',
    })
    const resolved = await resolveDynamicReportFields({
      field_keys: ['custom.contact'],
      product_id: 3,
    })

    expect(http.put).toHaveBeenCalledWith(
      '/report-fields/products/3/values/custom.contact',
      { value: '王经理', source_reference: '路演资料' },
    )
    expect(resolved.fields['custom.contact'].value).toBe('王经理')
  })

  it('模板校验和发布使用草稿生命周期接口', async () => {
    http.post
      .mockResolvedValueOnce({ data: { status: 'draft', validation_errors: [] } })
      .mockResolvedValueOnce({ data: { status: 'published', version: 1 } })

    expect((await validateReportTemplate(9)).status).toBe('draft')
    expect((await publishReportTemplate(9)).status).toBe('published')
    expect(http.post).toHaveBeenNthCalledWith(1, '/reports/templates/9/validate')
    expect(http.post).toHaveBeenNthCalledWith(2, '/reports/templates/9/publish')
  })

  it('可把 OnlyOffice 样板运行确认成批量模板', async () => {
    http.post.mockResolvedValueOnce({
      data: { key: 'template-version:21', status: 'published', version: 1 },
    })

    const template = await confirmReportRunAsTemplate(18, {
      name: '周报批量模板',
      description: '已完成字段定位',
    })

    expect(template.key).toBe('template-version:21')
    expect(http.post).toHaveBeenCalledWith(
      '/reports/runs/18/confirm-template',
      { name: '周报批量模板', description: '已完成字段定位' },
      { timeout: 180_000 },
    )
  })

  it('批量任务支持创建、轮询、重试、取消和 ZIP 下载', async () => {
    const batch = { id: 12, status: 'pending' }
    http.post.mockResolvedValue({ data: batch })
    http.get
      .mockResolvedValueOnce({ data: batch })
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: new Blob(['zip']) })

    await createReportBatch({
      product_ids: [1, 2],
      template_key: 'builtin:weekly',
      report_date: '2026-08-21',
      sections: ['product_info'],
      settings: {},
      idempotency_key: 'batch-test-key',
    })
    await getReportBatch(12)
    await getReportBatchItems(12)
    await retryReportBatch(12)
    await cancelReportBatch(12)
    await downloadReportBatch(12)

    expect(http.post).toHaveBeenCalledWith('/reports/batches', expect.any(Object))
    expect(http.post).toHaveBeenCalledWith('/reports/batches/12/retry')
    expect(http.post).toHaveBeenCalledWith('/reports/batches/12/cancel')
    expect(http.get).toHaveBeenLastCalledWith('/reports/batches/12/download', {
      responseType: 'blob',
    })
  })

  it('OnlyOffice 预览会话使用报表运行编号', async () => {
    http.post.mockResolvedValueOnce({
      data: { api_url: 'http://127.0.0.1:8080/api.js', config: {} },
    })
    await createOnlyOfficeSession(18)
    expect(http.post).toHaveBeenCalledWith('/reports/runs/18/onlyoffice/session')
  })

  it('读取并保存拖拽布局坐标', async () => {
    const metadata = { slide_count: 2, slide_width: 16, slide_height: 9, placements: [] }
    http.get.mockResolvedValueOnce({ data: metadata })
    http.post.mockResolvedValueOnce({ data: { id: 18, current_version: 2 } })
    const placement = {
      id: 'field1', token: '{{product_name}}', slide: 1,
      x: 0.1, y: 0.2, width: 0.3, height: 0.1,
      font_size: 18, bold: false, color: '#173B4D',
    }

    expect((await getReportDesignMetadata(18)).slide_count).toBe(2)
    await updateReportLayout(18, [placement])

    expect(http.get).toHaveBeenCalledWith('/reports/runs/18/design-metadata')
    expect(http.post).toHaveBeenCalledWith(
      '/reports/runs/18/layout',
      { placements: [placement] },
      { timeout: 180_000 },
    )
  })
})
