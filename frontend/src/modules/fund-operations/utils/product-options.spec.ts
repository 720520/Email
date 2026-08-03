import { describe, expect, it } from 'vitest'

import type { ProductOption } from '../api/types'
import { groupProductOptions, productOptionLabel } from './product-options'

const products: ProductOption[] = [
  { product_name: '吉余示例基金', product_code: 'F001', fund_group_name: '吉余示例基金', share_class: null },
  { product_name: '吉余示例基金A类', product_code: 'F001A', fund_group_name: '吉余示例基金', share_class: 'A类' },
  { product_name: '吉余示例基金B类', product_code: 'F001B', fund_group_name: '吉余示例基金', share_class: 'B类' },
]

describe('product options', () => {
  it('把同一基金不同份额放入同一下拉分组', () => {
    const groups = groupProductOptions(products)
    expect(groups).toHaveLength(1)
    expect(groups[0]?.options.map((item) => item.product_code)).toEqual(['F001', 'F001A', 'F001B'])
  })

  it('份额选项突出类别和产品代码', () => {
    expect(productOptionLabel(products[1]!)).toBe('吉余示例基金A类 · A类 · F001A')
  })
})
